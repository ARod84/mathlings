"""Data model for a Sum Grid puzzle. Plain data only: no generation or checking.

The grid holds the visible numbers, with None where a cell is blank. The
answers are in the steps, one per blank, in the order the blanks can be
worked out. What shared code reads (puzzle_id, generator_version, seed, level,
steps) is the InternalPuzzle protocol in app/puzzles/core/contract.py.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

PuzzleTypeName = Literal["sum_grid"]
LineKind = Literal["row", "col"]


class MistakeRule(StrEnum):
    """A known way of getting a blank wrong. See rules.py for what each one computes."""

    ADD_VISIBLE = "ADD_VISIBLE"
    FORGOT_ONE = "FORGOT_ONE"
    PLACE_VALUE_SLIP = "PLACE_VALUE_SLIP"
    CARRY_DROPPED = "CARRY_DROPPED"
    TENS_AS_ONES = "TENS_AS_ONES"
    WRONG_LINE = "WRONG_LINE"
    OFF_BY_ONE_OVER = "OFF_BY_ONE_OVER"
    OFF_BY_ONE_UNDER = "OFF_BY_ONE_UNDER"
    # Not a mistake a child makes: a filler value near the answer, used only
    # when the real rules give fewer than three distractors.
    NEAR_MISS = "NEAR_MISS"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Cell(_Frozen):
    """A place in the grid, counted from 0."""

    row: StrictInt
    col: StrictInt


class Line(_Frozen):
    """A row or a column, counted from 0."""

    kind: LineKind
    index: StrictInt


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


class SumGridStep(_Frozen):
    """One blank, and the line it is worked out from."""

    cell: Cell
    # The row or column in which this blank is the only unknown at this point.
    line: Line
    answer: StrictInt
    distractors: list[Distractor]
    # Three tiers, child-facing: where to look, the sum to do, the worked step.
    hints: list[str]
    hint_source: list[HintSource] = Field(default_factory=list)


class SumGridPuzzle(_Frozen):
    puzzle_type: PuzzleTypeName = "sum_grid"
    # Encodes generator version, level and seed; see ids.py.
    puzzle_id: str
    generator_version: str
    seed: StrictInt
    level: StrictInt
    size: StrictInt
    # Row by row. None where the cell is blank: the answers are in the steps.
    cells: list[list[StrictInt | None]]
    row_targets: list[StrictInt]
    col_targets: list[StrictInt]
    # One per blank, in an order in which each can be worked out without guessing.
    steps: list[SumGridStep]
    # Taxonomy topics this puzzle practises, primary first.
    topic_ids: list[str]
