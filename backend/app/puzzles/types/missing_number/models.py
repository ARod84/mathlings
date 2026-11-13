"""Data model for a chain. Plain data only: no generation, checking or database code.

A puzzle is a list of steps. What shared code reads from it (puzzle_id,
generator_version, seed, level, steps) is the InternalPuzzle protocol in
app/puzzles/core/contract.py; everything else here is the chain's own.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

Form = Literal["a+?=c", "?+b=c", "a-?=c", "?-b=c", "c=a+?", "c=?-b"]
PuzzleType = Literal["missing_number_chain"]


class MistakeRule(StrEnum):
    """A known way of getting a step wrong. See rules.py for what each one computes."""

    ADD_VISIBLE = "ADD_VISIBLE"
    ANSWER_LEFT_BACKWARDS = "ANSWER_LEFT_BACKWARDS"
    POSITION_CONFUSION = "POSITION_CONFUSION"
    PLACE_VALUE_SLIP = "PLACE_VALUE_SLIP"
    OFF_BY_ONE_OVER = "OFF_BY_ONE_OVER"
    OFF_BY_ONE_UNDER = "OFF_BY_ONE_UNDER"
    # Not a mistake a child makes: a filler value near the answer, used only
    # when the real rules give fewer than three distractors.
    NEAR_MISS = "NEAR_MISS"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NumberToken(_Frozen):
    kind: Literal["number"] = "number"
    value: StrictInt


class OperatorToken(_Frozen):
    kind: Literal["operator"] = "operator"
    symbol: Literal["+", "-"]


class UnknownToken(_Frozen):
    """The box the child fills in."""

    kind: Literal["unknown"] = "unknown"


Token = Annotated[NumberToken | OperatorToken | UnknownToken, Field(discriminator="kind")]


class Equation(_Frozen):
    """`left = right`, as tokens, so a frontend can draw the box as a real box."""

    left: list[Token]
    right: list[Token]


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


class PuzzleStep(_Frozen):
    equation: Equation
    answer: StrictInt
    form: Form
    # Where the previous step's answer appears among this step's visible
    # numbers, counted in reading order from 0. None for the first step.
    link_position: int | None = None
    distractors: list[Distractor]
    # Three tiers, child-facing: meaning, strategy, worked step.
    hints: list[str]
    hint_source: list[HintSource] = Field(default_factory=list)


class Puzzle(_Frozen):
    puzzle_type: PuzzleType = "missing_number_chain"
    # Encodes generator version, level, length and seed; see ids.py.
    puzzle_id: str
    generator_version: str
    seed: StrictInt
    level: StrictInt
    steps: list[PuzzleStep]
    # Taxonomy topics this puzzle practises, primary first.
    topic_ids: list[str]
    # The mistake this puzzle was built to target, if any (levels.FOCUS_TARGET_FORMS).
    # Never sent to the browser.
    focus: MistakeRule | None = None
