"""What the puzzle API sends and receives. The internal Puzzle model never leaves the server.

Puzzle (models.py) carries answers, mistake-rule names, error-pattern ids and
tutor notes. PuzzlePublic is the cut-down shape a child's browser gets.

Known and accepted: in a chain, step n+1 shows step n's answer as one of its
visible numbers. That is how the puzzle works, and the frontend reveals steps
one at a time. Answers here are not secrets. This is a practice game for
children, not an exam: the aim is to keep the answer out of the way until the
child has tried, not to make it impossible to find. Please do not "fix" this
by hiding later steps or encrypting anything.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.puzzles.ids import MAX_SEED
from app.puzzles.levels import HINT_TIERS, MAX_STEPS, MIN_STEPS
from app.puzzles.models import Equation, MistakeRule

MAX_ANSWER = 10_000


class NewPuzzleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=3)
    length: int = Field(default=3, ge=MIN_STEPS, le=MAX_STEPS, description="Number of steps.")
    seed: int | None = Field(
        default=None,
        ge=0,
        le=MAX_SEED,
        description="Fixes the puzzle. Leave out for a random one.",
    )
    focus: MistakeRule | None = Field(
        default=None,
        description="A mistake rule to target, as `focus` from /players/me/next gives it. "
        "ADD_VISIBLE, ANSWER_LEFT_BACKWARDS and POSITION_CONFUSION change the puzzle; any "
        "other rule name is accepted and has no effect. Never tell the child about it.",
    )


class LinkedToken(BaseModel):
    """Where a token sits in an equation: which side, and its place on that side."""

    side: Literal["left", "right"]
    index: int = Field(description="0-based position within that side's token list.")


class PuzzleStepPublic(BaseModel):
    index: int = Field(description="0-based position in the chain.")
    equation: Equation
    options: list[int] = Field(
        description="The answer and three wrong answers, in an order that is fixed for the puzzle."
    )
    hint_tiers: int = Field(default=HINT_TIERS, description="How many hint tiers can be asked for.")
    linked_token: LinkedToken | None = Field(
        default=None,
        description="The visible number that is the previous step's answer. Null for the "
        "first step. Says which one when the same value appears twice.",
    )


class PuzzlePublic(BaseModel):
    puzzle_id: str
    level: int
    length: int
    topic_ids: list[str] = Field(description="Taxonomy topics practised, primary first.")
    steps: list[PuzzleStepPublic]


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: int = Field(ge=0, le=MAX_ANSWER)


class ReteachTopic(BaseModel):
    id: str
    name: str


class DiagnosisPublic(BaseModel):
    matched_rules: list[str] = Field(
        description="Names of the known mistakes that give this answer. For analytics and "
        "development; not for showing to a child."
    )
    unrecognized: bool = Field(description="Wrong, and no known mistake explains it.")
    reteach_topic: ReteachTopic | None = Field(description="Where to step back to, if anywhere.")


class CheckResult(BaseModel):
    correct: bool
    feedback: Literal["correct", "try_again"]
    diagnosis: DiagnosisPublic
    next_step: int | None = Field(
        description="Index of the next step after a correct answer; null on the last step "
        "and after a wrong answer."
    )


class HintOut(BaseModel):
    tier: int
    text: str


class PuzzleNotFoundBody(BaseModel):
    detail: str
    puzzle_id: str


class PuzzleGoneBody(BaseModel):
    detail: str
    current_version: str
