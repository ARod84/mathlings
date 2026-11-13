"""Data model for a "Next in Line" puzzle. Plain data only: no generation or checking.

A puzzle is a row of numbers with one or two of them blanked. Each blank is
one step, in reading order. What shared code reads (puzzle_id,
generator_version, seed, level, steps) is the InternalPuzzle protocol in
app/puzzles/core/contract.py.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.puzzles.types.sequences.levels import Kind

PuzzleTypeName = Literal["number_sequence"]


class MistakeRule(StrEnum):
    """A known way of getting a blank wrong. See rules.py for what each one computes."""

    STOPS_AT_ZERO = "STOPS_AT_ZERO"
    SIGN_DROPPED = "SIGN_DROPPED"
    WRONG_DIRECTION = "WRONG_DIRECTION"
    BOUNDARY_SLIP = "BOUNDARY_SLIP"
    CONSTANT_GAP = "CONSTANT_GAP"
    COUNT_BY_ONE = "COUNT_BY_ONE"
    SKIPPED_TERM = "SKIPPED_TERM"
    OFF_BY_ONE_OVER = "OFF_BY_ONE_OVER"
    OFF_BY_ONE_UNDER = "OFF_BY_ONE_UNDER"
    # Not a mistake a child makes: a filler value near the answer, used only
    # when the real rules give fewer than three distractors.
    NEAR_MISS = "NEAR_MISS"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Distractor(_Frozen):
    """A wrong answer option, and the mistake that produces it."""

    value: StrictInt
    rule: MistakeRule
    # "<topic id>#<position>": the taxonomy error pattern for this mistake, if there is one.
    error_pattern_id: str | None = None


class HintSource(_Frozen):
    """Raw taxonomy guidance for a tutor to build on. Not written for children."""

    error_pattern_id: str
    next_move: str


class SequenceStep(_Frozen):
    """One blank."""

    # Which term is blank, counted from 0.
    position: StrictInt
    answer: StrictInt
    distractors: list[Distractor]
    # Three tiers, child-facing: look at the changes, the rule, the worked step.
    hints: list[str]
    hint_source: list[HintSource] = Field(default_factory=list)


class SequencePuzzle(_Frozen):
    puzzle_type: PuzzleTypeName = "number_sequence"
    # Encodes generator version, level and seed; see ids.py.
    puzzle_id: str
    generator_version: str
    seed: StrictInt
    level: StrictInt
    kind: Kind
    # The whole sequence, blanks included. Never sent to the browser as it is.
    terms: list[StrictInt]
    # One per blank, in reading order.
    steps: list[SequenceStep]
    # Taxonomy topics this puzzle practises, primary first.
    topic_ids: list[str]

    @property
    def blanks(self) -> list[int]:
        return [step.position for step in self.steps]
