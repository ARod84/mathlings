"""Hint templates for a blank: three tiers, written for a child.

    1. Look      which line to look at. No numbers at all.
    2. Sum       what the line must make and what is already there. Never the answer.
    3. Worked    the subtraction done, with the answer.

A line is named in words ("the top row", "the right column"), not by number.
"Row 1" would put a 1 on show in the first hint of a blank whose answer is 1,
and small answers are exactly what the first two levels have.

Tier 2 quotes the target and the sum of the known cells, so the answer must
not be either. It is never the target. It is the known sum whenever the line
is a double (6 + □ = 12), and the generator leaves such a blank alone.
`quoted_numbers` says which numbers tier 2 shows; the verifier checks the
finished text.

Templates for now; a tutor model can replace them later using SumGridStep.hint_source.
"""

from app.puzzles.core.hint_text import MINUS, written_numbers
from app.puzzles.types.sum_grid.models import Line
from app.puzzles.types.sum_grid.rules import StepView

_PLACES = {
    ("row", 2): ("top", "bottom"),
    ("row", 3): ("top", "middle", "bottom"),
    ("col", 2): ("left", "right"),
    ("col", 3): ("left", "middle", "right"),
}
_NOUN = {"row": "row", "col": "column"}


def line_name(line: Line, size: int) -> str:
    """A line in words: "the top row", "the right column"."""
    return f"the {_PLACES[(line.kind, size)][line.index]} {_NOUN[line.kind]}"


def build_hints(line: Line, size: int, view: StepView) -> list[str]:
    """The three tiers for a blank solved from `line`."""
    name = line_name(line, size)
    capital = name[0].upper() + name[1:]
    others = "The other number is" if len(view.known_cells) == 1 else "The other numbers make"
    return [
        f"Look at {name}. Only one number is missing there.",
        f"{capital} must make {view.target}. {others} {view.known}. "
        f"What do you add to {view.known} to make {view.target}?",
        f"{view.target} {MINUS} {view.known} = {view.answer}, "
        f"so the missing number is {view.answer}.",
    ]


def quoted_numbers(line: Line, size: int, view: StepView) -> set[int]:
    """Every number tier 2 shows for the blank."""
    return written_numbers(build_hints(line, size, view)[1])
