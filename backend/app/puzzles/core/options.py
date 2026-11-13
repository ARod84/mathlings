"""Answer options as a browser gets them."""

import hashlib
import random


def shuffled_options(puzzle_id: str, step_index: int, values: list[int]) -> list[int]:
    """The answer options in an order fixed by the puzzle id and step, so a reload matches."""
    digest = hashlib.sha256(f"{puzzle_id}:{step_index}".encode()).digest()
    options = sorted(values)
    random.Random(int.from_bytes(digest[:8], "big")).shuffle(options)
    return options
