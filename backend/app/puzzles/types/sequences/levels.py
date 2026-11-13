"""The rules of "Next in Line" that the generator and the verifier share.

Only declarations live here: what a sequence may look like at each level,
where the blanks may be, the topics. How a puzzle is built (generator.py) and
how it is checked (verifier.py) are written separately against these.

A sequence is one of two kinds:

    constant   the same step every time       4, 8, 12, 16, 20     9, 6, 3, 0, −3
    growing    the step grows by a fixed      1, 2, 4, 7, 11       (+1, +2, +3, +4)
               amount each time

Evidence. A child can only find the rule from what is on show, so every puzzle
keeps a run of visible terms next to each other: three for a constant step
(the step is seen twice), four for a growing step (the growth is seen twice).
"""

from dataclasses import dataclass
from typing import Literal

GENERATOR_VERSION = "1"
PUZZLE_TYPE = "number_sequence"
# The game's name in URLs, in attempt.game and in shared/game-topics.json.
GAME = "sequences"

Kind = Literal["constant", "growing"]

MIN_TERMS = 5
MAX_TERMS = 6
DISTRACTORS_PER_STEP = 3
HINT_TIERS = 3

# What a check accepts as an answer. Wider than any option, on purpose: a
# later screen may let a child type a number, and −1000 is still a number.
MIN_ANSWER = -1000
MAX_ANSWER = 10_000
# No option at any level is outside this, whatever a mistake rule gives.
OPTION_FLOOR = -100
OPTION_CEILING = 2000

# How many visible terms in a row a puzzle of each kind must have.
EVIDENCE: dict[Kind, int] = {"constant": 3, "growing": 4}

TOPIC_GROWING_PATTERNS = "mt_W3VOAuFwVw"  # Describing growing number patterns
TOPIC_SKIP_COUNTING = "mt_IzQvs7k_sE"  # Skip Counting (4s, 8s, 50s, 100s)
TOPIC_LINEAR_SEQUENCES = "mt_hBZwbst0ow"  # Linear number sequences
TOPIC_NEGATIVE_NUMBERS = "mt_vXRzMbiPff"  # Negative Numbers
TOPIC_GENERALISING = "mt_fZTn0W_iZR"  # Generalising Patterns


@dataclass(frozen=True)
class LevelSpec:
    level: int
    # Shown on the level picker. Not used by the backend.
    label: str
    # Every term of the sequence is between these, both included.
    min_value: int
    max_value: int
    # A wrong option that comes from a mistake rule may go this far. It is
    # outside the term range on purpose: the term after the right one, or a
    # sequence continued the wrong way, often lands just past it, and those
    # are the answers worth catching. NEAR_MISS fillers stay inside the term range.
    option_min: int
    option_max: int
    # The kinds a sequence may be, and the topics a step of each kind practises,
    # primary first.
    topic_ids: dict[Kind, tuple[str, ...]]
    # constant: the sizes a step may have, and whether it may go up and down.
    steps: tuple[int, ...]
    may_go_up: bool
    may_go_down: bool
    # constant: the sequence must start above zero and end below it.
    through_zero: bool
    # growing: by how much the step may grow each time. Empty where no sequence grows.
    growths: tuple[int, ...]
    max_blanks: int
    # The one blank is the last term.
    blank_at_end_only: bool
    # A NEAR_MISS filler sits exactly this far from the answer.
    near_miss_offsets: tuple[int, ...]
    # Generator preferences, not constraints. The verifier does not know about them.
    # growing: the first step is at most this, and the first term at most that.
    preferred_first_step_max: int = 6
    preferred_start_max: int = 40

    @property
    def kinds(self) -> tuple[Kind, ...]:
        return tuple(self.topic_ids)


LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(
        level=1,
        label="Counting on",
        min_value=0,
        max_value=100,
        option_min=0,
        option_max=110,
        topic_ids={"constant": (TOPIC_GROWING_PATTERNS,)},
        steps=(1, 2, 3, 4, 5, 10),
        may_go_up=True,
        may_go_down=False,
        through_zero=False,
        growths=(),
        max_blanks=1,
        blank_at_end_only=True,
        near_miss_offsets=(2, 3, 4, 5),
    ),
    2: LevelSpec(
        level=2,
        label="Skip counting",
        min_value=0,
        max_value=1000,
        option_min=0,
        option_max=1100,
        topic_ids={"constant": (TOPIC_SKIP_COUNTING, TOPIC_GROWING_PATTERNS)},
        steps=(2, 3, 4, 5, 8, 10, 25, 50, 100),
        may_go_up=True,
        may_go_down=True,
        through_zero=False,
        growths=(),
        max_blanks=2,
        blank_at_end_only=False,
        near_miss_offsets=(2, 5, 10, 20),
    ),
    3: LevelSpec(
        level=3,
        label="Tricky patterns",
        min_value=-50,
        max_value=200,
        option_min=-100,
        option_max=250,
        topic_ids={
            "constant": (TOPIC_LINEAR_SEQUENCES, TOPIC_NEGATIVE_NUMBERS),
            "growing": (TOPIC_GENERALISING, TOPIC_GROWING_PATTERNS),
        },
        steps=(2, 3, 4, 5, 6, 7, 8, 9, 10),
        may_go_up=False,
        may_go_down=True,
        through_zero=True,
        growths=(1, 2),
        max_blanks=2,
        blank_at_end_only=False,
        near_miss_offsets=(2, 3, 4, 5),
    ),
}


def step_topic_ids(level: int, kind: Kind) -> list[str]:
    """The topics one step practises, primary first. They depend on the kind of sequence.

    Every step of a puzzle has the same kind, so these are the puzzle's topics too.
    """
    return list(LEVELS[level].topic_ids[kind])


def level_topic_ids(level: int) -> list[str]:
    """Every topic a puzzle at this level can practise: each kind's, in turn, each once."""
    topic_ids: list[str] = []
    for kind_topics in LEVELS[level].topic_ids.values():
        topic_ids += [topic_id for topic_id in kind_topics if topic_id not in topic_ids]
    return topic_ids


def longest_visible_run(length: int, blanks: tuple[int, ...] | list[int]) -> int:
    """The most visible terms next to each other, in a sequence with these blanks."""
    longest = run = 0
    for position in range(length):
        run = 0 if position in blanks else run + 1
        longest = max(longest, run)
    return longest
