import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from app.config import BACKEND_DIR, sqlite_url
from app.db import make_engine

FIXTURE_TAXONOMY = Path(__file__).parent / "fixtures" / "taxonomy"
# The same, plus the topics and error patterns the puzzle library needs.
PUZZLE_FIXTURE_TAXONOMY = Path(__file__).parent / "fixtures" / "taxonomy_puzzles"
FIXTURE_COMMIT = "f" * 40


def migrate(database_path: Path, revision: str = "head") -> Engine:
    """Create the schema with the real Alembic migrations and return an engine for it.

    `revision` stops at an earlier migration, or moves an existing database on.
    """
    url = sqlite_url(database_path)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    # Leave logging alone, so pytest's caplog keeps working.
    config.attributes["configure_logging"] = False
    command.upgrade(config, revision)
    return make_engine(url)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = migrate(tmp_path / "test.db")
    yield engine
    engine.dispose()


@pytest.fixture
def taxonomy(tmp_path: Path) -> Path:
    """A private copy of the fixture taxonomy, safe to edit."""
    target = tmp_path / "taxonomy"
    shutil.copytree(FIXTURE_TAXONOMY, target)
    return target


Edit = Callable[[Any], None]


def _editor(taxonomy: Path) -> Callable[..., None]:
    """Edits one data file of a taxonomy copy, keeping the checksums consistent by default."""

    def edit(name: str, change: Edit, *, fix_checksums: bool = True) -> None:
        data_dir = taxonomy / "data"
        payload = json.loads((data_dir / name).read_bytes())
        change(payload)
        (data_dir / name).write_bytes(json.dumps(payload, indent=2).encode("utf-8"))
        if not fix_checksums:
            return

        def digest(file_name: str) -> str:
            return hashlib.sha256((data_dir / file_name).read_bytes()).hexdigest()

        if name == "topics.json":
            research = json.loads((data_dir / "teaching-research.json").read_bytes())
            research["topicFileSha256"] = digest("topics.json")
            (data_dir / "teaching-research.json").write_bytes(json.dumps(research).encode("utf-8"))
        manifest = json.loads((data_dir / "manifest.json").read_bytes())
        for file_name in manifest["files"]:
            manifest["files"][file_name]["sha256"] = digest(file_name)
        (data_dir / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))

    return edit


@pytest.fixture
def edit_taxonomy(taxonomy: Path) -> Callable[..., None]:
    """Edit one data file of the `taxonomy` copy in place."""
    return _editor(taxonomy)


@pytest.fixture
def taxonomy_puzzles(tmp_path: Path) -> Path:
    """A private copy of the puzzle fixture taxonomy, safe to edit."""
    target = tmp_path / "taxonomy_puzzles"
    shutil.copytree(PUZZLE_FIXTURE_TAXONOMY, target)
    return target


@pytest.fixture
def edit_puzzle_taxonomy(taxonomy_puzzles: Path) -> Callable[..., None]:
    """Edit one data file of the `taxonomy_puzzles` copy in place."""
    return _editor(taxonomy_puzzles)
