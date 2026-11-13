"""What the puzzle API sends and receives for Sum Grid.

SumGridPuzzle (models.py) carries answers, mistake-rule names, error-pattern
ids and tutor notes. SumGridPublic is the cut-down shape a child's browser
gets: the grid with its blanks, the targets, and four options per blank.

A step says which line it is solved from. That is not a secret: it follows
from the visible grid, and it is what the first hint points at.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.puzzles.core import NewPuzzleBody, PublicPuzzle
from app.puzzles.types.sum_grid.levels import HINT_TIERS
from app.puzzles.types.sum_grid.models import Cell, Line


class NewSumGridRequest(NewPuzzleBody):
    """The body of POST /puzzles/sum-grid. The seed decides everything but the level."""

    level: int = Field(ge=1, le=3)


class SumGridStepPublic(BaseModel):
    index: int = Field(description="0-based position in the order the blanks are solved in.")
    cell: Cell = Field(description="Which cell this blank is: row and column, from 0.")
    line: Line = Field(
        description="The row or column in which this blank is the only unknown when its turn "
        "comes. Follows from the visible grid."
    )
    options: list[int] = Field(
        description="The answer and three wrong answers, in an order that is fixed for the puzzle."
    )
    hint_tiers: int = Field(default=HINT_TIERS, description="How many hint tiers can be asked for.")


class SumGridPublic(PublicPuzzle):
    """A grid with blanks and a target for every row and column, as the browser gets it."""

    game: Literal["sum-grid"] = Field(
        default="sum-grid",
        description="Which game the puzzle belongs to. Always sent; tells the shapes apart.",
    )
    size: int = Field(description="The grid is this many cells by this many.")
    length: int = Field(description="Number of blanks, which is the number of steps.")
    topic_ids: list[str] = Field(description="Taxonomy topics practised, primary first.")
    cells: list[list[int | None]] = Field(
        description="The grid, row by row. Null where a cell is blank. A blank stays null here "
        "after it is solved: the browser fills in what the child found."
    )
    row_targets: list[int] = Field(description="What each row must add up to, top to bottom.")
    col_targets: list[int] = Field(description="What each column must add up to, left to right.")
    steps: list[SumGridStepPublic] = Field(
        description="One per blank, in the order they can be worked out without guessing."
    )
