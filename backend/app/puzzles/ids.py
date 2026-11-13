"""Puzzle ids and seed derivation.

A puzzle id spells out everything needed to build the puzzle again:

    mnc-3-2-3-9ix-9bd8          no focus
    mnc-3-2-3-9ix-av-6c0e       focused on a mistake rule
     |  | | |  |  |    '-- checksum of the rest, to catch a mistyped or made-up id
     |  | | |  |  '------- focus code (levels.FOCUS_CODES); left out when there is no focus
     |  | | |  '---------- seed, in base 36
     |  | | '------------- number of steps
     |  | '--------------- level
     |  '----------------- generator version
     '-------------------- puzzle type (missing-number chain)

So nothing has to be stored: an API can take the id, regenerate and verify.
This module only carries the focus code. What a code means is levels.py's business.
"""

import hashlib
import re
from dataclasses import dataclass

TYPE_CODE = "mnc"
MAX_SEED = 2**63 - 1
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
# Letters only, so a focus code can never be read as a seed or a checksum by eye.
_FOCUS_CODE = re.compile(r"[a-z]{1,4}")


class InvalidPuzzleId(ValueError):
    pass


class OutdatedPuzzleId(InvalidPuzzleId):
    """A genuine id, made by an older generator version than the current one."""


@dataclass(frozen=True)
class PuzzleKey:
    generator_version: str
    level: int
    length: int
    seed: int
    # The focus code, or None for a puzzle without a focus.
    focus: str | None = None


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


def make_puzzle_id(
    generator_version: str, level: int, length: int, seed: int, focus: str | None = None
) -> str:
    if not generator_version.isalnum():
        raise ValueError("generator_version must be letters and digits only")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")
    if focus is not None and not _FOCUS_CODE.fullmatch(focus):
        raise ValueError("a focus code is one to four lower-case letters")
    body = f"{TYPE_CODE}-{generator_version}-{level}-{length}-{_base36(seed)}"
    if focus is not None:
        body += f"-{focus}"
    return f"{body}-{_checksum(body)}"


def parse_puzzle_id(puzzle_id: str) -> PuzzleKey:
    parts = puzzle_id.split("-")
    if len(parts) not in (6, 7) or parts[0] != TYPE_CODE:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}")
    *body, checksum = parts
    if _checksum("-".join(body)) != checksum:
        raise InvalidPuzzleId(f"checksum does not match: {puzzle_id!r}")
    _, version, level, length, seed, *rest = body
    focus = rest[0] if rest else None
    if focus is not None and not _FOCUS_CODE.fullmatch(focus):
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}")
    try:
        return PuzzleKey(version, int(level), int(length), int(seed, 36), focus)
    except ValueError as error:
        raise InvalidPuzzleId(f"not a puzzle id: {puzzle_id!r}") from error


def derive_seed(seed: int, attempt: int) -> int:
    """The seed for a retry. Attempt 0 is the seed itself; later ones are hashed from it."""
    if attempt == 0:
        return seed
    digest = hashlib.sha256(f"{seed}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") & MAX_SEED
