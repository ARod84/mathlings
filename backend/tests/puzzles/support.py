"""Helpers for the puzzle tests: a catalog that needs no database, and hand-built puzzles."""

from app.puzzles.types.missing_number.equations import build_equation
from app.puzzles.types.missing_number.hints import build_hints
from app.puzzles.types.missing_number.ids import make_puzzle_id
from app.puzzles.types.missing_number.levels import (
    FOCUS_CODES,
    GENERATOR_VERSION,
    LEVELS,
    TOPIC_EQUALS_SIGN,
    TOPIC_INVERSE,
    TOPIC_MISSING_NUMBER,
    TOPIC_UNKNOWN_ADD_SUB,
    topic_ids_for,
)
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog, resolve_catalog
from app.puzzles.types.missing_number.models import (
    Distractor,
    Form,
    MistakeRule,
    Puzzle,
    PuzzleStep,
)
from app.puzzles.types.missing_number.rules import distractor_value
from app.taxonomy.schemas import ErrorPatternOut, TopicSummary

TOPIC_WITHIN_1000 = "mt_yTWxkzzoOZ"

KNOWN_TOPICS = {
    TOPIC_UNKNOWN_ADD_SUB,
    TOPIC_EQUALS_SIGN,
    TOPIC_MISSING_NUMBER,
    TOPIC_INVERSE,
    TOPIC_WITHIN_1000,
}


def _summary(topic_id: str) -> TopicSummary:
    return TopicSummary(
        id=topic_id,
        name=topic_id,
        subject="Mathematics",
        domain="Addition & Subtraction",
        type="CONCEPTUAL",
        age_range_start=6,
        age_range_end=11,
        in_scope=True,
        has_research=True,
    )


def _row(position: int, pattern: str, reteach: str | None, next_move: str) -> ErrorPatternOut:
    return ErrorPatternOut(
        id=100 + position,
        position=position,
        kind="misconception",
        pattern=pattern,
        next_move=next_move,
        distractor=None,
        revealed_by="",
        reteach_prerequisite=_summary(reteach) if reteach else None,
    )


# The opening words are copied from the real taxonomy rows (pinned commit).
ERROR_PATTERN_ROWS: dict[str, list[ErrorPatternOut]] = {
    TOPIC_UNKNOWN_ADD_SUB: [
        _row(
            0,
            "Adds the two visible numbers regardless of the box's position — 8 + ? = 11 "
            "becomes 8 + 11 = 19 in the box.",
            TOPIC_EQUALS_SIGN,
            "Model on a bar: 11 is the whole, 8 a part.",
        ),
        _row(
            1,
            "Reads the answer-left form as backwards — 5 = □ − 3 solved as 5 − 3 = 2.",
            TOPIC_EQUALS_SIGN,
            "Balance model: □ − 3 must weigh the same as 5.",
        ),
        _row(2, "Solves only by slow trial-and-error.", TOPIC_INVERSE, "Prompt the inverse."),
    ],
    TOPIC_MISSING_NUMBER: [
        _row(
            0,
            "Operator view of '=' — 'the answer comes after the equals'",
            None,
            "Use a balance/bar model to re-establish '=' as 'the same as'.",
        ),
        _row(1, "Doesn't use the inverse", "mt_SrrsLiJkr3", "Model finding a missing addend."),
        _row(
            2,
            "Position confusion — treats □ − 120 = 250 as 250 − 120 (=130)",
            TOPIC_WITHIN_1000,
            "Represent with a part-whole bar: here the box is the WHOLE.",
        ),
    ],
}

STEP_BACK = {TOPIC_UNKNOWN_ADD_SUB: TOPIC_EQUALS_SIGN, TOPIC_MISSING_NUMBER: TOPIC_WITHIN_1000}


def make_catalog() -> MisconceptionCatalog:
    return resolve_catalog(lambda topic_id: ERROR_PATTERN_ROWS[topic_id])


def topic_exists(topic_id: str) -> bool:
    return topic_id in KNOWN_TOPICS


def step_back(topic_id: str) -> str | None:
    return STEP_BACK.get(topic_id)


# The right answer for each form, written out here so the tests do not lean
# on the generator's arithmetic. x and y are the visible numbers in reading order.
_ANSWERS = {
    "a+?=c": lambda x, y: y - x,
    "?+b=c": lambda x, y: y - x,
    "a-?=c": lambda x, y: x - y,
    "?-b=c": lambda x, y: x + y,
    "c=a+?": lambda x, y: x - y,
    "c=?-b": lambda x, y: x + y,
}

_RULE_ORDER = (
    MistakeRule.ADD_VISIBLE,
    MistakeRule.ANSWER_LEFT_BACKWARDS,
    MistakeRule.POSITION_CONFUSION,
    MistakeRule.PLACE_VALUE_SLIP,
    MistakeRule.OFF_BY_ONE_OVER,
    MistakeRule.OFF_BY_ONE_UNDER,
)


def make_step(
    form: Form,
    first: int,
    second: int,
    *,
    level: int = 1,
    link_position: int | None = None,
    answer: int | None = None,
    focus: MistakeRule | None = None,
) -> PuzzleStep:
    """A step with valid hints and distractors, built by hand from its two visible numbers.

    With a `focus`, the step is what a focused puzzle needs: that rule's wrong
    answer first, and the focus wording in the first hint.
    """
    spec = LEVELS[level]
    catalog = make_catalog()
    solved = _ANSWERS[form](first, second) if answer is None else answer
    step = PuzzleStep(
        equation=build_equation(form, first, second),
        answer=solved,
        form=form,
        link_position=link_position,
        distractors=[],
        hints=build_hints(form, first, second, solved, focus),
    )
    distractors: list[Distractor] = []
    used = {solved}
    for rule in sorted(_RULE_ORDER, key=lambda rule: rule is not focus):
        value = distractor_value(rule, step, spec)
        if value is None or value in used or len(distractors) == 3:
            continue
        link = catalog.link_for(rule, spec.primary_topic_id)
        distractors.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)
    for offset in spec.near_miss_offsets:
        for value in (solved + offset, solved - offset):
            if len(distractors) < 3 and 0 <= value <= spec.max_value and value not in used:
                distractors.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
                used.add(value)
    return step.model_copy(update={"distractors": distractors})


def make_puzzle(
    steps: list[PuzzleStep], *, level: int = 1, seed: int = 7, focus: MistakeRule | None = None
) -> Puzzle:
    return Puzzle(
        focus=focus,
        puzzle_id=make_puzzle_id(
            GENERATOR_VERSION, level, len(steps), seed, FOCUS_CODES[focus] if focus else None
        ),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        steps=steps,
        topic_ids=topic_ids_for(LEVELS[level], [step.form for step in steps]),
    )


def example_chain() -> Puzzle:
    """The chain from the spec:  8 + □ = 11,  □ − 3 = 5,  14 − □ = 8."""
    return make_puzzle(
        [
            make_step("a+?=c", 8, 11),
            make_step("?-b=c", 3, 5, link_position=0),
            make_step("a-?=c", 14, 8, link_position=1),
        ]
    )


def replace_step(puzzle: Puzzle, index: int, **changes) -> Puzzle:
    steps = list(puzzle.steps)
    steps[index] = steps[index].model_copy(update=changes)
    return puzzle.model_copy(update={"steps": steps})
