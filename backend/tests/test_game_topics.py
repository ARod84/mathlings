"""shared/game-topics.json: the topics each game practises, read by both apps.

These tests keep that file honest: every id is a real topic with the name the
file gives it, and the missing-number section says what levels.py says.
"""

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.config import BACKEND_DIR, get_settings
from app.db import make_engine
from app.models import Topic
from app.puzzles.registry import default_registry
from app.puzzles.types.missing_number.equations import ALL_FORMS
from app.puzzles.types.missing_number.levels import LEVELS, topic_ids_for
from app.taxonomy.importer import run_import
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate

GAME_TOPICS_FILE = BACKEND_DIR.parent / "shared" / "game-topics.json"


def load() -> dict:
    return json.loads(GAME_TOPICS_FILE.read_text(encoding="utf-8"))


def games(data: dict) -> dict[str, dict]:
    return {key: value for key, value in data.items() if not key.startswith("_")}


def all_ids(data: dict) -> set[str]:
    return {
        topic_id
        for game in games(data).values()
        for ids in game["byLevel"].values()
        for topic_id in ids
    }


def topic_names(engine) -> dict[str, str]:
    with Session(engine) as session:
        return dict(session.exec(select(Topic.id, Topic.name)).all())


def test_file_shape():
    data = load()

    assert set(games(data)) == {"number-pyramid", "missing-number"}
    assert set(data["number-pyramid"]["byLevel"]) == {"addOnly", "mixed", "fourRows"}
    assert set(data["missing-number"]["byLevel"]) == {"1", "2", "3"}
    for game in games(data).values():
        for ids in game["byLevel"].values():
            assert ids, "a level needs at least one topic"
            assert len(set(ids)) == len(ids)
    # The names map covers exactly the ids in use.
    assert set(data["_names"]) == all_ids(data)


def test_missing_number_topics_agree_with_levels_py():
    """The backend tags each puzzle from levels.py. The shared file must say the same."""
    by_level = load()["missing-number"]["byLevel"]

    assert set(by_level) == {str(level) for level in LEVELS}
    for level, spec in LEVELS.items():
        # Everything a chain at this level can be tagged with: primary first,
        # then the always-on extras, then the topic an answer-left step adds.
        every_topic = topic_ids_for(spec, list(ALL_FORMS))
        assert by_level[str(level)] == every_topic, f"level {level}"
        assert by_level[str(level)][0] == spec.primary_topic_id
        # A chain with no answer-left step carries a prefix of that list.
        without_answer_left = topic_ids_for(spec, ["a+?=c", "?+b=c"])
        assert by_level[str(level)][: len(without_answer_left)] == without_answer_left


def test_every_registered_puzzle_type_agrees_with_the_shared_file():
    """Whatever the registry serves has an entry in the shared file, level for level."""
    data = load()

    for puzzle_type in default_registry():
        assert puzzle_type.game in games(data), puzzle_type.game
        by_level = data[puzzle_type.game]["byLevel"]
        assert set(by_level) == {str(level) for level in puzzle_type.levels}
        for level, info in puzzle_type.levels.items():
            assert info.level == level
            assert by_level[str(level)] == list(info.topic_ids), (puzzle_type.game, level)


def test_every_topic_id_exists_in_the_fixture_taxonomy(tmp_path: Path):
    data = load()
    engine = migrate(tmp_path / "topics.db")
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    known = topic_names(engine)
    engine.dispose()

    missing = sorted(all_ids(data) - set(known))
    assert missing == [], f"not in the fixture taxonomy: {missing}"
    for topic_id, name in data["_names"].items():
        assert known[topic_id] == name, topic_id
    # In scope, so the taxonomy API lists them without extra flags.
    assert len(all_ids(data)) == 6


@pytest.mark.slow
def test_every_topic_id_exists_in_the_real_database():
    if not get_settings().database_path.is_file():
        pytest.skip("no database; run the migration and the importer first")
    engine = make_engine()
    known = topic_names(engine)
    with Session(engine) as session:
        in_scope = set(session.exec(select(Topic.id).where(Topic.in_scope)).all())
    engine.dispose()
    if "mt_3JgrHY221M" not in known:
        pytest.skip("the real taxonomy is not imported")
    data = load()

    missing = sorted(all_ids(data) - set(known))
    assert missing == [], f"not in the real taxonomy: {missing}"
    for topic_id, name in data["_names"].items():
        assert known[topic_id] == name, topic_id
    assert all_ids(data) <= in_scope
