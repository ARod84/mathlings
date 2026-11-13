"""How numbers are written in a hint, and read back out of one. For every puzzle type.

A negative number is written with a real minus sign and no space (−3), and a
subtraction with spaces around the sign (0 − 3). `written_numbers` reads a
hint back the same way, so "down by 3" does not count as showing −3.

A verifier uses `written_numbers` to check that only the last hint tier
shows the answer; a generator uses it to leave alone a step whose earlier
hint would have to quote the answer.
"""

import re

MINUS = "−"
# A number as `show` writes it. "0 − 3" is 0 and 3; "−3" is −3.
_NUMBER = re.compile(rf"[{MINUS}-]?\d+")


def show(value: int) -> str:
    """A number as a child reads it: −3, not -3."""
    return f"{MINUS}{-value}" if value < 0 else str(value)


def written_numbers(text: str) -> set[int]:
    """Every number written in a hint. A minus sign right before the digits makes it negative."""
    return {int(match.replace(MINUS, "-")) for match in _NUMBER.findall(text)}
