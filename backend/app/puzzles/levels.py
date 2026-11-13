"""The rules of the missing-number chain that the generator and the verifier share.

Only declarations live here: number ranges, limits and topic ids. How a puzzle
is built (generator.py) and how it is checked (verifier.py) are written
separately against these.
"""

from dataclasses import dataclass

from app.puzzles.models import Form

GENERATOR_VERSION = "2"
PUZZLE_TYPE = "missing_number_chain"

MIN_STEPS = 1
MAX_STEPS = 4
DISTRACTORS_PER_STEP = 3
HINT_TIERS = 3

ANSWER_LEFT_FORMS: frozenset[Form] = frozenset({"c=a+?", "c=?-b"})

# How likely the generator is to pick each form for a step, relative to the
# others. The five forms where a known misconception can show are weighted a
# little above a-?=c, where none can: "do the sum you can see" gives the right
# answer there. They are also the forms children get wrong, so practice value
# does not suffer. Every form stays reachable. A generator preference only:
# the verifier does not know about it.
FORM_WEIGHTS: dict[Form, float] = {
    "a+?=c": 3.0,
    "?+b=c": 3.0,
    "a-?=c": 1.5,
    "?-b=c": 3.0,
    "c=a+?": 3.0,
    "c=?-b": 3.0,
}

TOPIC_UNKNOWN_ADD_SUB = "mt_3JgrHY221M"  # Unknown in Addition & Subtraction
TOPIC_EQUALS_SIGN = "mt_oIzycTBeE4"  # What the equals sign means
TOPIC_MISSING_NUMBER = "mt_XuHmIn2xje"  # Missing number problems (age 7+)
TOPIC_INVERSE = "mt_ehGS_uVSJv"  # Inverse: addition undoes subtraction


@dataclass(frozen=True)
class LevelSpec:
    level: int
    # Every number in a step, the unknown included, is between 0 and this.
    max_value: int
    # A distractor that comes from a mistake rule may be as large as this. It is
    # above max_value on purpose: a child at "up to 20" who adds the visible
    # numbers of 8 + □ = 15 really does write 23, and that is the answer worth
    # catching. The answer itself and NEAR_MISS fillers stay within max_value.
    distractor_max: int
    primary_topic_id: str
    # Tagged on every puzzle of the level.
    extra_topic_ids: tuple[str, ...]
    # Tagged only when the chain has an answer-left step.
    answer_left_topic_id: str | None
    # At most this many answer-left steps in a chain; None for no limit.
    max_answer_left_steps: int | None
    # Each step must show or ask for at least one number from 100 to 999.
    requires_three_digit: bool
    # The column-by-column slip only makes sense with multi-digit numbers.
    place_value_rule: bool
    # A NEAR_MISS filler sits exactly this far from the answer.
    near_miss_offsets: tuple[int, ...]
    # Generator preferences, not constraints: they keep a level from looking
    # like the one below it. The verifier does not know about them.
    preferred_min_whole: int = 2
    preferred_min_part: int = 1


LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(
        level=1,
        max_value=20,
        distractor_max=40,
        primary_topic_id=TOPIC_UNKNOWN_ADD_SUB,
        extra_topic_ids=(),
        answer_left_topic_id=TOPIC_EQUALS_SIGN,
        max_answer_left_steps=1,
        requires_three_digit=False,
        place_value_rule=False,
        near_miss_offsets=(2, 3, 4, 5),
        preferred_min_whole=5,
    ),
    2: LevelSpec(
        level=2,
        max_value=100,
        distractor_max=200,
        primary_topic_id=TOPIC_UNKNOWN_ADD_SUB,
        extra_topic_ids=(),
        answer_left_topic_id=TOPIC_EQUALS_SIGN,
        max_answer_left_steps=1,
        requires_three_digit=False,
        place_value_rule=False,
        near_miss_offsets=(2, 3, 10, 20),
        preferred_min_whole=21,
        preferred_min_part=2,
    ),
    3: LevelSpec(
        level=3,
        max_value=1000,
        distractor_max=2000,
        primary_topic_id=TOPIC_MISSING_NUMBER,
        extra_topic_ids=(TOPIC_INVERSE,),
        answer_left_topic_id=None,
        max_answer_left_steps=None,
        requires_three_digit=True,
        place_value_rule=True,
        near_miss_offsets=(2, 10, 20, 100),
        preferred_min_whole=100,
        preferred_min_part=11,
    ),
}


def topic_ids_for(spec: LevelSpec, forms: list[Form]) -> list[str]:
    """The topics a chain with these forms is tagged with, primary first."""
    topic_ids = [spec.primary_topic_id, *spec.extra_topic_ids]
    if spec.answer_left_topic_id and any(form in ANSWER_LEFT_FORMS for form in forms):
        topic_ids.append(spec.answer_left_topic_id)
    return topic_ids


def step_topic_ids(level: int, form: Form) -> list[str]:
    """The topics one step practises, primary first.

    Narrower than the puzzle's list: at levels 1 and 2 only an answer-left step
    (c=a+? or c=?-b) practises "what the equals sign means". A puzzle's
    topic_ids are the union of its steps' topics. Practice history is stored
    per step, so a step never counts toward a topic it does not practise.
    Migration 0003 carries a frozen copy of this mapping.
    """
    return topic_ids_for(LEVELS[level], [form])
