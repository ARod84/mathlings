"""Checks a puzzle without trusting how it was made.

    verify(puzzle, catalog=..., topic_exists=...) -> VerificationResult

A puzzle does not reach a child unless `result.ok`. This module never imports
the generator and does not use its arithmetic: each step is solved by trying
every whole number in the level's range in the box and seeing which ones make
the two sides equal. It works from the puzzle's tokens, so a puzzle written by
hand, by another program or by a model can be checked the same way.

It does share the declared rules of the puzzle type (levels.py) and the
mistake rules (rules.py): a distractor has to equal what its rule gives, and
there is one definition of each rule.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.puzzles.ids import InvalidPuzzleId, parse_puzzle_id
from app.puzzles.levels import (
    ANSWER_LEFT_FORMS,
    DISTRACTORS_PER_STEP,
    GENERATOR_VERSION,
    HINT_TIERS,
    LEVELS,
    MAX_STEPS,
    MIN_STEPS,
    PUZZLE_TYPE,
    LevelSpec,
    topic_ids_for,
)
from app.puzzles.misconceptions import MisconceptionCatalog
from app.puzzles.models import (
    Form,
    MistakeRule,
    NumberToken,
    OperatorToken,
    Puzzle,
    PuzzleStep,
    Token,
    UnknownToken,
)
from app.puzzles.rules import distractor_value, is_near_miss


class FailureName(StrEnum):
    UNSUPPORTED_PUZZLE = "unsupported_puzzle"
    PUZZLE_ID_MISMATCH = "puzzle_id_mismatch"
    BAD_LENGTH = "bad_length"
    MALFORMED_EQUATION = "malformed_equation"
    FORM_MISMATCH = "form_mismatch"
    NEGATIVE_VALUE = "negative_value"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    NO_UNIQUE_SOLUTION = "no_unique_solution"
    WRONG_ANSWER = "wrong_answer"
    TRIVIAL_STEP = "trivial_step"
    MISSING_THREE_DIGIT_NUMBER = "missing_three_digit_number"
    BROKEN_CHAIN_LINK = "broken_chain_link"
    REPEATED_FORM = "repeated_form"
    TOO_MANY_ANSWER_LEFT = "too_many_answer_left"
    DISTRACTOR_COUNT = "distractor_count"
    DUPLICATE_DISTRACTOR = "duplicate_distractor"
    DISTRACTOR_EQUALS_ANSWER = "distractor_equals_answer"
    DISTRACTOR_OUT_OF_RANGE = "distractor_out_of_range"
    DISTRACTOR_RULE_MISMATCH = "distractor_rule_mismatch"
    DISTRACTOR_PATTERN_MISMATCH = "distractor_pattern_mismatch"
    HINT_COUNT = "hint_count"
    HINT_REVEALS_ANSWER = "hint_reveals_answer"
    HINT_MISSING_ANSWER = "hint_missing_answer"
    WRONG_TOPICS = "wrong_topics"
    UNKNOWN_TOPIC = "unknown_topic"


@dataclass(frozen=True)
class Failure:
    name: FailureName
    detail: str
    # 0-based step the failure is in; None when it is about the whole puzzle.
    step: int | None = None


@dataclass(frozen=True)
class VerificationResult:
    failures: list[Failure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def names(self) -> set[FailureName]:
        return {failure.name for failure in self.failures}


# The token shape each form must have: N a number, ? the box, then the operator.
_FORM_SHAPES: dict[Form, tuple[str, str]] = {
    "a+?=c": ("N+?", "N"),
    "?+b=c": ("?+N", "N"),
    "a-?=c": ("N-?", "N"),
    "?-b=c": ("?-N", "N"),
    "c=a+?": ("N", "N+?"),
    "c=?-b": ("N", "?-N"),
}


def _shape(tokens: list[Token]) -> str:
    out = ""
    for token in tokens:
        if isinstance(token, NumberToken):
            out += "N"
        elif isinstance(token, UnknownToken):
            out += "?"
        else:
            out += token.symbol
    return out


def _is_expression(tokens: list[Token]) -> bool:
    """True for value, operator, value, ... : a single value or a chain of + and -."""
    return len(tokens) % 2 == 1 and all(
        isinstance(token, OperatorToken) == (index % 2 == 1) for index, token in enumerate(tokens)
    )


def _evaluate(tokens: list[Token], box: int) -> int | None:
    """The value of one side with `box` in the box, worked left to right.

    None if the side is not an expression, or if the running total dips below
    zero on the way: these children do not have negative numbers yet.
    """
    if not _is_expression(tokens):
        return None
    total = 0
    sign = 1
    for token in tokens:
        if isinstance(token, OperatorToken):
            sign = 1 if token.symbol == "+" else -1
            continue
        total += sign * (box if isinstance(token, UnknownToken) else token.value)
        if total < 0:
            return None
    return total


def _solutions(step: PuzzleStep, max_value: int) -> list[int]:
    """Every whole number from 0 to max_value that makes the equation true."""
    found = []
    for candidate in range(max_value + 1):
        left = _evaluate(step.equation.left, candidate)
        if left is not None and left == _evaluate(step.equation.right, candidate):
            found.append(candidate)
    return found


def _numbers(step: PuzzleStep) -> list[int]:
    return [
        token.value
        for token in (*step.equation.left, *step.equation.right)
        if isinstance(token, NumberToken)
    ]


def _has_standalone_number(text: str, number: int) -> bool:
    return any(int(match) == number for match in re.findall(r"\d+", text))


def _check_step(
    index: int, step: PuzzleStep, spec: LevelSpec, catalog: MisconceptionCatalog
) -> list[Failure]:
    failures: list[Failure] = []

    def fail(name: FailureName, detail: str) -> None:
        failures.append(Failure(name, detail, index))

    # ---- the equation itself ----
    tokens = [*step.equation.left, *step.equation.right]
    boxes = sum(isinstance(token, UnknownToken) for token in tokens)
    well_formed = (
        boxes == 1 and _is_expression(step.equation.left) and _is_expression(step.equation.right)
    )
    if not well_formed:
        fail(FailureName.MALFORMED_EQUATION, "each side must be a sum or difference; one box")
    shapes = (_shape(step.equation.left), _shape(step.equation.right))
    form_ok = shapes == _FORM_SHAPES[step.form]
    if not form_ok:
        fail(FailureName.FORM_MISMATCH, f"tokens {shapes} are not the form {step.form}")

    visible = _numbers(step)
    values = [*visible, step.answer]
    if any(value < 0 for value in values):
        fail(FailureName.NEGATIVE_VALUE, f"negative number among {values}")
    if any(value > spec.max_value for value in values):
        fail(FailureName.VALUE_OUT_OF_RANGE, f"{values} not all within 0..{spec.max_value}")

    # ---- brute-force solve ----
    solutions = _solutions(step, spec.max_value) if well_formed else []
    if len(solutions) != 1:
        fail(
            FailureName.NO_UNIQUE_SOLUTION,
            f"{len(solutions)} numbers in 0..{spec.max_value} make the equation true",
        )
    elif solutions[0] != step.answer:
        fail(FailureName.WRONG_ANSWER, f"stored answer {step.answer}, solved {solutions[0]}")

    if step.answer == 0 or 0 in visible:
        fail(FailureName.TRIVIAL_STEP, "a step may not use 0: it makes the answer free")
    if spec.requires_three_digit and not any(100 <= value <= 999 for value in values):
        fail(FailureName.MISSING_THREE_DIGIT_NUMBER, f"no number from 100 to 999 among {values}")

    # ---- distractors ----
    if len(step.distractors) != DISTRACTORS_PER_STEP:
        fail(
            FailureName.DISTRACTOR_COUNT,
            f"{len(step.distractors)} distractors, need {DISTRACTORS_PER_STEP}",
        )
    distractor_values = [distractor.value for distractor in step.distractors]
    if len(set(distractor_values)) != len(distractor_values):
        fail(FailureName.DUPLICATE_DISTRACTOR, f"repeated value in {distractor_values}")
    for distractor in step.distractors:
        label = f"{distractor.rule.value}={distractor.value}"
        if distractor.value == step.answer:
            fail(FailureName.DISTRACTOR_EQUALS_ANSWER, f"{label} is the answer")
        if not 0 <= distractor.value <= spec.max_value:
            fail(FailureName.DISTRACTOR_OUT_OF_RANGE, f"{label} not within 0..{spec.max_value}")
        if not form_ok:
            continue  # a rule cannot be recomputed on an equation of the wrong shape
        if distractor.rule is MistakeRule.NEAR_MISS:
            if not is_near_miss(distractor.value, step, spec):
                fail(FailureName.DISTRACTOR_RULE_MISMATCH, f"{label} is not a near miss")
        elif distractor_value(distractor.rule, step, spec) != distractor.value:
            expected = distractor_value(distractor.rule, step, spec)
            fail(FailureName.DISTRACTOR_RULE_MISMATCH, f"{label}, but the rule gives {expected}")
        link = catalog.link_for(distractor.rule, spec.primary_topic_id)
        if distractor.error_pattern_id != (link.error_pattern_id if link else None):
            fail(
                FailureName.DISTRACTOR_PATTERN_MISMATCH,
                f"{label} is tagged {distractor.error_pattern_id}",
            )

    # ---- hints ----
    if len(step.hints) != HINT_TIERS:
        fail(FailureName.HINT_COUNT, f"{len(step.hints)} hints, need {HINT_TIERS}")
    else:
        for tier, hint in enumerate(step.hints[:-1], start=1):
            if _has_standalone_number(hint, step.answer):
                fail(FailureName.HINT_REVEALS_ANSWER, f"tier {tier} shows {step.answer}")
        if not _has_standalone_number(step.hints[-1], step.answer):
            fail(FailureName.HINT_MISSING_ANSWER, "the last hint must show the answer")

    return failures


def verify(
    puzzle: Puzzle,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
) -> VerificationResult:
    """Every way `puzzle` breaks the rules, by name. An empty list means it may be used.

    `topic_exists` answers whether a topic id is in the taxonomy database.
    """
    failures: list[Failure] = []
    spec = LEVELS.get(puzzle.level)
    if (
        spec is None
        or puzzle.puzzle_type != PUZZLE_TYPE
        or puzzle.generator_version != GENERATOR_VERSION
    ):
        return VerificationResult(
            [
                Failure(
                    FailureName.UNSUPPORTED_PUZZLE,
                    f"type {puzzle.puzzle_type}, version {puzzle.generator_version}, "
                    f"level {puzzle.level}",
                )
            ]
        )

    try:
        key = parse_puzzle_id(puzzle.puzzle_id)
        id_matches = (key.generator_version, key.level, key.length, key.seed) == (
            puzzle.generator_version,
            puzzle.level,
            len(puzzle.steps),
            puzzle.seed,
        )
    except InvalidPuzzleId:
        id_matches = False
    if not id_matches:
        failures.append(
            Failure(FailureName.PUZZLE_ID_MISMATCH, f"{puzzle.puzzle_id} does not describe it")
        )

    if not MIN_STEPS <= len(puzzle.steps) <= MAX_STEPS:
        failures.append(
            Failure(FailureName.BAD_LENGTH, f"{len(puzzle.steps)} steps, need 1 to {MAX_STEPS}")
        )

    for index, step in enumerate(puzzle.steps):
        failures.extend(_check_step(index, step, spec, catalog))

        # ---- how the step sits in the chain ----
        if index == 0:
            if step.link_position is not None:
                failures.append(
                    Failure(FailureName.BROKEN_CHAIN_LINK, "the first step has no link", index)
                )
            continue
        previous = puzzle.steps[index - 1]
        visible = _numbers(step)
        linked = (
            step.link_position is not None
            and 0 <= step.link_position < len(visible)
            and visible[step.link_position] == previous.answer
        )
        if not linked:
            failures.append(
                Failure(
                    FailureName.BROKEN_CHAIN_LINK,
                    f"previous answer {previous.answer} is not at position "
                    f"{step.link_position} of {visible}",
                    index,
                )
            )
        if step.form == previous.form:
            failures.append(
                Failure(FailureName.REPEATED_FORM, f"{step.form} twice in a row", index)
            )

    forms = [step.form for step in puzzle.steps]
    answer_left = sum(form in ANSWER_LEFT_FORMS for form in forms)
    if spec.max_answer_left_steps is not None and answer_left > spec.max_answer_left_steps:
        failures.append(
            Failure(
                FailureName.TOO_MANY_ANSWER_LEFT,
                f"{answer_left} answer-left steps, at most {spec.max_answer_left_steps}",
            )
        )

    expected_topics = topic_ids_for(spec, forms)
    if puzzle.topic_ids != expected_topics:
        failures.append(
            Failure(FailureName.WRONG_TOPICS, f"{puzzle.topic_ids}, expected {expected_topics}")
        )
    for topic_id in puzzle.topic_ids:
        if not topic_exists(topic_id):
            failures.append(Failure(FailureName.UNKNOWN_TOPIC, f"{topic_id} is not a topic"))

    return VerificationResult(failures)
