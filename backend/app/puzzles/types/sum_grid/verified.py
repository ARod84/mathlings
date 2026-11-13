"""Verified Sum Grids for Python callers that have a catalog and no running app.

    generate_verified(seed, level, catalog=..., topic_exists=...) -> SumGridPuzzle
    regenerate(puzzle_id, catalog=..., topic_exists=...) -> SumGridPuzzle

The quality report and the tests use these. The retry loop and the version
check are the shared ones in app/puzzles/core/verified.py.
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
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog
from app.puzzles.types.sum_grid.models import SumGridPuzzle
from app.puzzles.types.sum_grid.puzzle_type import SumGrid, SumGridParams

__all__ = [
    "MAX_ATTEMPTS",
    "GenerationOutcome",
    "PuzzleGenerationFailed",
    "PuzzleRejected",
    "generate_verified",
    "generate_verified_outcome",
    "regenerate",
]


def _sum_grids(catalog: SumGridCatalog, topic_exists: Callable[[str], bool]) -> SumGrid:
    # Generating and verifying never step back through the graph; only check does.
    return SumGrid(catalog, topic_exists=topic_exists, step_back=lambda _topic: None)


def generate_verified_outcome(
    seed: int,
    level: int,
    *,
    catalog: SumGridCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome[SumGridPuzzle]:
    """Like generate_verified, and also says how many retries it took."""
    return _generate_verified_outcome(
        _sum_grids(catalog, topic_exists),
        seed,
        level,
        SumGridParams(),
        max_attempts=max_attempts,
    )


def generate_verified(
    seed: int,
    level: int,
    *,
    catalog: SumGridCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> SumGridPuzzle:
    """A verified puzzle for these inputs. The same inputs always give the same puzzle."""
    return generate_verified_outcome(
        seed, level, catalog=catalog, topic_exists=topic_exists, max_attempts=max_attempts
    ).puzzle


def regenerate(
    puzzle_id: str, *, catalog: SumGridCatalog, topic_exists: Callable[[str], bool]
) -> SumGridPuzzle:
    """Rebuild the puzzle an id names, and verify it again before handing it out."""
    return _regenerate(_sum_grids(catalog, topic_exists), split_id(puzzle_id), puzzle_id)
