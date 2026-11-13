"""Checks a "Next in Line" puzzle without trusting how it was made.

    verify(puzzle, catalog=..., topic_exists=...) -> VerificationResult

A puzzle does not reach a child unless `result.ok`. This module never imports
the generator. It reads the visible terms only, works out for itself which
rules they fit, and checks the stored answers against that. So a puzzle
written by hand, by another program or by a model can be checked the same way.

WHAT "EXACTLY ONE ANSWER" MEANS HERE

Any finite row of numbers can be continued in infinitely many ways, so "one
answer" only means something inside a declared set of rules. This is the set:

    constant   the same whole-number step every time, not zero
               t(i) = a + i × d
    growing    the step changes by the same whole number every time, not zero
               (a constant second difference): 1, 2, 4, 7, 11
    ratio      every term is 2 times the one before, or 3 times
               (a child who sees 2, 4 may well think "doubling")

`fitting_rules` finds every rule of these families that passes through all
the visible terms. With numbers on show at given places there is at most one
constant rule, at most one growing rule and at most one of each ratio, so the
list can be written out in full. A family that the visible terms do not pin
down (two visible terms fit infinitely many growing rules) is reported as
open, which is ambiguous by definition.

A puzzle passes when:

    1. at least one fitting rule is of the kind the puzzle says it is, and
       that kind is one the level intends
    2. no family is open, and every fitting rule gives the same number for
       every blank
    3. that number is the stored answer

and, separately, when it shows enough: a run of visible terms next to each
other (levels.EVIDENCE). The second is not implied by the first. 1, 2, □, 7, □
is a row that only one rule of the set fits, yet a child cannot see the
growth twice in it.

It does share the declared rules of the puzzle type (levels.py), the mistake
rules (rules.py) and the way a number in a hint is read back
(hints.written_numbers): a distractor has to equal what its rule gives, and
there is one definition of each rule.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from itertools import pairwise
from typing import Literal

from app.puzzles.types.sequences.hints import written_numbers
from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import (
    DISTRACTORS_PER_STEP,
    EVIDENCE,
    GENERATOR_VERSION,
    HINT_TIERS,
    LEVELS,
    MAX_TERMS,
    MIN_TERMS,
    PUZZLE_TYPE,
    LevelSpec,
    longest_visible_run,
    step_topic_ids,
)
from app.puzzles.types.sequences.misconceptions import SequenceCatalog
from app.puzzles.types.sequences.models import MistakeRule, SequencePuzzle, SequenceStep
from app.puzzles.types.sequences.rules import distractor_value, in_option_range, is_near_miss

Family = Literal["constant", "growing", "ratio"]
RATIOS = (2, 3)


class FailureName(StrEnum):
    UNSUPPORTED_PUZZLE = "unsupported_puzzle"
    PUZZLE_ID_MISMATCH = "puzzle_id_mismatch"
    BAD_LENGTH = "bad_length"
    BAD_BLANKS = "bad_blanks"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    NOT_ENOUGH_EVIDENCE = "not_enough_evidence"
    NO_INTENDED_RULE = "no_intended_rule"
    AMBIGUOUS = "ambiguous"
    WRONG_ANSWER = "wrong_answer"
    BAD_STEP = "bad_step"
    BAD_DIRECTION = "bad_direction"
    NOT_THROUGH_ZERO = "not_through_zero"
    NO_BLANK_BELOW_ZERO = "no_blank_below_zero"
    BAD_GROWTH = "bad_growth"
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


# ---- which rules fit a row of visible terms ----


@dataclass(frozen=True)
class FittedRule:
    """One rule of the declared set that passes through every visible term."""

    family: Family
    # For people: "+4", "−3", "step grows by 1", "×2".
    name: str
    # The whole sequence under this rule, blanks filled in.
    terms: tuple[int, ...]


@dataclass(frozen=True)
class Fit:
    rules: list[FittedRule]
    # Families the visible terms do not pin down: more than one of their rules fits.
    open_families: list[Family]


def _whole(values: list[Fraction]) -> tuple[int, ...] | None:
    if any(value.denominator != 1 for value in values):
        return None
    return tuple(int(value) for value in values)


def _fit_constant(points: list[tuple[int, int]], length: int) -> FittedRule | None:
    (p0, v0), (p1, v1) = points[0], points[1]
    step = Fraction(v1 - v0, p1 - p0)
    if step == 0 or step.denominator != 1:
        return None
    terms = _whole([v0 + step * (index - p0) for index in range(length)])
    if terms is None or any(terms[p] != v for p, v in points):
        return None
    sign = "+" if step > 0 else "−"
    return FittedRule("constant", f"{sign}{abs(int(step))}", terms)


def _fit_growing(points: list[tuple[int, int]], length: int) -> FittedRule | None:
    # The one curve t(i) = A·i² + B·i + C through the first three visible terms.
    (p0, v0), (p1, v1), (p2, v2) = points[0], points[1], points[2]
    first = Fraction(v1 - v0, p1 - p0)
    second = Fraction(v2 - v1, p2 - p1)
    a = (second - first) / (p2 - p0)
    b = first - a * (p0 + p1)
    c = v0 - a * p0 * p0 - b * p0
    growth = 2 * a  # how much the step changes each time
    if growth == 0 or growth.denominator != 1:
        return None
    terms = _whole([a * index * index + b * index + c for index in range(length)])
    if terms is None or any(terms[p] != v for p, v in points):
        return None
    verb = "grows" if growth > 0 else "shrinks"
    return FittedRule("growing", f"step {verb} by {abs(int(growth))}", terms)


def _fit_ratio(points: list[tuple[int, int]], length: int, ratio: int) -> FittedRule | None:
    p0, v0 = points[0]
    start = Fraction(v0, ratio**p0)
    terms = _whole([start * ratio**index for index in range(length)])
    if terms is None or terms[0] == 0 or any(terms[p] != v for p, v in points):
        return None
    return FittedRule("ratio", f"×{ratio}", terms)


def fitting_rules(visible: Mapping[int, int], length: int) -> Fit:
    """Every rule of the declared set that fits the visible terms of a sequence.

    `visible` maps a position (from 0) to the number shown there; `length` is
    the number of terms, blanks included.
    """
    points = sorted(visible.items())
    rules: list[FittedRule] = []
    open_families: list[Family] = []

    # A family is pinned down once it has as many visible terms as it has
    # unknowns: two for a constant step or a ratio, three for a growing step.
    if len(points) < 2:
        open_families += ["constant", "ratio"]
    else:
        rules += [rule for rule in [_fit_constant(points, length)] if rule]
        rules += [rule for ratio in RATIOS if (rule := _fit_ratio(points, length, ratio))]
    if len(points) < 3:
        open_families.append("growing")
    else:
        rules += [rule for rule in [_fit_growing(points, length)] if rule]
    return Fit(rules, open_families)


# ---- the puzzle ----


def _check_step(
    index: int,
    step: SequenceStep,
    puzzle: SequencePuzzle,
    terms: tuple[int, ...],
    spec: LevelSpec,
    catalog: SequenceCatalog,
) -> list[Failure]:
    """The options and hints of one blank. `terms` is the sequence the verifier worked out."""
    failures: list[Failure] = []

    def fail(name: FailureName, detail: str) -> None:
        failures.append(Failure(name, detail, index))

    answer = terms[step.position]
    primary_topic_id = spec.topic_ids[puzzle.kind][0]

    # ---- distractors ----
    if len(step.distractors) != DISTRACTORS_PER_STEP:
        fail(FailureName.DISTRACTOR_COUNT, f"{len(step.distractors)} distractors, need 3")
    values = [distractor.value for distractor in step.distractors]
    if len(set(values)) != len(values):
        fail(FailureName.DUPLICATE_DISTRACTOR, f"{values}")
    for distractor in step.distractors:
        if distractor.value == answer:
            fail(FailureName.DISTRACTOR_EQUALS_ANSWER, f"{distractor.value} is the answer")
            continue
        if distractor.rule is MistakeRule.NEAR_MISS:
            if not is_near_miss(distractor.value, answer, spec):
                fail(
                    FailureName.DISTRACTOR_OUT_OF_RANGE
                    if not spec.min_value <= distractor.value <= spec.max_value
                    else FailureName.DISTRACTOR_RULE_MISMATCH,
                    f"{distractor.value} is not a near miss of {answer}",
                )
            expected_pattern = None
        else:
            if not in_option_range(distractor.value, spec):
                fail(FailureName.DISTRACTOR_OUT_OF_RANGE, f"{distractor.value}")
            expected = distractor_value(distractor.rule, terms, step.position, puzzle.kind, spec)
            if expected != distractor.value:
                fail(
                    FailureName.DISTRACTOR_RULE_MISMATCH,
                    f"{distractor.rule.value} gives {expected}, not {distractor.value}",
                )
            link = catalog.link_for(distractor.rule, primary_topic_id)
            expected_pattern = link.error_pattern_id if link else None
        if distractor.error_pattern_id != expected_pattern:
            fail(
                FailureName.DISTRACTOR_PATTERN_MISMATCH,
                f"{distractor.rule.value} carries {distractor.error_pattern_id}, "
                f"expected {expected_pattern}",
            )

    # ---- hints ----
    if len(step.hints) != HINT_TIERS:
        fail(FailureName.HINT_COUNT, f"{len(step.hints)} hints, need {HINT_TIERS}")
    else:
        for tier, hint in enumerate(step.hints[:-1], start=1):
            if answer in written_numbers(hint):
                fail(FailureName.HINT_REVEALS_ANSWER, f"tier {tier} shows {answer}")
        if answer not in written_numbers(step.hints[-1]):
            fail(FailureName.HINT_MISSING_ANSWER, "the last hint must show the answer")
    return failures


def _check_level_rules(rule: FittedRule, blanks: list[int], spec: LevelSpec) -> list[Failure]:
    """Is the rule the verifier found one this level is meant to use?"""
    failures: list[Failure] = []
    terms = rule.terms
    for value in terms:
        if not spec.min_value <= value <= spec.max_value:
            failures.append(
                Failure(
                    FailureName.VALUE_OUT_OF_RANGE,
                    f"{value} is outside {spec.min_value} to {spec.max_value}",
                )
            )
    first_step = terms[1] - terms[0]
    if rule.family == "constant":
        if abs(first_step) not in spec.steps:
            failures.append(Failure(FailureName.BAD_STEP, f"a step of {abs(first_step)}"))
        allowed = spec.may_go_up if first_step > 0 else spec.may_go_down
        if not allowed:
            failures.append(Failure(FailureName.BAD_DIRECTION, "up" if first_step > 0 else "down"))
        if spec.through_zero:
            if not (terms[0] > 0 > terms[-1]):
                failures.append(
                    Failure(FailureName.NOT_THROUGH_ZERO, f"{terms[0]} down to {terms[-1]}")
                )
            if not any(terms[position] < 0 for position in blanks):
                failures.append(
                    Failure(FailureName.NO_BLANK_BELOW_ZERO, "every blank is zero or more")
                )
    else:
        growth = (terms[2] - terms[1]) - first_step
        if growth not in spec.growths or first_step < 1:
            failures.append(
                Failure(FailureName.BAD_GROWTH, f"first step {first_step}, growing by {growth}")
            )
    return failures


def verify(
    puzzle: SequencePuzzle,
    *,
    catalog: SequenceCatalog,
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
        or puzzle.kind not in spec.kinds
    ):
        return VerificationResult(
            [
                Failure(
                    FailureName.UNSUPPORTED_PUZZLE,
                    f"type {puzzle.puzzle_type}, version {puzzle.generator_version}, "
                    f"level {puzzle.level}, kind {puzzle.kind}",
                )
            ]
        )

    try:
        expected_id = make_sequence_id(puzzle.generator_version, puzzle.level, puzzle.seed)
    except ValueError:
        expected_id = None
    if puzzle.puzzle_id != expected_id:
        failures.append(
            Failure(FailureName.PUZZLE_ID_MISMATCH, f"{puzzle.puzzle_id} does not describe it")
        )

    length = len(puzzle.terms)
    if not MIN_TERMS <= length <= MAX_TERMS:
        failures.append(
            Failure(FailureName.BAD_LENGTH, f"{length} terms, need {MIN_TERMS} to {MAX_TERMS}")
        )

    # ---- where the blanks are ----
    blanks = puzzle.blanks
    in_order = all(a < b for a, b in pairwise(blanks))
    if not blanks or not in_order or any(not 1 <= position < length for position in blanks):
        # Nothing below makes sense without knowing which terms are visible.
        failures.append(Failure(FailureName.BAD_BLANKS, f"blanks at {blanks} in a row of {length}"))
        return VerificationResult(failures)
    if len(blanks) > spec.max_blanks or (spec.blank_at_end_only and blanks != [length - 1]):
        failures.append(Failure(FailureName.BAD_BLANKS, f"blanks at {blanks}"))
    if longest_visible_run(length, blanks) < EVIDENCE[puzzle.kind]:
        failures.append(
            Failure(
                FailureName.NOT_ENOUGH_EVIDENCE,
                f"a {puzzle.kind} sequence needs {EVIDENCE[puzzle.kind]} visible terms in a "
                f"row; blanks at {blanks} leave {longest_visible_run(length, blanks)}",
            )
        )

    # ---- which rules fit what is on show, and do they agree ----
    visible = {
        position: value for position, value in enumerate(puzzle.terms) if position not in blanks
    }
    fit = fitting_rules(visible, length)
    intended = next((rule for rule in fit.rules if rule.family == puzzle.kind), None)
    if intended is None:
        failures.append(
            Failure(
                FailureName.NO_INTENDED_RULE,
                f"no {puzzle.kind} rule fits; fitting: {[rule.name for rule in fit.rules]}",
            )
        )
    disagree = [
        position for position in blanks if len({rule.terms[position] for rule in fit.rules}) > 1
    ]
    if fit.open_families or disagree:
        readings = ", ".join(
            f"{rule.name} gives {[rule.terms[position] for position in blanks]}"
            for rule in fit.rules
        )
        open_note = (
            f"; not enough terms to pin down: {', '.join(fit.open_families)}"
            if fit.open_families
            else ""
        )
        failures.append(Failure(FailureName.AMBIGUOUS, f"{readings}{open_note}"))

    if intended is not None:
        failures += _check_level_rules(intended, blanks, spec)
    else:
        for value in visible.values():
            if not spec.min_value <= value <= spec.max_value:
                failures.append(Failure(FailureName.VALUE_OUT_OF_RANGE, f"{value}"))

    # From here on the sequence is the one the verifier worked out, where it
    # found one. The stored terms at the blanks are only compared with it.
    terms = intended.terms if intended is not None else tuple(puzzle.terms)
    for index, step in enumerate(puzzle.steps):
        if step.answer != terms[step.position] or puzzle.terms[step.position] != step.answer:
            failures.append(
                Failure(
                    FailureName.WRONG_ANSWER,
                    f"stored {step.answer} (term {puzzle.terms[step.position]}), "
                    f"the rule gives {terms[step.position]}",
                    index,
                )
            )
        failures += _check_step(index, step, puzzle, terms, spec, catalog)

    expected_topics = step_topic_ids(puzzle.level, puzzle.kind)
    if puzzle.topic_ids != expected_topics:
        failures.append(
            Failure(FailureName.WRONG_TOPICS, f"{puzzle.topic_ids}, expected {expected_topics}")
        )
    for topic_id in puzzle.topic_ids:
        if not topic_exists(topic_id):
            failures.append(Failure(FailureName.UNKNOWN_TOPIC, f"{topic_id} is not a topic"))

    return VerificationResult(failures)
