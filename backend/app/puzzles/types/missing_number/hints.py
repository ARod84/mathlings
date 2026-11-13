"""Hint templates for a step: three tiers, written for a child.

    1. Meaning   what the equals sign is saying. No numbers, unless the puzzle
                 has a focus (see below).
    2. Strategy  which calculation to try. Shows the visible numbers, not the answer.
    3. Worked    the calculation done, with the answer and a check.

A puzzle made with a focus (a mistake the child keeps making) replaces tier 1
on the steps the focus targets with a line about the idea behind that mistake.
It may quote the visible numbers, never the answer, and it does not tell the
child that they are being given extra practice.

Templates for now; a tutor model can replace them later using PuzzleStep.hint_source.
"""

from app.puzzles.types.missing_number.models import Form, MistakeRule

MINUS = "−"

MEANING = "The = sign means both sides are worth the same."
MEANING_ANSWER_LEFT = (
    "The = sign means both sides are worth the same. The answer does not have to come last."
)

FOCUS_ADD_VISIBLE = (
    "The box isn't always the answer to a sum. What number makes both sides worth the same?"
)


def focus_meaning(focus: MistakeRule, form: Form, first: int, second: int) -> str | None:
    """The tier 1 line for a step the focus targets, or None if it does not target this form.

    `first` and `second` are the visible numbers in reading order.
    """
    if focus is MistakeRule.ADD_VISIBLE and form in ("a+?=c", "?+b=c", "c=a+?"):
        return FOCUS_ADD_VISIBLE
    if focus is MistakeRule.ANSWER_LEFT_BACKWARDS and form == "c=?-b":
        # Reads  first = □ − second.
        return (
            "The answer can be on the left! Read it as: what number, "
            f"take away {second}, leaves {first}?"
        )
    if focus is MistakeRule.POSITION_CONFUSION and form == "?-b=c":
        # Reads  □ − first = second.
        return (
            "The box comes first here. What number do you start with, "
            f"so that taking away {first} leaves {second}?"
        )
    return None


def build_hints(
    form: Form, first: int, second: int, answer: int, focus: MistakeRule | None = None
) -> list[str]:
    """`first` and `second` are the visible numbers in reading order."""
    hints = _plain_hints(form, first, second, answer)
    meaning = focus_meaning(focus, form, first, second) if focus is not None else None
    if meaning is not None:
        hints[0] = meaning
    return hints


def _plain_hints(form: Form, first: int, second: int, answer: int) -> list[str]:
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
