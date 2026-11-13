"""The one way to get a puzzle that may be shown to a child: generate, then verify.

    generate_verified(seed, level, length, catalog=..., topic_exists=...) -> Puzzle

If the first attempt cannot be built or fails verification, the seed is
replaced by one derived from it (ids.derive_seed) and tried again, up to
MAX_ATTEMPTS. The puzzle that comes back carries the seed that actually built
it, so its puzzle_id regenerates it directly.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.puzzles.generator import GenerationError, generate
from app.puzzles.ids import InvalidPuzzleId, OutdatedPuzzleId, derive_seed, parse_puzzle_id
from app.puzzles.levels import GENERATOR_VERSION
from app.puzzles.misconceptions import MisconceptionCatalog
from app.puzzles.models import Puzzle
from app.puzzles.verifier import VerificationResult, verify

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 20


class PuzzleGenerationFailed(Exception):
    """No attempt produced a puzzle that passes verification."""


class PuzzleRejected(Exception):
    """A puzzle rebuilt from an id did not pass verification."""

    def __init__(self, puzzle_id: str, result: VerificationResult) -> None:
        names = ", ".join(sorted(name.value for name in result.names))
        super().__init__(f"{puzzle_id} failed verification: {names}")
        self.result = result


@dataclass(frozen=True)
class GenerationOutcome:
    puzzle: Puzzle
    # 0 when the first attempt passed.
    retries: int


def generate_verified_outcome(
    seed: int,
    level: int,
    length: int,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome:
    """Like generate_verified, and also says how many retries it took."""
    last_problem = "no attempt was made"
    for attempt in range(max_attempts):
        attempt_seed = derive_seed(seed, attempt)
        try:
            puzzle = generate(attempt_seed, level, length, catalog)
        except GenerationError as error:
            last_problem = str(error)
            continue
        result = verify(puzzle, catalog=catalog, topic_exists=topic_exists)
        if result.ok:
            if attempt:
                logger.info(
                    "Puzzle for seed %s, level %s, length %s took %s retries (used seed %s)",
                    seed,
                    level,
                    length,
                    attempt,
                    attempt_seed,
                )
            return GenerationOutcome(puzzle, attempt)
        last_problem = "failed verification: " + ", ".join(
            sorted(name.value for name in result.names)
        )
        logger.warning(
            "Generated puzzle %s failed verification: %s", puzzle.puzzle_id, last_problem
        )
    raise PuzzleGenerationFailed(
        f"seed {seed}, level {level}, length {length}: no valid puzzle in "
        f"{max_attempts} attempts (last: {last_problem})"
    )


def generate_verified(
    seed: int,
    level: int,
    length: int,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> Puzzle:
    """A verified puzzle for these inputs. The same inputs always give the same puzzle."""
    return generate_verified_outcome(
        seed, level, length, catalog=catalog, topic_exists=topic_exists, max_attempts=max_attempts
    ).puzzle


def _is_older(version: str) -> bool:
    """Versions are whole numbers written as text; anything else is simply unknown."""
    return (
        version.isdigit() and GENERATOR_VERSION.isdigit() and int(version) < int(GENERATOR_VERSION)
    )


def regenerate(
    puzzle_id: str, *, catalog: MisconceptionCatalog, topic_exists: Callable[[str], bool]
) -> Puzzle:
    """Rebuild the puzzle an id names, and verify it again before handing it out.

    Raises InvalidPuzzleId for an id that is malformed or names a version this
    generator does not know, OutdatedPuzzleId (a kind of InvalidPuzzleId) for an
    id from an older version, and PuzzleRejected if the rebuilt puzzle fails.
    """
    key = parse_puzzle_id(puzzle_id)
    if key.generator_version != GENERATOR_VERSION:
        message = (
            f"{puzzle_id!r} is from generator version {key.generator_version}, "
            f"this is version {GENERATOR_VERSION}"
        )
        if _is_older(key.generator_version):
            raise OutdatedPuzzleId(message)
        raise InvalidPuzzleId(message)
    puzzle = generate(key.seed, key.level, key.length, catalog)
    result = verify(puzzle, catalog=catalog, topic_exists=topic_exists)
    if not result.ok:
        raise PuzzleRejected(puzzle_id, result)
    return puzzle
