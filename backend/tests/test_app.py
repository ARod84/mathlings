from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.config import Settings
from app.main import app as fastapi_app


def test_health():
    response = TestClient(fastapi_app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_defaults_and_environment(monkeypatch, tmp_path: Path):
    defaults = Settings(_env_file=None)
    assert defaults.database_path.name == "app.db"
    assert defaults.database_path.parent.name == "data"
    assert defaults.taxonomy_path.parts[-2:] == ("vendor", "os-taxonomy")

    monkeypatch.setenv("MATHLINGS_DATABASE_PATH", str(tmp_path / "other.db"))
    monkeypatch.setenv("MATHLINGS_TAXONOMY_PATH", str(tmp_path / "tax"))
    overridden = Settings(_env_file=None)
    assert overridden.database_path == tmp_path / "other.db"
    assert overridden.taxonomy_path == tmp_path / "tax"
    assert overridden.database_url.startswith("sqlite:///")


def test_migration_creates_exactly_the_model_schema(engine: Engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, SQLModel.metadata)
    assert differences == []


def test_migration_creates_the_query_indexes(engine: Engine):
    inspector = inspect(engine)

    def indexed(table: str) -> set[tuple[str, ...]]:
        return {tuple(index["column_names"]) for index in inspector.get_indexes(table)}

    assert ("domain",) in indexed("topic")
    assert ("in_scope",) in indexed("topic")
    assert ("prerequisite_id",) in indexed("prerequisite")
    assert ("topic_id",) in indexed("error_pattern")
    pair = inspector.get_unique_constraints("prerequisite")
    assert [constraint["column_names"] for constraint in pair] == [["topic_id", "prerequisite_id"]]
    research = inspector.get_unique_constraints("teaching_research")
    assert [constraint["column_names"] for constraint in research] == [["topic_id"]]
