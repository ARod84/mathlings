"""The ids of Sum Grid puzzles.

    sg-1-3-9ix-1f0c
    |  | |  |   '-- checksum of the rest
    |  | |  '------ seed, in base 36
    |  | '--------- level
    |  '----------- generator version
    '-------------- puzzle type

The seed decides everything else (the numbers, which cells are blank and the
order they are solved in), so there is nothing more to write down. The type
code, the version and the checksum are read by app/puzzles/core/ids.py.
"""

from collections.abc import Sequence

from app.puzzles.core.ids import InvalidPuzzleId, make_id, seed_field

TYPE_CODE = "sg"


def make_sum_grid_id(generator_version: str, level: int, seed: int) -> str:
    return make_id(TYPE_CODE, generator_version, [str(level), seed_field(seed)])


def decode_fields(fields: Sequence[str]) -> tuple[int, int]:
    """Level and seed from the fields of a Sum Grid id."""
    if len(fields) != 2:
        raise InvalidPuzzleId(f"not the fields of a sum grid id: {'-'.join(fields)!r}")
    level, seed = fields
    try:
        return int(level), int(seed, 36)
    except ValueError as error:
        raise InvalidPuzzleId(f"not the fields of a sum grid id: {'-'.join(fields)!r}") from error
