"""Puzzle ids, for every puzzle type, and seed derivation.

A puzzle id spells out everything needed to build the puzzle again:

    mnc-3-2-3-9ix-9bd8
     |  | '-----' '-- checksum of the rest, to catch a mistyped or made-up id
     |  |    '------- fields: what the type needs (for a chain: level, length, seed, focus)
     |  '------------ generator version
     '--------------- type code: which puzzle type made it (registry.py)

So nothing has to be stored: an API can take the id, regenerate and verify.
This module reads the type code, the version and the checksum. What the
fields mean is the type's business (PuzzleType.decode_key).
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

MAX_SEED = 2**63 - 1
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


class InvalidPuzzleId(ValueError):
    pass


class OutdatedPuzzleId(InvalidPuzzleId):
    """A genuine id, made by an older generator version than the current one."""


@dataclass(frozen=True)
class RawPuzzleId:
    """An id whose checksum holds, split up but not yet understood."""

    type_code: str
    generator_version: str
    fields: tuple[str, ...]


def base36(value: int) -> str:
    if value == 0:
        return "0"
    digits = []
    while value:
        value, remainder = divmod(value, 36)
        digits.append(_ALPHABET[remainder])
    return "".join(reversed(digits))


def _checksum(body: str) -> str:
    return hashlib.sha256(body.encode("ascii")).hexdigest()[:4]


def make_id(type_code: str, generator_version: str, fields: Sequence[str]) -> str:
    if not generator_version.isalnum():
        raise ValueError("generator_version must be letters and digits only")
    if not fields:
        raise ValueError("an id needs at least one field")
    body = "-".join((type_code, generator_version, *fields))
    return f"{body}-{_checksum(body)}"


def split_id(puzzle_id: str) -> RawPuzzleId:
    """Check the checksum and split the id. Says nothing about whether the type exists."""
    parts = puzzle_id.split("-")
    # Type code, version, at least one field, checksum.
    if len(parts) < 4:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}")
    *body, checksum = parts
    try:
        matches = _checksum("-".join(body)) == checksum
    except UnicodeEncodeError:
        matches = False
    if not matches:
        raise InvalidPuzzleId(f"checksum does not match: {puzzle_id!r}")
    type_code, version, *fields = body
    return RawPuzzleId(type_code, version, tuple(fields))


def seed_field(seed: int) -> str:
    """A seed as an id field: base 36."""
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")
    return base36(seed)


def derive_seed(seed: int, attempt: int) -> int:
    """The seed for a retry. Attempt 0 is the seed itself; later ones are hashed from it."""
    if attempt == 0:
        return seed
    digest = hashlib.sha256(f"{seed}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") & MAX_SEED
