"""Puzzle ids and seed derivation.

A puzzle id spells out everything needed to build the puzzle again:

    mnc-1-2-3-9ix-4f1c
     |  | | |  |    '-- checksum of the rest, to catch a mistyped or made-up id
     |  | | |  '------- seed, in base 36
     |  | | '---------- number of steps
     |  | '------------ level
     |  '-------------- generator version
     '----------------- puzzle type (missing-number chain)

So nothing has to be stored: an API can take the id, regenerate and verify.
"""

import hashlib
from dataclasses import dataclass

TYPE_CODE = "mnc"
MAX_SEED = 2**63 - 1
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


class InvalidPuzzleId(ValueError):
    pass


@dataclass(frozen=True)
class PuzzleKey:
    generator_version: str
    level: int
    length: int
    seed: int


def _base36(value: int) -> str:
    if value == 0:
        return "0"
    digits = []
    while value:
        value, remainder = divmod(value, 36)
        digits.append(_ALPHABET[remainder])
    return "".join(reversed(digits))


def _checksum(body: str) -> str:
    return hashlib.sha256(body.encode("ascii")).hexdigest()[:4]


def make_puzzle_id(generator_version: str, level: int, length: int, seed: int) -> str:
    if not generator_version.isalnum():
        raise ValueError("generator_version must be letters and digits only")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")
    body = f"{TYPE_CODE}-{generator_version}-{level}-{length}-{_base36(seed)}"
    return f"{body}-{_checksum(body)}"


def parse_puzzle_id(puzzle_id: str) -> PuzzleKey:
    parts = puzzle_id.split("-")
    if len(parts) != 6 or parts[0] != TYPE_CODE:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}")
    _, version, level, length, seed, checksum = parts
    if _checksum("-".join(parts[:5])) != checksum:
        raise InvalidPuzzleId(f"checksum does not match: {puzzle_id!r}")
    try:
        return PuzzleKey(version, int(level), int(length), int(seed, 36))
    except ValueError as error:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}") from error


def derive_seed(seed: int, attempt: int) -> int:
    """The seed for a retry. Attempt 0 is the seed itself; later ones are hashed from it."""
    if attempt == 0:
        return seed
    digest = hashlib.sha256(f"{seed}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") & MAX_SEED
