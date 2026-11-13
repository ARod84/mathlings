"""What the puzzle API sends and receives for "Next in Line".

SequencePuzzle (models.py) carries answers, mistake-rule names, error-pattern
ids and tutor notes. SequencePublic is the cut-down shape a child's browser
gets: the row with its blanks, and four options per blank.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.puzzles.core import NewPuzzleBody, PublicPuzzle
from app.puzzles.types.sequences.levels import HINT_TIERS


class NewSequenceRequest(NewPuzzleBody):
    """The body of POST /puzzles/sequences. The seed decides everything but the level."""

    level: int = Field(ge=1, le=3)


class SequenceStepPublic(BaseModel):
    index: int = Field(description="0-based position among the blanks, in reading order.")
    position: int = Field(description="Which term of the row this blank is, from 0.")
    options: list[int] = Field(
        description="The answer and three wrong answers, in an order that is fixed for the "
        "puzzle. May be negative."
    )
    hint_tiers: int = Field(default=HINT_TIERS, description="How many hint tiers can be asked for.")


class SequencePublic(PublicPuzzle):
    """A row of numbers with one or two blanks, as the browser gets it."""

    game: Literal["sequences"] = Field(
        default="sequences",
        description="Which game the puzzle belongs to. Always sent; tells the shapes apart.",
    )
    length: int = Field(description="Number of blanks, which is the number of steps.")
    topic_ids: list[str] = Field(description="Taxonomy topics practised, primary first.")
    terms: list[int | None] = Field(
        description="The row, in order. Null where a term is blank. A blank stays null here "
        "after it is solved: the browser fills in what the child found."
    )
    steps: list[SequenceStepPublic]
