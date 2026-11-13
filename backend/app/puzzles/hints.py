"""Hint templates for a step: three tiers, written for a child.

    1. Meaning   what the equals sign is saying. No numbers.
    2. Strategy  which calculation to try. Shows the visible numbers, not the answer.
    3. Worked    the calculation done, with the answer and a check.

Templates for now; a tutor model can replace them later using PuzzleStep.hint_source.
"""

from app.puzzles.models import Form

MINUS = "−"

MEANING = "The = sign means both sides are worth the same."
MEANING_ANSWER_LEFT = (
    "The = sign means both sides are worth the same. The answer does not have to come last."
)


def build_hints(form: Form, first: int, second: int, answer: int) -> list[str]:
    """`first` and `second` are the visible numbers in reading order."""
    x, y, u = first, second, answer
    if form == "a+?=c":
        return [
            MEANING,
            f"What number do you add to {x} to make {y}? Try {y} {MINUS} {x}.",
            f"{y} {MINUS} {x} = {u}, so the missing number is {u}. Check: {x} + {u} = {y}.",
        ]
    if form == "?+b=c":
        return [
            MEANING,
            f"What number plus {x} makes {y}? Try {y} {MINUS} {x}.",
            f"{y} {MINUS} {x} = {u}, so the missing number is {u}. Check: {u} + {x} = {y}.",
        ]
    if form == "a-?=c":
        return [
            MEANING,
            f"What do you take away from {x} to leave {y}? Try {x} {MINUS} {y}.",
            f"{x} {MINUS} {y} = {u}, so the missing number is {u}. Check: {x} {MINUS} {u} = {y}.",
        ]
    if form == "?-b=c":
        return [
            MEANING,
            f"A number take away {x} leaves {y}. Put them back together: try {y} + {x}.",
            f"{y} + {x} = {u}, so the missing number is {u}. Check: {u} {MINUS} {x} = {y}.",
        ]
    if form == "c=a+?":
        return [
            MEANING_ANSWER_LEFT,
            f"{x} is the same as {y} plus what? Try {x} {MINUS} {y}.",
            f"{x} {MINUS} {y} = {u}, so the missing number is {u}. Check: {y} + {u} = {x}.",
        ]
    return [
        MEANING_ANSWER_LEFT,
        f"{x} is what is left when you take {y} from a number. "
        f"Put them back together: try {x} + {y}.",
        f"{x} + {y} = {u}, so the missing number is {u}. Check: {u} {MINUS} {y} = {x}.",
    ]
