"""The ids of missing-number chains.

    mnc-3-2-3-9ix-9bd8          no focus
    mnc-3-2-3-9ix-av-6c0e       focused on a mistake rule
     |  | | |  |  |    '-- checksum of the rest, to catch a mistyped or made-up id
     |  | | |  |  '------- focus code (levels.FOCUS_CODES); left out when there is no focus
     |  | | |  '---------- seed, in base 36
     |  | | '------------- number of steps
     |  | '--------------- level
     |  '----------------- generator version
     '-------------------- puzzle type (missing-number chain)

The type code, the version and the checksum are read by app/puzzles/core/ids.py,
the same way for every puzzle type. This module owns the fields in between:
level, length, seed and focus code. It only carries the focus code. What a
code means is levels.py's business.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.puzzles.core.ids import (
    MAX_SEED,
    InvalidPuzzleId,
    OutdatedPuzzleId,
    derive_seed,
    make_id,
    seed_field,
    split_id,
)

__all__ = [
    "MAX_SEED",
    "TYPE_CODE",
    "InvalidPuzzleId",
    "OutdatedPuzzleId",
    "PuzzleKey",
    "decode_fields",
    "derive_seed",
    "make_puzzle_id",
    "parse_puzzle_id",
]

TYPE_CODE = "mnc"
# Letters only, so a focus code can never be read as a seed or a checksum by eye.
_FOCUS_CODE = re.compile(r"[a-z]{1,4}")


@dataclass(frozen=True)
class PuzzleKey:
    generator_version: str
    level: int
    length: int
    seed: int
    # The focus code, or None for a puzzle without a focus.
    focus: str | None = None


def make_puzzle_id(
    generator_version: str, level: int, length: int, seed: int, focus: str | None = None
) -> str:
    if not generator_version.isalnum():
        raise ValueError("generator_version must be letters and digits only")
    fields = [str(level), str(length), seed_field(seed)]
    if focus is not None:
        if not _FOCUS_CODE.fullmatch(focus):
            raise ValueError("a focus code is one to four lower-case letters")
        fields.append(focus)
    return make_id(TYPE_CODE, generator_version, fields)


def decode_fields(fields: Sequence[str]) -> tuple[int, int, int, str | None]:
    """Level, length, seed and focus code from the fields of a chain id."""
    if len(fields) not in (3, 4):
        raise InvalidPuzzleId(f"not the fields of a chain id: {'-'.join(fields)!r}")
    level, length, seed, *rest = fields
    focus = rest[0] if rest else None
    if focus is not None and not _FOCUS_CODE.fullmatch(focus):
        raise InvalidPuzzleId(f"not a focus code: {focus!r}")
    try:
        return int(level), int(length), int(seed, 36), focus
    except ValueError as error:
        raise InvalidPuzzleId(f"not the fields of a chain id: {'-'.join(fields)!r}") from error


def parse_puzzle_id(puzzle_id: str) -> PuzzleKey:
    raw = split_id(puzzle_id)
    if raw.type_code != TYPE_CODE:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}")
    level, length, seed, focus = decode_fields(raw.fields)
    return PuzzleKey(raw.generator_version, level, length, seed, focus)
