"""Anonymous players: the X-Player-Id header, what gets stored, the summary and deletion."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, col, select

from app.config import BACKEND_DIR, sqlite_url
from app.db import make_engine
from app.models import Attempt, HintRequest, Player
from app.players.service import AttemptRecord, PlayerNotFound, PlayerService
from app.puzzles.levels import step_topic_ids
from app.puzzles.models import MistakeRule
from app.puzzles.service import PuzzleService
from app.taxonomy.importer import run_import
from app.taxonomy.service import TaxonomyService
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.test_api import api_client, count_statements
from tests.test_puzzle_api import PUZZLES, find_step, internal, new_puzzle

PLAYERS = "/api/v1/players"
HEADER = "X-Player-Id"
SNAPSHOT = Path(__file__).parent / "snapshots" / "puzzle_api_stateless.json"

UNKNOWN_ADD_SUB = "mt_3JgrHY221M"
EQUALS_SIGN = "mt_oIzycTBeE4"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    database_path = tmp_path_factory.mktemp("players") / "players.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def as_player(player_id: uuid.UUID | str) -> dict[str, str]:
    return {HEADER: str(player_id)}


def check(client: TestClient, puzzle_id: str, step: int, answer: int, player=None) -> dict:
    response = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/{step}/check",
        json={"answer": answer},
        headers=as_player(player) if player else None,
    )
    assert response.status_code == 200, response.text
    return response.json()


def hint(client: TestClient, puzzle_id: str, step: int, tier: int, player=None) -> dict:
    response = client.get(
        f"{PUZZLES}/{puzzle_id}/steps/{step}/hints/{tier}",
        headers=as_player(player) if player else None,
    )
    assert response.status_code == 200, response.text
    return response.json()


def row_counts(client: TestClient, player_id: uuid.UUID | None = None) -> dict[str, int]:
    """Rows per player table, for one player or for everyone."""
    with Session(client.app.state.engine) as session:
        counts = {}
        for model, column in (
            (Player, Player.id),
            (Attempt, Attempt.player_id),
            (HintRequest, HintRequest.player_id),
        ):
            query = select(func.count()).select_from(model)
            if player_id is not None:
                query = query.where(col(column) == player_id)
            counts[model.__tablename__] = session.exec(query).one()
        return counts


def attempts_of(client: TestClient, player_id: uuid.UUID) -> list[Attempt]:
    with Session(client.app.state.engine) as session:
        return list(
            session.exec(
                select(Attempt).where(col(Attempt.player_id) == player_id).order_by(col(Attempt.id))
            ).all()
        )


# ---- without the header nothing changes ----


def test_without_a_header_nothing_is_stored_and_responses_match_the_snapshot(client: TestClient):
    """The snapshot was taken from the API before player history existed.

    It is tied to generator version 2 and the puzzle fixture taxonomy. After a
    deliberate change to either, look at the diff and write the file again.
    """
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    before = row_counts(client)

    created = client.post(f"{PUZZLES}/missing-number", json={"level": 1, "length": 2, "seed": 42})
    puzzle_id = created.json()["puzzle_id"]

    assert created.json() == snapshot["new"]
    assert client.get(f"{PUZZLES}/{puzzle_id}").json() == snapshot["get"]
    for answer, expected in snapshot["checks"].items():
        assert check(client, puzzle_id, 0, int(answer)) == expected
    for tier, expected in enumerate(snapshot["hints"], start=1):
        assert hint(client, puzzle_id, 0, tier) == expected

    assert row_counts(client) == before


def test_with_a_header_the_response_bodies_are_the_same(client: TestClient):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    player = uuid.uuid4()
    headers = as_player(player)

    created = client.post(
        f"{PUZZLES}/missing-number", json={"level": 1, "length": 2, "seed": 42}, headers=headers
    )
    puzzle_id = created.json()["puzzle_id"]

    assert created.json() == snapshot["new"]
    assert client.get(f"{PUZZLES}/{puzzle_id}", headers=headers).json() == snapshot["get"]
    for answer, expected in snapshot["checks"].items():
        assert check(client, puzzle_id, 0, int(answer), player) == expected
    for tier, expected in enumerate(snapshot["hints"], start=1):
        assert hint(client, puzzle_id, 0, tier, player) == expected

    assert row_counts(client, player) == {
        "player": 1,
        "attempt": len(snapshot["checks"]),
        "hint_request": 3,
    }


def test_new_and_get_never_store_anything_even_with_a_header(client: TestClient):
    player = uuid.uuid4()

    puzzle_id = client.post(
        f"{PUZZLES}/missing-number", json={"level": 1}, headers=as_player(player)
    ).json()["puzzle_id"]
    client.get(f"{PUZZLES}/{puzzle_id}", headers=as_player(player))

    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}


# ---- the header ----


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-uuid",
        "1234",
        "",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",  # a real UUID, but version 1
        "00000000-0000-0000-0000-000000000000",
    ],
)
def test_a_malformed_header_is_422_with_a_clear_detail(client: TestClient, bad: str):
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    before = row_counts(client)
    headers = {HEADER: bad}

    responses = [
        client.post(f"{PUZZLES}/missing-number", json={"level": 1}, headers=headers),
        client.get(f"{PUZZLES}/{puzzle_id}", headers=headers),
        client.post(f"{PUZZLES}/{puzzle_id}/steps/0/check", json={"answer": 1}, headers=headers),
        client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/1", headers=headers),
        client.get(f"{PLAYERS}/me/summary", headers=headers),
        client.delete(f"{PLAYERS}/me", headers=headers),
    ]

    for response in responses:
        assert response.status_code == 422, response.text
        (problem,) = response.json()["detail"]
        assert problem["loc"] == ["header", HEADER]
        assert "UUID" in problem["msg"]
    assert row_counts(client) == before


def test_player_routes_need_the_header(client: TestClient):
    for response in (client.get(f"{PLAYERS}/me/summary"), client.delete(f"{PLAYERS}/me")):
        assert response.status_code == 422
        (problem,) = response.json()["detail"]
        assert problem["loc"] == ["header", HEADER]
        assert problem["type"] == "missing"


def test_the_header_is_accepted_in_upper_case(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    check(client, puzzle_id, 0, 1, str(player).upper())

    assert row_counts(client, player)["attempt"] == 1


# ---- what a check stores ----


def test_the_first_check_creates_the_player(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    assert row_counts(client, player)["player"] == 0

    check(client, puzzle_id, 0, 1, player)

    with Session(client.app.state.engine) as session:
        row = session.get(Player, player)
    assert row is not None
    assert row.created_at == row.last_seen_at
    assert row_counts(client, player) == {"player": 1, "attempt": 1, "hint_request": 0}

    check(client, puzzle_id, 0, 2, player)
    with Session(client.app.state.engine) as session:
        again = session.get(Player, player)
    assert again.created_at == row.created_at
    assert again.last_seen_at >= row.last_seen_at
    assert row_counts(client, player)["player"] == 1


def test_a_first_hint_also_creates_the_player(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    hint(client, puzzle_id, 1, 2, player)

    assert row_counts(client, player) == {"player": 1, "attempt": 0, "hint_request": 1}
    with Session(client.app.state.engine) as session:
        row = session.exec(select(HintRequest).where(col(HintRequest.player_id) == player)).one()
    assert (row.puzzle_id, row.step_index, row.tier) == (puzzle_id, 1, 2)


def test_attempt_on_step_counts_retries_per_step_and_per_player(client: TestClient):
    player, other = uuid.uuid4(), uuid.uuid4()
    puzzle = internal(client, new_puzzle(client, level=1, length=3, seed=8)["puzzle_id"])
    wrong = puzzle.steps[0].distractors[0].value

    check(client, puzzle.puzzle_id, 0, wrong, other)  # someone else's try does not count
    check(client, puzzle.puzzle_id, 0, wrong, player)
    check(client, puzzle.puzzle_id, 0, wrong, player)
    check(client, puzzle.puzzle_id, 0, puzzle.steps[0].answer, player)
    check(client, puzzle.puzzle_id, 1, puzzle.steps[1].answer, player)

    rows = attempts_of(client, player)
    assert [(row.step_index, row.attempt_on_step, row.correct) for row in rows] == [
        (0, 1, False),
        (0, 2, False),
        (0, 3, True),
        (1, 1, True),
    ]
    assert [row.attempt_on_step for row in attempts_of(client, other)] == [1]


def test_hint_tier_before_reflects_only_hints_fetched_before_the_check(client: TestClient):
    player, other = uuid.uuid4(), uuid.uuid4()
    puzzle = internal(client, new_puzzle(client, level=1, length=3, seed=9)["puzzle_id"])
    puzzle_id = puzzle.puzzle_id
    wrong = puzzle.steps[0].distractors[0].value

    hint(client, puzzle_id, 0, 3, other)  # another player's hint
    hint(client, puzzle_id, 1, 3, player)  # this player's hint, but for another step
    check(client, puzzle_id, 0, wrong, player)
    hint(client, puzzle_id, 0, 1, player)
    check(client, puzzle_id, 0, wrong, player)
    hint(client, puzzle_id, 0, 2, player)
    hint(client, puzzle_id, 0, 1, player)  # asking for a lower tier again changes nothing
    check(client, puzzle_id, 0, puzzle.steps[0].answer, player)
    hint(client, puzzle_id, 0, 3, player)  # after the last check: recorded nowhere on attempts

    assert [row.hint_tier_before for row in attempts_of(client, player)] == [0, 1, 2]


def test_a_known_mistake_is_stored_with_its_rules_pattern_and_reteach_topic(client: TestClient):
    player = uuid.uuid4()
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)

    body = check(client, puzzle.puzzle_id, index, wrong, player)
    check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, player)

    mistake, right = attempts_of(client, player)
    assert mistake.matched_rules == body["diagnosis"]["matched_rules"] == ["ADD_VISIBLE"]
    assert mistake.error_pattern_ids == [f"{UNKNOWN_ADD_SUB}#0"]
    assert mistake.reteach_topic_id == body["diagnosis"]["reteach_topic"]["id"] == EQUALS_SIGN
    assert mistake.correct is False
    assert mistake.answer == wrong
    assert (mistake.puzzle_id, mistake.step_index) == (puzzle.puzzle_id, index)
    assert (mistake.game, mistake.level) == ("missing-number", 1)
    assert mistake.generator_version == puzzle.generator_version
    assert mistake.form == puzzle.steps[index].form
    assert mistake.topic_ids == step_topic_ids(1, puzzle.steps[index].form)
    assert isinstance(mistake.created_at, datetime)

    assert right.correct is True
    assert (right.matched_rules, right.error_pattern_ids, right.reteach_topic_id) == ([], [], None)
    assert right.attempt_on_step == 2


def test_a_mistake_without_a_taxonomy_pattern_stores_no_pattern_id(client: TestClient):
    player = uuid.uuid4()
    puzzle, index, wrong = find_step(client, 3, MistakeRule.PLACE_VALUE_SLIP)

    body = check(client, puzzle.puzzle_id, index, wrong, player)

    (row,) = attempts_of(client, player)
    assert row.matched_rules == body["diagnosis"]["matched_rules"]
    assert "PLACE_VALUE_SLIP" in row.matched_rules
    linked = [rule for rule in row.matched_rules if rule != "PLACE_VALUE_SLIP"]
    assert bool(row.error_pattern_ids) == bool(linked)
    assert row.reteach_topic_id == body["diagnosis"]["reteach_topic"]["id"]


def test_a_request_that_fails_stores_nothing(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    headers = as_player(player)

    responses = [
        client.post(f"{PUZZLES}/nonsense/steps/0/check", json={"answer": 1}, headers=headers),
        client.post(f"{PUZZLES}/{puzzle_id}/steps/9/check", json={"answer": 1}, headers=headers),
        client.post(f"{PUZZLES}/{puzzle_id}/steps/0/check", json={"answer": -1}, headers=headers),
        client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/9", headers=headers),
        client.get(f"{PUZZLES}/{puzzle_id}/steps/9/hints/1", headers=headers),
    ]

    assert [response.status_code for response in responses] == [404, 404, 422, 404, 404]
    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}


def test_a_storage_failure_does_not_change_the_response(client: TestClient, monkeypatch, caplog):
    player = uuid.uuid4()
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    expected_check = check(client, puzzle.puzzle_id, index, wrong)
    expected_hint = hint(client, puzzle.puzzle_id, index, 1)

    def broken(*_args, **_kwargs):
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    monkeypatch.setattr(PlayerService, "record_attempt", broken)
    monkeypatch.setattr(PlayerService, "record_hint", broken)

    assert check(client, puzzle.puzzle_id, index, wrong, player) == expected_check
    assert hint(client, puzzle.puzzle_id, index, 1, player) == expected_hint
    assert "Could not store practice history" in caplog.text
    # The id is not written to the log.
    assert str(player) not in caplog.text
    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}


# ---- privacy ----


def test_the_tables_hold_no_personal_data(client: TestClient):
    inspector = inspect(client.app.state.engine)
    columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("player", "attempt", "hint_request")
    }

    assert columns["player"] == {"id", "created_at", "last_seen_at"}
    assert columns["hint_request"] == {
        "id",
        "player_id",
        "puzzle_id",
        "step_index",
        "tier",
        "created_at",
    }
    assert columns["attempt"] == {
        "id",
        "player_id",
        "puzzle_id",
        "generator_version",
        "game",
        "level",
        "step_index",
        "form",
        "answer",
        "correct",
        "matched_rules",
        "error_pattern_ids",
        "reteach_topic_id",
        "topic_ids",
        "attempt_on_step",
        "hint_tier_before",
        "created_at",
    }


def test_no_cookie_is_set_and_the_id_is_never_sent_back_or_logged(client: TestClient, caplog):
    player = uuid.uuid4()
    headers = as_player(player) | {"User-Agent": "KidBrowser/1.0"}
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    with caplog.at_level("DEBUG"):
        responses = [
            client.post(f"{PUZZLES}/missing-number", json={"level": 1}, headers=headers),
            client.post(
                f"{PUZZLES}/{puzzle_id}/steps/0/check", json={"answer": 1}, headers=headers
            ),
            client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/1", headers=headers),
            client.get(f"{PLAYERS}/me/summary", headers=headers),
            client.delete(f"{PLAYERS}/me", headers=headers),
        ]

    for response in responses:
        assert "set-cookie" not in response.headers
        assert str(player) not in response.text
        assert str(player) not in str(response.headers)
    assert str(player) not in caplog.text
    assert "KidBrowser" not in caplog.text


# ---- the summary ----


def build_history(client: TestClient, player: uuid.UUID) -> None:
    """A history written row by row, so the expected summary can be worked out by hand.

    puzzle one (topics: add/sub and equals sign)
      step 0   ADD_VISIBLE, ADD_VISIBLE, right       hints: tiers 1 and 2
      step 1   right
    puzzle two (topic: add/sub)
      step 0   OFF_BY_ONE_OVER, ADD_VISIBLE + POSITION_CONFUSION, PLACE_VALUE_SLIP,
               OFF_BY_ONE_OVER (never right)         hints: tier 1
      step 1   right
      step 3   never checked                         hints: tier 1
    """
    both, one = [UNKNOWN_ADD_SUB, EQUALS_SIGN], [UNKNOWN_ADD_SUB]
    tries = [
        ("one", both, 0, ["ADD_VISIBLE"]),
        ("one", both, 0, ["ADD_VISIBLE"]),
        ("one", both, 0, None),
        ("one", both, 1, None),
        ("two", one, 0, ["OFF_BY_ONE_OVER"]),
        ("two", one, 0, ["ADD_VISIBLE", "POSITION_CONFUSION"]),
        ("two", one, 0, ["PLACE_VALUE_SLIP"]),
        ("two", one, 0, ["OFF_BY_ONE_OVER"]),
        ("two", one, 1, None),
    ]
    seen: dict[tuple[str, int], int] = {}
    with Session(client.app.state.engine) as session:
        session.add(
            Player(
                id=player,
                created_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
                last_seen_at=datetime(2026, 11, 2, 10, 8, tzinfo=UTC),
            )
        )
        session.commit()
        for minute, (puzzle_id, topic_ids, step, rules) in enumerate(tries):
            seen[(puzzle_id, step)] = seen.get((puzzle_id, step), 0) + 1
            session.add(
                Attempt(
                    player_id=player,
                    puzzle_id=puzzle_id,
                    generator_version="2",
                    game="missing-number",
                    level=1,
                    step_index=step,
                    form="a+?=c",
                    answer=5,
                    correct=rules is None,
                    matched_rules=rules or [],
                    error_pattern_ids=[],
                    reteach_topic_id=None,
                    topic_ids=topic_ids,
                    attempt_on_step=seen[(puzzle_id, step)],
                    hint_tier_before=0,
                    # Puzzle one on 1 November, puzzle two on 2 November.
                    created_at=datetime(
                        2026, 11, 1 if puzzle_id == "one" else 2, 10, minute, tzinfo=UTC
                    ),
                )
            )
        for puzzle_id, step, tier in (("one", 0, 1), ("one", 0, 2), ("two", 0, 1), ("two", 3, 1)):
            session.add(
                HintRequest(
                    player_id=player,
                    puzzle_id=puzzle_id,
                    step_index=step,
                    tier=tier,
                    created_at=datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
                )
            )
        session.commit()


def test_summary_numbers_on_a_hand_built_history(client: TestClient):
    player, other = uuid.uuid4(), uuid.uuid4()
    build_history(client, player)
    # Someone else's practice must not leak into the numbers.
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    check(client, puzzle.puzzle_id, index, wrong, other)
    hint(client, puzzle.puzzle_id, index, 1, other)

    response = client.get(f"{PLAYERS}/me/summary", headers=as_player(player))

    assert response.status_code == 200
    body = response.json()
    # Mastery has its own tests, in test_adaptive.py.
    assert len(body.pop("mastery")) == 2
    assert body == {
        "player_since": "2026-11-01T09:00:00Z",
        "totals": {
            "attempts": 9,
            "steps": 4,
            "correct": 3,
            "hint_requests": 4,
            "first_try_correct_rate": 0.5,
            "hints_per_step": 1.0,
        },
        "topics": [
            {
                "topic_id": UNKNOWN_ADD_SUB,
                "attempts": 9,
                "steps": 4,
                "first_try_correct_rate": 0.5,
                # Three hints on steps that were checked; the fourth has no step to belong to.
                "hints_per_step": 0.75,
                "top_mistakes": [
                    {"rule": "ADD_VISIBLE", "count": 3},
                    {"rule": "OFF_BY_ONE_OVER", "count": 2},
                    # One each with POSITION_CONFUSION; the name settles the tie.
                    {"rule": "PLACE_VALUE_SLIP", "count": 1},
                ],
                "last_practised": "2026-11-02T10:08:00Z",
            },
            {
                "topic_id": EQUALS_SIGN,
                "attempts": 4,
                "steps": 2,
                "first_try_correct_rate": 0.5,
                "hints_per_step": 1.0,
                "top_mistakes": [{"rule": "ADD_VISIBLE", "count": 2}],
                "last_practised": "2026-11-01T10:03:00Z",
            },
        ],
    }


def test_summary_from_a_short_real_play_session(client: TestClient):
    player = uuid.uuid4()
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)

    check(client, puzzle.puzzle_id, index, wrong, player)
    hint(client, puzzle.puzzle_id, index, 1, player)
    check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, player)

    summary = client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).json()

    assert summary["totals"] == {
        "attempts": 2,
        "steps": 1,
        "correct": 1,
        "hint_requests": 1,
        "first_try_correct_rate": 0.0,
        "hints_per_step": 1.0,
    }
    assert [topic["topic_id"] for topic in summary["topics"]] == sorted(
        step_topic_ids(1, puzzle.steps[index].form)
    )
    for topic in summary["topics"]:
        assert topic["top_mistakes"] == [{"rule": "ADD_VISIBLE", "count": 1}]
        assert (topic["attempts"], topic["steps"], topic["hints_per_step"]) == (2, 1, 1.0)
    assert summary["player_since"].endswith("Z")


def test_summary_is_empty_for_a_known_player_with_no_attempts(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    hint(client, puzzle_id, 0, 1, player)  # known, but nothing checked yet

    response = client.get(f"{PLAYERS}/me/summary", headers=as_player(player))

    assert response.status_code == 200
    body = response.json()
    assert body["topics"] == []
    assert body["totals"] == {
        "attempts": 0,
        "steps": 0,
        "correct": 0,
        "hint_requests": 1,
        "first_try_correct_rate": None,
        "hints_per_step": None,
    }
    assert set(body) == {"player_since", "totals", "topics", "mastery"}
    assert body["mastery"] == []


def test_summary_for_an_unknown_id_is_404(client: TestClient):
    response = client.get(f"{PLAYERS}/me/summary", headers=as_player(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json() == {"detail": "Player not found"}


# ---- deleting ----


def test_delete_removes_every_row_and_a_second_delete_is_still_204(client: TestClient):
    player, other = uuid.uuid4(), uuid.uuid4()
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    for who in (player, other):
        check(client, puzzle.puzzle_id, index, wrong, who)
        hint(client, puzzle.puzzle_id, index, 1, who)
        check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, who)
    kept = {"player": 1, "attempt": 2, "hint_request": 1}
    assert row_counts(client, player) == kept

    first = client.delete(f"{PLAYERS}/me", headers=as_player(player))

    assert first.status_code == 204
    assert first.content == b""
    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}
    # Nobody else's rows were touched.
    assert row_counts(client, other) == kept
    assert client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).status_code == 404

    second = client.delete(f"{PLAYERS}/me", headers=as_player(player))
    assert second.status_code == 204
    never_seen = client.delete(f"{PLAYERS}/me", headers=as_player(uuid.uuid4()))
    assert never_seen.status_code == 204


def test_the_foreign_keys_cascade_on_their_own(client: TestClient):
    """Deleting only the player row takes the attempts and hints with it."""
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    check(client, puzzle_id, 0, 1, player)
    hint(client, puzzle_id, 0, 1, player)
    assert row_counts(client, player) == {"player": 1, "attempt": 1, "hint_request": 1}

    with Session(client.app.state.engine) as session:
        session.execute(text("DELETE FROM player WHERE id = :id"), {"id": player.hex})
        session.commit()

    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}


def test_a_player_can_start_again_after_deleting(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    check(client, puzzle_id, 0, 1, player)
    check(client, puzzle_id, 0, 1, player)
    client.delete(f"{PLAYERS}/me", headers=as_player(player))

    check(client, puzzle_id, 0, 1, player)

    assert [row.attempt_on_step for row in attempts_of(client, player)] == [1]


# ---- statement budgets ----


def test_statement_budgets_with_a_player(client: TestClient):
    """What the header costs on top of the stateless budgets in test_puzzle_api.py.

    check   +3: create-or-touch the player, the two counts in one SELECT, the INSERT
    hint    +2: create-or-touch the player, the INSERT
    new/get +0: the header is validated, nothing is read or written
    """
    player = uuid.uuid4()
    headers = as_player(player)
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    puzzle_id = puzzle.puzzle_id
    right = puzzle.steps[index].answer

    def statements(method: str, path: str, **kwargs) -> list[str]:
        with count_statements(client) as seen:
            response = client.request(method, f"{PUZZLES}{path}", headers=headers, **kwargs)
        assert response.status_code in (200, 201), response.text
        return seen

    assert len(statements("GET", f"/{puzzle_id}")) == 1
    assert len(statements("POST", "/missing-number", json={"level": 3, "length": 4})) == 1
    # Stateless: 1. The first one also creates the player, in the same statement.
    assert len(statements("GET", f"/{puzzle_id}/steps/{index}/hints/3")) == 3
    assert len(statements("GET", f"/{puzzle_id}/steps/{index}/hints/3")) == 3
    # Stateless: 2 (the second names the reteach topic).
    assert len(statements("POST", f"/{puzzle_id}/steps/{index}/check", json={"answer": wrong})) == 5
    # Stateless: 1.
    assert len(statements("POST", f"/{puzzle_id}/steps/{index}/check", json={"answer": right})) == 4
    # The numbers do not grow with the history.
    for _ in range(25):
        check(client, puzzle_id, index, wrong, player)
    assert len(statements("POST", f"/{puzzle_id}/steps/{index}/check", json={"answer": right})) == 4


def test_summary_and_delete_use_a_fixed_number_of_statements(client: TestClient):
    small, large = uuid.uuid4(), uuid.uuid4()
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    check(client, puzzle.puzzle_id, index, wrong, small)
    for seed in range(40):
        other = internal(client, new_puzzle(client, level=2, length=4, seed=seed)["puzzle_id"])
        for step_index, step in enumerate(other.steps):
            check(client, other.puzzle_id, step_index, step.distractors[0].value, large)
            hint(client, other.puzzle_id, step_index, 1, large)
            check(client, other.puzzle_id, step_index, step.answer, large)
    assert row_counts(client, large) == {"player": 1, "attempt": 320, "hint_request": 160}

    def summary_statements(player: uuid.UUID) -> list[str]:
        with count_statements(client) as seen:
            response = client.get(f"{PLAYERS}/me/summary", headers=as_player(player))
        assert response.status_code == 200
        return seen

    # The player, per topic, mistakes per topic, hints per topic, totals, and
    # one for the first tries that mastery is replayed from.
    assert len(summary_statements(small)) == 6
    assert len(summary_statements(large)) == 6

    for player in (large, uuid.uuid4()):
        with count_statements(client) as seen:
            assert client.delete(f"{PLAYERS}/me", headers=as_player(player)).status_code == 204
        assert len(seen) == 3


# ---- the service on its own ----


def test_the_player_service_works_without_http(client: TestClient):
    player = uuid.uuid4()
    record = AttemptRecord(
        puzzle_id="p",
        generator_version="2",
        game="missing-number",
        level=1,
        step_index=0,
        form="a+?=c",
        answer=3,
        correct=False,
        matched_rules=["ADD_VISIBLE"],
        error_pattern_ids=[f"{UNKNOWN_ADD_SUB}#0"],
        reteach_topic_id=EQUALS_SIGN,
        topic_ids=[UNKNOWN_ADD_SUB],
    )
    with Session(client.app.state.engine) as session:
        players = PlayerService(session)
        with pytest.raises(PlayerNotFound):
            players.summary(player)

        players.record_hint(player, "p", 0, 2)
        players.record_attempt(player, record)
        summary = players.summary(player)
        assert summary.totals.attempts == 1
        assert summary.topics[0].top_mistakes[0].rule == "ADD_VISIBLE"
        assert summary.topics[0].hints_per_step == 1.0
        assert summary.player_since.tzinfo is not None

        players.delete(player)
        with pytest.raises(PlayerNotFound):
            players.summary(player)
    assert row_counts(client, player) == {"player": 0, "attempt": 0, "hint_request": 0}


def test_the_puzzle_service_stores_nothing_without_a_player(client: TestClient):
    before = row_counts(client)
    with Session(client.app.state.engine) as session:
        taxonomy = TaxonomyService(session, client.app.state.graph)
        catalog = client.app.state.puzzles.require_catalog()
        puzzle = PuzzleService(taxonomy, catalog).new_puzzle(level=1, length=2, seed=4)

        # No PlayerService: a player id has nowhere to go.
        PuzzleService(taxonomy, catalog).check(puzzle.puzzle_id, 0, 1, player_id=uuid.uuid4())
        # A PlayerService but no player id.
        with_players = PuzzleService(taxonomy, catalog, players=PlayerService(session))
        with_players.check(puzzle.puzzle_id, 0, 1)
        with_players.hint(puzzle.puzzle_id, 0, 1)

    assert row_counts(client) == before


def test_player_modules_do_not_import_fastapi():
    for name in ("service.py", "schemas.py"):
        source = (BACKEND_DIR / "app" / "players" / name).read_text(encoding="utf-8")
        assert "fastapi" not in source, name
        assert "starlette" not in source, name


# ---- the app around it ----


def test_delete_and_the_header_are_allowed_by_cors(client: TestClient):
    preflight = client.options(
        f"{PLAYERS}/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-player-id",
        },
    )

    assert preflight.status_code == 200
    assert "DELETE" in preflight.headers["access-control-allow-methods"]
    assert "x-player-id" in preflight.headers["access-control-allow-headers"].lower()


def test_player_routes_are_documented(client: TestClient):
    document = client.get("/openapi.json").json()
    paths = document["paths"]

    assert paths[f"{PLAYERS}/me/summary"]["get"]["tags"] == ["Players"]
    assert paths[f"{PLAYERS}/me"]["delete"]["tags"] == ["Players"]
    assert "204" in paths[f"{PLAYERS}/me"]["delete"]["responses"]
    summary = paths[f"{PLAYERS}/me/summary"]["get"]
    assert summary["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PlayerSummary"
    )
    assert "404" in summary["responses"]

    def header_of(operation: dict) -> dict:
        (parameter,) = [p for p in operation["parameters"] if p["in"] == "header"]
        return parameter

    for operation in (summary, paths[f"{PLAYERS}/me"]["delete"]):
        assert header_of(operation)["name"] == HEADER
        assert header_of(operation)["required"] is True
    for path, operations in paths.items():
        if "/puzzles" in path:
            for operation in operations.values():
                assert header_of(operation)["name"] == HEADER
                assert header_of(operation)["required"] is False


def test_without_the_player_tables_play_goes_on_and_player_routes_are_503(tmp_path: Path, caplog):
    """A database that stopped at migration 0001: the games work, history does not."""
    database_path = tmp_path / "old.db"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    config.attributes["configure_logging"] = False
    command.upgrade(config, "0001")
    engine = make_engine(sqlite_url(database_path))
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    player = uuid.uuid4()

    with api_client(database_path) as old:
        puzzle_id = new_puzzle(old, level=1, length=2, seed=6)["puzzle_id"]
        assert check(old, puzzle_id, 0, 1, player)["correct"] in (True, False)
        assert hint(old, puzzle_id, 0, 1, player)["tier"] == 1
        assert "Could not store practice history" in caplog.text

        for response in (
            old.get(f"{PLAYERS}/me/summary", headers=as_player(player)),
            old.delete(f"{PLAYERS}/me", headers=as_player(player)),
        ):
            assert response.status_code == 503
            assert "migration" in response.json()["detail"]
