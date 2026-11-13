"""Verified sequences for Python callers that have a catalog and no running app.

    generate_verified(seed, level, catalog=..., topic_exists=...) -> SequencePuzzle
    regenerate(puzzle_id, catalog=..., topic_exists=...) -> SequencePuzzle

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
from app.puzzles.types.sequences.misconceptions import SequenceCatalog
from app.puzzles.types.sequences.models import SequencePuzzle
from app.puzzles.types.sequences.puzzle_type import NumberSequences, SequenceParams

__all__ = [
    "MAX_ATTEMPTS",
    "GenerationOutcome",
    "PuzzleGenerationFailed",
    "PuzzleRejected",
    "generate_verified",
    "generate_verified_outcome",
    "regenerate",
]


def _sequences(catalog: SequenceCatalog, topic_exists: Callable[[str], bool]) -> NumberSequences:
    # Generating and verifying never step back through the graph; only check does.
    return NumberSequences(catalog, topic_exists=topic_exists, step_back=lambda _topic: None)


def generate_verified_outcome(
    seed: int,
    level: int,
    *,
    catalog: SequenceCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome[SequencePuzzle]:
    """Like generate_verified, and also says how many retries it took."""
    return _generate_verified_outcome(
        _sequences(catalog, topic_exists),
        seed,
        level,
        SequenceParams(),
        max_attempts=max_attempts,
    )


def generate_verified(
    seed: int,
    level: int,
    *,
    catalog: SequenceCatalog,
    topic_exists: Callable[[str], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> SequencePuzzle:
    """A verified puzzle for these inputs. The same inputs always give the same puzzle."""
    return generate_verified_outcome(
        seed, level, catalog=catalog, topic_exists=topic_exists, max_attempts=max_attempts
    ).puzzle


def regenerate(
    puzzle_id: str, *, catalog: SequenceCatalog, topic_exists: Callable[[str], bool]
) -> SequencePuzzle:
    """Rebuild the puzzle an id names, and verify it again before handing it out."""
    return _regenerate(_sequences(catalog, topic_exists), split_id(puzzle_id), puzzle_id)
