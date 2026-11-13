"""The one way to get a puzzle that may be shown to a child: generate, then verify.

    generate_verified(puzzle_type, seed, level, params) -> the type's puzzle
    regenerate(puzzle_type, raw_id) -> the puzzle an id names

The same for every puzzle type. If the first attempt cannot be built or fails
verification, the seed is replaced by one derived from it (ids.derive_seed)
and tried again, up to MAX_ATTEMPTS. The puzzle that comes back carries the
seed that actually built it, so its puzzle_id regenerates it directly.
"""

import logging
from dataclasses import dataclass

from app.puzzles.core.contract import (
    GenerationError,
    InternalPuzzle,
    PuzzleType,
    VerificationResult,
)
from app.puzzles.core.ids import InvalidPuzzleId, OutdatedPuzzleId, RawPuzzleId, derive_seed

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 20


class PuzzleGenerationFailed(Exception):
    """No attempt produced a puzzle that passes verification."""


class PuzzleRejected(Exception):
    """A puzzle rebuilt from an id did not pass verification."""

    def __init__(self, puzzle_id: str, result: VerificationResult) -> None:
        super().__init__(f"{puzzle_id} failed verification: {_names(result)}")
        self.result = result


@dataclass(frozen=True)
class GenerationOutcome[PuzzleT: InternalPuzzle]:
    puzzle: PuzzleT
    # 0 when the first attempt passed.
    retries: int


def _names(result: VerificationResult) -> str:
    return ", ".join(sorted(str(name) for name in result.names))


def generate_verified_outcome[PuzzleT: InternalPuzzle, ParamsT](
    puzzle_type: PuzzleType[PuzzleT, ParamsT],
    seed: int,
    level: int,
    params: ParamsT | None = None,
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome[PuzzleT]:
    """Like generate_verified, and also says how many retries it took."""
    params = puzzle_type.normalize_params(
        puzzle_type.default_params() if params is None else params
    )
    last_problem = "no attempt was made"
    for attempt in range(max_attempts):
        attempt_seed = derive_seed(seed, attempt)
        try:
            puzzle = puzzle_type.generate(attempt_seed, level, params)
        except GenerationError as error:
            last_problem = str(error)
            continue
        result = puzzle_type.verify(puzzle)
        if result.ok:
            if attempt:
                logger.info(
                    "Puzzle for %s, seed %s, level %s, %s took %s retries (used seed %s)",
                    puzzle_type.game,
                    seed,
                    level,
                    params,
                    attempt,
                    attempt_seed,
                )
            return GenerationOutcome(puzzle, attempt)
        last_problem = "failed verification: " + _names(result)
        logger.warning(
            "Generated puzzle %s failed verification: %s", puzzle.puzzle_id, last_problem
        )
    raise PuzzleGenerationFailed(
        f"{puzzle_type.game}, seed {seed}, level {level}, {params}: no valid puzzle in "
        f"{max_attempts} attempts (last: {last_problem})"
    )


def generate_verified[PuzzleT: InternalPuzzle, ParamsT](
    puzzle_type: PuzzleType[PuzzleT, ParamsT],
    seed: int,
    level: int,
    params: ParamsT | None = None,
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> PuzzleT:
    """A verified puzzle for these inputs. The same inputs always give the same puzzle.

    Without `params` the type's defaults are used.
    """
    return generate_verified_outcome(
        puzzle_type, seed, level, params, max_attempts=max_attempts
    ).puzzle


def _is_older(version: str, current: str) -> bool:
    """Versions are whole numbers written as text; anything else is simply unknown."""
    return version.isdigit() and current.isdigit() and int(version) < int(current)


def require_current_version(
    puzzle_type: type[PuzzleType] | PuzzleType, raw: RawPuzzleId, puzzle_id: str
) -> None:
    """Raise unless the id was made by this type's current generator version.

    OutdatedPuzzleId for an older version, InvalidPuzzleId for one this
    generator does not know. Done before the fields are read, because an
    older version may have laid them out differently.
    """
    current = puzzle_type.generator_version
    if raw.generator_version == current:
        return
    message = (
        f"{puzzle_id!r} is from generator version {raw.generator_version}, "
        f"this is version {current}"
    )
    if _is_older(raw.generator_version, current):
        raise OutdatedPuzzleId(message)
    raise InvalidPuzzleId(message)


def regenerate[PuzzleT: InternalPuzzle, ParamsT](
    puzzle_type: PuzzleType[PuzzleT, ParamsT], raw: RawPuzzleId, puzzle_id: str
) -> PuzzleT:
    """Rebuild the puzzle an id names, and verify it again before handing it out.

    `raw` is `puzzle_id` after ids.split_id, which the caller has already
    used to find the type. Raises InvalidPuzzleId for an id that is malformed
    or names a version this generator does not know, OutdatedPuzzleId (a kind
    of InvalidPuzzleId) for an id from an older version, and PuzzleRejected if
    the rebuilt puzzle fails.
    """
    if raw.type_code != puzzle_type.type_code:
        raise InvalidPuzzleId(f"{puzzle_id!r} is not a {puzzle_type.game} puzzle")
    require_current_version(puzzle_type, raw, puzzle_id)
    key = puzzle_type.decode_key(raw.fields)
    puzzle = puzzle_type.generate(key.seed, key.level, key.params)
    result = puzzle_type.verify(puzzle)
    if not result.ok:
        raise PuzzleRejected(puzzle_id, result)
    return puzzle
