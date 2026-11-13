"""What the puzzle API sends and receives for a chain. The internal Puzzle never leaves the server.

Puzzle (models.py) carries answers, mistake-rule names, error-pattern ids and
tutor notes. PuzzlePublic is the cut-down shape a child's browser gets. The
shapes every game shares (check, hint, errors) are in app/puzzles/core/schemas.py.

Known and accepted: in a chain, step n+1 shows step n's answer as one of its
visible numbers. That is how the puzzle works, and the frontend reveals steps
one at a time. Answers here are not secrets. This is a practice game for
children, not an exam: the aim is to keep the answer out of the way until the
child has tried, not to make it impossible to find. Please do not "fix" this
by hiding later steps or encrypting anything.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.puzzles.core import NewPuzzleBody, PublicPuzzle
from app.puzzles.types.missing_number.levels import (
    DEFAULT_LENGTH,
    HINT_TIERS,
    MAX_STEPS,
    MIN_STEPS,
)
from app.puzzles.types.missing_number.models import Equation, MistakeRule


class NewPuzzleRequest(NewPuzzleBody):
    """The body of POST /puzzles/missing-number."""

    level: int = Field(ge=1, le=3)
    length: int = Field(
        default=DEFAULT_LENGTH, ge=MIN_STEPS, le=MAX_STEPS, description="Number of steps."
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


class PuzzlePublic(PublicPuzzle):
    """A missing-number chain, as the browser gets it."""

    game: Literal["missing-number"] = Field(
        default="missing-number",
        description="Which game the puzzle belongs to. Always sent; tells the shapes apart.",
    )
    length: int
    topic_ids: list[str] = Field(description="Taxonomy topics practised, primary first.")
    steps: list[PuzzleStepPublic]
