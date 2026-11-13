"""Hint templates for a blank: three tiers, written for a child.

    1. Look      where to look. No numbers.
    2. Rule      the rule, without the result. Shows the step and the term
                 before the blank, never the answer.
    3. Worked    the calculation done, with the answer.

A negative number is written with a real minus sign and no space (−3), and a
subtraction with spaces around the sign (0 − 3). `written_numbers` reads a
hint back the same way, so "down by 3" does not count as showing −3: for a
child who has not met negative numbers, saying 3 is not saying −3, and
dropping the sign is one of the mistakes this game looks for.

Tier 2 quotes numbers from the sequence, so the answer must not be one of
them. `quoted_numbers` says which numbers tier 2 shows for a blank; the
generator leaves alone any blank whose answer is among them, and the verifier
checks the finished text.

Templates for now; a tutor model can replace them later using SequenceStep.hint_source.
"""

import re
from collections.abc import Sequence

from app.puzzles.types.sequences.levels import Kind

MINUS = "−"
# A number as `show` writes it. "0 − 3" is 0 and 3; "−3" is −3.
_NUMBER = re.compile(rf"[{MINUS}-]?\d+")

LOOK = "Look at how much each number changes from one to the next."


def show(value: int) -> str:
    """A number as a child reads it: −3, not -3."""
    return f"{MINUS}{-value}" if value < 0 else str(value)


def _growing_steps(terms: Sequence[int]) -> tuple[int, int, int, int]:
    """The first three steps of a growing sequence, and how much the step grows."""
    first, second, third = (terms[i + 1] - terms[i] for i in range(3))
    return first, second, third, second - first


def written_numbers(text: str) -> set[int]:
    """Every number written in a hint. A minus sign right before the digits makes it negative."""
    return {int(match.replace(MINUS, "-")) for match in _NUMBER.findall(text)}


def quoted_numbers(terms: Sequence[int], position: int, kind: Kind) -> set[int]:
    """Every number tier 2 shows for the blank at `position`."""
    return written_numbers(build_hints(terms, position, kind)[1])


def build_hints(terms: Sequence[int], position: int, kind: Kind) -> list[str]:
    """The three tiers for the blank at `position`. `terms` is the whole sequence."""
    before, answer = terms[position - 1], terms[position]
    if kind == "growing":
        first, second, third, growth = _growing_steps(terms)
        step = answer - before
        return [
            LOOK,
            f"The jumps get bigger by {growth} each time: +{first}, +{second}, +{third}… "
            "How big is the jump into the box?",
            f"The jump into the box is +{step}. {show(before)} + {step} = {show(answer)}, "
            f"so the missing number is {show(answer)}.",
        ]
    step = abs(answer - before)
    if answer > before:
        return [
            LOOK,
            f"Each time it goes up by {step}. What is {show(before)} + {step}?",
            f"{show(before)} + {step} = {show(answer)}, so the missing number is {show(answer)}.",
        ]
    worked = (
        f"{show(before)} {MINUS} {step} = {show(answer)}, so the missing number is {show(answer)}."
    )
    if answer < 0:
        return [
            LOOK,
            f"Keep going down by {step}, past zero. The numbers below zero have a minus sign.",
            worked,
        ]
    return [
        LOOK,
        f"Each time it goes down by {step}. What is {show(before)} {MINUS} {step}?",
        worked,
    ]
