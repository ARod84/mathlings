"""Optional: the real import against backend/vendor/os-taxonomy.

Not part of the normal run (the research file is about 24 MB). Run it with:

    uv run pytest -m slow
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.config import BACKEND_DIR
from app.taxonomy.constants import REVIEWED_COUNTS
from app.taxonomy.importer import checked_commit, run_import

VENDOR = BACKEND_DIR / "vendor" / "os-taxonomy"


@pytest.mark.slow
def test_real_import_matches_the_reviewed_counts(engine: Engine):
    if not (Path(VENDOR) / "data" / "manifest.json").is_file():
        pytest.skip("backend/vendor/os-taxonomy is missing; run scripts/fetch_taxonomy first")

    commit = checked_commit(VENDOR)
    summary = run_import(engine, VENDOR, commit)

    assert summary.topics_in_scope == REVIEWED_COUNTS["topics_in_scope"]
    assert summary.topics_total == REVIEWED_COUNTS["topics_total"]
    assert summary.closure_non_math == REVIEWED_COUNTS["closure_non_math"]
    assert summary.dangling_references == []
    assert summary.error_patterns > 0

    again = run_import(engine, VENDOR, commit)
    assert not again.changed_anything
