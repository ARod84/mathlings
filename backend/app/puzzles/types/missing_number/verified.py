"""Verified chains for Python callers that have a catalog and no running app.

    generate_verified(seed, level, length, focus=None, catalog=..., topic_exists=...) -> Puzzle
    regenerate(puzzle_id, catalog=..., topic_exists=...) -> Puzzle

The quality report, the simulator and the tests use these. The retry loop and
the version check are not here: they are the shared ones in
app/puzzles/core/verified.py, which these call with a MissingNumberChains
built from the arguments. The API goes through the same shared code by way of
PuzzleService.
"""

from collections.abc import Callable

from app.puzzles.core.ids import split_id
from app.puzzles.core.verified import (
    MAX_ATTEMPTS,
    GenerationOutcome,
    PuzzleGenerationFailed,
    PuzzleRejected,
)
from app.puzzles.core.verified import generate_verified_outcome as _generate_verified_outcome
from app.puzzles.core.verified import regenerate as _regenerate
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog
from app.puzzles.types.missing_number.models import MistakeRule, Puzzle
from app.puzzles.types.missing_number.puzzle_type import MissingNumberChains, MissingNumberParams

__all__ = [
    "MAX_ATTEMPTS",
    "GenerationOutcome",
    "PuzzleGenerationFailed",
    "PuzzleRejected",
    "generate_verified",
    "generate_verified_outcome",
    "regenerate",
]


def _chains(
    catalog: MisconceptionCatalog, topic_exists: Callable[[str], bool]
) -> MissingNumberChains:
    # Generating and verifying never step back through the graph; only check does.
    return MissingNumberChains(catalog, topic_exists=topic_exists, step_back=lambda _topic: None)


def generate_verified_outcome(
    seed: int,
    level: int,
    length: int,
    focus: MistakeRule | None = None,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome[Puzzle]:
    """Like generate_verified, and also says how many retries it took."""
    return _generate_verified_outcome(
        _chains(catalog, topic_exists),
        seed,
        level,
        MissingNumberParams(length, focus),
        max_attempts=max_attempts,
    )


def generate_verified(
    seed: int,
    level: int,
    length: int,
    focus: MistakeRule | None = None,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> Puzzle:
    """A verified puzzle for these inputs. The same inputs always give the same puzzle.

    `focus` is a mistake rule to target (see levels.FOCUS_TARGET_FORMS). A
    rule that cannot be targeted is logged and treated as no focus.
    """
    return generate_verified_outcome(
        seed,
        level,
        length,
        focus,
        catalog=catalog,
        topic_exists=topic_exists,
        max_attempts=max_attempts,
    ).puzzle


def regenerate(
    puzzle_id: str, *, catalog: MisconceptionCatalog, topic_exists: Callable[[str], bool]
) -> Puzzle:
    """Rebuild the chain an id names, and verify it again before handing it out.

    Raises InvalidPuzzleId for an id that is malformed or names a version this
    generator does not know, OutdatedPuzzleId (a kind of InvalidPuzzleId) for an
    id from an older version, and PuzzleRejected if the rebuilt puzzle fails.
    """
    return _regenerate(_chains(catalog, topic_exists), split_id(puzzle_id), puzzle_id)
