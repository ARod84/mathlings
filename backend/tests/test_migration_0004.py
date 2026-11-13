"""Migration 0004: attempt.details is added and filled, attempt.form becomes optional."""

import json
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import BACKEND_DIR, sqlite_url
from tests.conftest import migrate

INSERT_WITH_FORM = (
    "INSERT INTO attempt (player_id, puzzle_id, generator_version, game, level, "
    "step_index, form, answer, correct, matched_rules, error_pattern_ids, "
    "topic_ids, attempt_on_step, hint_tier_before, created_at) VALUES "
    "(:player, :puzzle, '3', :game, 1, 0, :form, 1, 1, '[]', '[]', "
    "'[]', 1, 0, '2026-11-01 10:00:00')"
)
INSERT_WITH_DETAILS = (
    "INSERT INTO attempt (player_id, puzzle_id, generator_version, game, level, "
    "step_index, details, answer, correct, matched_rules, error_pattern_ids, "
    "topic_ids, attempt_on_step, hint_tier_before, created_at) VALUES "
    "(:player, :puzzle, '3', :game, 1, 0, :details, 1, 1, '[]', '[]', "
    "'[]', 1, 0, '2026-11-02 10:00:00')"
)
OLD_ROWS = [("p1", "missing-number", "a+?=c"), ("p2", "missing-number", "c=?-b"), ("p3", "x", "?")]


def downgrade(database_path: Path, revision: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    config.attributes["configure_logging"] = False
    command.downgrade(config, revision)


def columns(engine) -> dict[str, bool]:
    """Column name to "may be null", for the attempt table."""
    return {column["name"]: column["nullable"] for column in inspect(engine).get_columns("attempt")}


def test_upgrade_copies_form_into_details_and_keeps_the_form_column(tmp_path: Path):
    database_path = tmp_path / "attempts.db"
    engine = migrate(database_path, "0003")
    player = uuid.uuid4().hex
    assert columns(engine) == {**columns(engine), "form": False}
    assert "details" not in columns(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO player (id, created_at, last_seen_at) VALUES (:id, :at, :at)"),
            {"id": player, "at": "2026-11-01 10:00:00"},
        )
        for puzzle, game, form in OLD_ROWS:
            connection.execute(
                text(INSERT_WITH_FORM),
                {"player": player, "puzzle": puzzle, "game": game, "form": form},
            )
    engine.dispose()

    engine = migrate(database_path)

    assert columns(engine)["form"] is True
    assert columns(engine)["details"] is False
    with engine.begin() as connection:
        stored = connection.execute(
            text("SELECT puzzle_id, game, form, details FROM attempt ORDER BY id")
        ).all()
        # Every old row: the form is still in its column, and now in details too.
        assert [(row.puzzle_id, row.game, row.form) for row in stored] == OLD_ROWS
        assert [json.loads(row.details) for row in stored] == [
            {"form": form} for _puzzle, _game, form in OLD_ROWS
        ]
        # A new row needs no form.
        connection.execute(
            text(INSERT_WITH_DETAILS),
            {"player": player, "puzzle": "p4", "game": "dummy", "details": '{"shown": 7}'},
        )
        assert (
            connection.execute(text("SELECT form FROM attempt WHERE puzzle_id = 'p4'")).scalar_one()
            is None
        )
    engine.dispose()


def test_downgrade_puts_the_form_back_and_drops_details(tmp_path: Path):
    database_path = tmp_path / "attempts.db"
    engine = migrate(database_path)
    player = uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO player (id, created_at, last_seen_at) VALUES (:id, :at, :at)"),
            {"id": player, "at": "2026-11-01 10:00:00"},
        )
        # Rows as the app writes them now: details only.
        for puzzle, game, details in (
            ("p1", "missing-number", '{"form": "?-b=c"}'),
            ("p2", "dummy", '{"shown": 7}'),
        ):
            connection.execute(
                text(INSERT_WITH_DETAILS),
                {"player": player, "puzzle": puzzle, "game": game, "details": details},
            )
    engine.dispose()

    downgrade(database_path, "0003")

    engine = migrate(database_path, "0003")
    assert columns(engine)["form"] is False
    assert "details" not in columns(engine)
    with engine.connect() as connection:
        forms = connection.execute(text("SELECT puzzle_id, form FROM attempt ORDER BY id")).all()
    engine.dispose()
    # A chain's form comes back from details; a game without one gets an empty form.
    assert [tuple(row) for row in forms] == [("p1", "?-b=c"), ("p2", "")]
