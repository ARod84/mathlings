"""The rules of Sum Grid that the generator and the verifier share.

Only declarations live here: grid sizes, value ranges, blank counts, topics.
How a puzzle is built (generator.py) and how it is checked (verifier.py) are
written separately against these.

A Sum Grid is a small square grid of numbers with a target sum at the end of
every row and at the bottom of every column. Some cells are blank. The child
fills them one at a time, always the blank that can be worked out now: the
only unknown left in its row or in its column.

     3 | □ |  9        □ is the only blank in the top row: 9 − 3 = 6
     □ | 5 |  7
    ---------
     8  11             column targets

Two rules about blanks hold at every level:

- every row and every column keeps at least one visible number (so no line is
  blank from end to end)
- there is an order in which every blank can be worked out without guessing
"""

from dataclasses import dataclass

GENERATOR_VERSION = "1"
PUZZLE_TYPE = "sum_grid"
# The game's name in URLs, in attempt.game and in shared/game-topics.json.
GAME = "sum-grid"

DISTRACTORS_PER_STEP = 3
HINT_TIERS = 3

# What a check accepts as an answer. Wide enough for every option of every level.
MIN_ANSWER = 0
MAX_ANSWER = 1000

TOPIC_FLUENT_WITHIN_20 = "mt__t4afSyZRm"  # Fluent adding and subtracting within 20
TOPIC_UNKNOWN_ADD_SUB = "mt_3JgrHY221M"  # Unknown in Addition & Subtraction
TOPIC_THREE_SMALL_NUMBERS = "mt_Zx1xZM-RbX"  # Adding Three Small Numbers
TOPIC_ADD_SUBTRACT_7 = "mt_SrrsLiJkr3"  # Adding and subtracting (age 7+)
TOPIC_ADDING_WITHIN_100 = "mt_glPPG-kTQY"  # Adding within 100


@dataclass(frozen=True)
class LevelSpec:
    level: int
    # The grid is size by size.
    size: int
    # Every cell, visible or blank, is between these.
    min_value: int
    max_value: int
    # No row or column target is above this.
    max_target: int
    min_blanks: int
    max_blanks: int
    # A wrong option that comes from a mistake rule may be as large as this.
    # It is above the cell range on purpose: adding where a part is missing
    # lands past it, and that is the answer worth catching. NEAR_MISS fillers
    # stay inside the cell range. No option is below zero.
    option_max: int
    # The topics every step of the level practises, primary first.
    topic_ids: tuple[str, ...]
    # Mistake rules that only make sense at some levels.
    place_value_rule: bool
    tens_as_ones_rule: bool
    # A NEAR_MISS filler sits exactly this far from the answer.
    near_miss_offsets: tuple[int, ...]
    # A generator preference, not a constraint: how often a cell is drawn as a
    # multiple of ten, so that the TENS_AS_ONES mistake has something to act on.
    tens_share: float = 0.0


LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(
        level=1,
        size=2,
        min_value=1,
        max_value=9,
        max_target=18,
        min_blanks=2,
        max_blanks=2,
        option_max=40,
        topic_ids=(TOPIC_FLUENT_WITHIN_20, TOPIC_UNKNOWN_ADD_SUB),
        place_value_rule=False,
        tens_as_ones_rule=False,
        near_miss_offsets=(2, 3, 4),
    ),
    2: LevelSpec(
        level=2,
        size=3,
        min_value=1,
        max_value=9,
        max_target=27,
        min_blanks=3,
        max_blanks=4,
        option_max=60,
        topic_ids=(TOPIC_THREE_SMALL_NUMBERS, TOPIC_UNKNOWN_ADD_SUB),
        place_value_rule=False,
        tens_as_ones_rule=False,
        near_miss_offsets=(2, 3, 4),
    ),
    3: LevelSpec(
        level=3,
        size=3,
        min_value=10,
        max_value=60,
        max_target=100,
        min_blanks=4,
        max_blanks=5,
        option_max=200,
        topic_ids=(TOPIC_ADD_SUBTRACT_7, TOPIC_ADDING_WITHIN_100),
        place_value_rule=True,
        tens_as_ones_rule=True,
        near_miss_offsets=(2, 5, 10, 20),
        tens_share=0.4,
    ),
}


def step_topic_ids(level: int) -> list[str]:
    """The topics one step practises, primary first. The same for every step of a level."""
    return list(LEVELS[level].topic_ids)
