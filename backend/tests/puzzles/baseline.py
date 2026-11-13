"""The fingerprint of what the generator produces with no focus, seed by seed.

tests/snapshots/generator_v2_focus_none.json was written by this module from
generator version 2, before the generator learned about focus. The test that
reads it proves that a puzzle made without a focus is, apart from its id and
version stamp, exactly the puzzle version 2 made from the same seed.

    uv run python -m tests.puzzles.baseline     # rewrite the file (deliberate changes only)
"""

import hashlib
import json
from pathlib import Path

from app.puzzles.models import Puzzle
from app.puzzles.verified import generate_verified
from tests.puzzles.support import KNOWN_TOPICS, make_catalog

BASELINE_FILE = Path(__file__).parent.parent / "snapshots" / "generator_v2_focus_none.json"
SEEDS = 2000
# The id spells out the version, and both change when the version is bumped.
# `focus` did not exist in version 2; without a focus it is None.
NOT_COMPARED = ("puzzle_id", "generator_version", "focus")


def inputs(seed: int) -> tuple[int, int]:
    """The level and chain length used for a seed: every combination, in turn."""
    return seed % 3 + 1, seed % 4 + 1


def fingerprint(puzzle: Puzzle) -> str:
    content = puzzle.model_dump(mode="json")
    for key in NOT_COMPARED:
        content.pop(key, None)
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def current_fingerprints() -> list[str]:
    catalog = make_catalog()
    prints = []
    for seed in range(SEEDS):
        level, length = inputs(seed)
        puzzle = generate_verified(
            seed, level, length, catalog=catalog, topic_exists=lambda topic: topic in KNOWN_TOPICS
        )
        prints.append(fingerprint(puzzle))
    return prints


if __name__ == "__main__":
    from app.puzzles.levels import GENERATOR_VERSION

    payload = {
        "written_by_generator_version": GENERATOR_VERSION,
        "seeds": SEEDS,
        "fingerprints": current_fingerprints(),
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {SEEDS} fingerprints from generator version {GENERATOR_VERSION}")
