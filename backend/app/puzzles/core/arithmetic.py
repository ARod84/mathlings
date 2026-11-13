"""Written arithmetic done wrongly in the usual ways. For mistake rules of any puzzle type.

Both work column by column on whole numbers that are not negative.
"""


def _digits(value: int, width: int) -> list[int]:
    return [int(char) for char in str(value).zfill(width)]


def subtract_without_exchange(minuend: int, subtrahend: int) -> int:
    """Each column on its own, smaller digit from larger: 380 and 245 give 145."""
    width = max(len(str(minuend)), len(str(subtrahend)))
    columns = zip(_digits(minuend, width), _digits(subtrahend, width), strict=True)
    return int("".join(str(abs(top - bottom)) for top, bottom in columns))


def add_without_carry(first: int, second: int) -> int:
    """Each column on its own, carries dropped: 275 and 148 give 313."""
    width = max(len(str(first)), len(str(second)))
    columns = zip(_digits(first, width), _digits(second, width), strict=True)
    return int("".join(str((a + b) % 10) for a, b in columns))
