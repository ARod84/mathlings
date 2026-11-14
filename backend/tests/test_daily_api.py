"""Today's Puzzle: GET /api/v1/daily, and `context` on checks.

The route is pure generation on top of the registered puzzle types. These
tests pin down what makes it a daily puzzle: the same answer for everyone on
the same day, the rotation, the date window, and that the puzzle it hands out
is an ordinary verified puzzle that the check and hint routes accept.
"""

import hashlib
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.puzzles import daily
from app.puzzles.core.ids import MAX_SEED, split_id
from app.puzzles.core.verified import regenerate
from app.puzzles.daily import EPOCH, ROTATION
from app.taxonomy.importer import run_import
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.test_api import api_client, count_statements
from tests.test_players import as_player, attempts_of

DAILY = "/api/v1/daily"
PUZZLES = "/api/v1/puzzles"
# A Tuesday, frozen as the server's UTC date in the tests that need one.
TODAY = date(2026, 3, 10)


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The real app, with the real registry, on the puzzle fixture taxonomy."""
    database_path = tmp_path_factory.mktemp("daily") / "daily.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


@pytest.fixture
def frozen_today(monkeypatch: pytest.MonkeyPatch) -> date:
    """The server believes it is TODAY, in UTC."""
    monkeypatch.setattr(daily, "utc_today", lambda: TODAY)
    return TODAY


def get_daily(client: TestClient, day: date | str, level: int) -> dict:
    response = client.get(DAILY, params={"date": str(day), "level": level})
    assert response.status_code == 200, response.text
    return response.json()


def internal(client: TestClient, puzzle_id: str):
    """The full server-side puzzle behind an id, whichever game it is."""
    raw = split_id(puzzle_id)
    registered = client.app.state.puzzles.registry.by_code(raw.type_code)
    assert registered is not None, puzzle_id
    puzzle_type = client.app.state.puzzles.require(registered.game)
    return puzzle_type, regenerate(puzzle_type, raw, puzzle_id)


# ---- determinism ----


def test_the_same_date_game_and_level_give_the_same_puzzle_every_time(
    client: TestClient, frozen_today: date
):
    first = get_daily(client, frozen_today, 2)
    second = get_daily(client, frozen_today, 2)

    assert first == second
    assert first["date"] == frozen_today.isoformat()
    assert first["level"] == first["puzzle"]["level"] == 2
    assert first["game"] == first["puzzle"]["game"] == daily.game_for(frozen_today)
    # A level is a different puzzle; so is another day.
    assert get_daily(client, frozen_today, 1)["puzzle"]["puzzle_id"] != first["puzzle"]["puzzle_id"]
    other_day = get_daily(client, frozen_today + timedelta(days=1), 2)
    assert other_day["puzzle"]["puzzle_id"] != first["puzzle"]["puzzle_id"]


def test_the_seed_is_the_sha256_of_a_fixed_text_reduced_to_the_seed_range():
    day = date(2026, 3, 10)
    expected = int(hashlib.sha256(b"daily:2026-03-10:sum-grid:3").hexdigest(), 16) % (MAX_SEED + 1)

    choice = daily.choose(day, 3)

    # 68 days after the epoch: the third game of the wheel.
    assert choice.game == "sum-grid"
    assert choice.seed == expected
    assert 0 <= choice.seed <= MAX_SEED
    assert daily.daily_seed(day, "sum-grid", 3) == daily.daily_seed(day, "sum-grid", 3)
    assert daily.daily_seed(day, "sum-grid", 1) != daily.daily_seed(day, "sum-grid", 2)


def test_the_puzzle_id_regenerates_the_same_puzzle_through_the_ordinary_route(
    client: TestClient, frozen_today: date
):
    body = get_daily(client, frozen_today, 1)

    fetched = client.get(f"{PUZZLES}/{body['puzzle']['puzzle_id']}")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == body["puzzle"]


# ---- the rotation ----


def test_the_rotation_repeats_over_nine_consecutive_days():
    games = [daily.game_for(EPOCH + timedelta(days=offset)) for offset in range(9)]

    assert games == list(ROTATION) * 3
    assert ROTATION == ("missing-number", "sequences", "sum-grid")
    # Days before the epoch follow the same wheel backwards.
    assert daily.game_for(EPOCH - timedelta(days=1)) == "sum-grid"


def test_the_route_serves_the_game_of_each_day_in_the_window(
    client: TestClient, frozen_today: date
):
    for offset in (-1, 0, 1):
        day = frozen_today + timedelta(days=offset)
        assert get_daily(client, day, 1)["game"] == daily.game_for(day)


# ---- the date window ----


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_a_date_within_a_day_of_utc_today_is_accepted(
    client: TestClient, frozen_today: date, offset: int
):
    assert get_daily(client, frozen_today + timedelta(days=offset), 1)["level"] == 1


@pytest.mark.parametrize("offset", [-2, 2, -30, 365])
def test_a_date_further_away_is_a_422_that_says_why(
    client: TestClient, frozen_today: date, offset: int
):
    day = frozen_today + timedelta(days=offset)

    response = client.get(DAILY, params={"date": day.isoformat(), "level": 1})

    assert response.status_code == 422, response.text
    (problem,) = response.json()["detail"]
    assert problem["loc"] == ["query", "date"]
    assert problem["type"] == "date_out_of_window"
    assert problem["msg"] == "Input should be within 1 day of the server's date, 2026-03-10 (UTC)"
    assert problem["input"] == day.isoformat()


@pytest.mark.parametrize("bad", ["nope", "2026-13-01", "10/03/2026", "", "2026-03-10T12:00:00Z"])
def test_a_malformed_date_is_a_422(client: TestClient, frozen_today: date, bad: str):
    response = client.get(DAILY, params={"date": bad, "level": 1})

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", "date"]


@pytest.mark.parametrize("level", [0, 4, "easy"])
def test_a_level_outside_one_to_three_is_a_422(client: TestClient, frozen_today: date, level):
    response = client.get(DAILY, params={"date": frozen_today.isoformat(), "level": level})

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", "level"]


def test_the_date_and_the_level_are_required(client: TestClient, frozen_today: date):
    assert client.get(DAILY).status_code == 422
    assert client.get(DAILY, params={"date": frozen_today.isoformat()}).status_code == 422
    assert client.get(DAILY, params={"level": 1}).status_code == 422


def test_the_window_is_measured_against_the_real_clock_by_default(client: TestClient):
    today = daily.utc_today()

    assert get_daily(client, today, 1)["date"] == today.isoformat()
    assert client.get(DAILY, params={"date": "2000-01-01", "level": 1}).status_code == 422


# ---- the puzzle itself ----


@pytest.mark.parametrize("level", [1, 2, 3])
def test_the_returned_puzzle_is_verified_and_uses_the_default_parameters(
    client: TestClient, frozen_today: date, level: int
):
    body = get_daily(client, frozen_today, level)

    puzzle_type, puzzle = internal(client, body["puzzle"]["puzzle_id"])
    result = puzzle_type.verify(puzzle)

    assert result.ok, result
    assert puzzle.level == level
    assert puzzle_type.to_public(puzzle).model_dump(mode="json") == body["puzzle"]


def test_a_chain_day_uses_the_default_length_of_three(client: TestClient, monkeypatch):
    chain_day = next(
        EPOCH + timedelta(days=offset)
        for offset in range(3)
        if daily.game_for(EPOCH + timedelta(days=offset)) == "missing-number"
    )
    monkeypatch.setattr(daily, "utc_today", lambda: chain_day)

    body = get_daily(client, chain_day, 2)

    assert body["game"] == "missing-number"
    assert body["puzzle"]["length"] == 3
    assert len(body["puzzle"]["steps"]) == 3


# ---- check and hint on a daily id, and the context ----


def test_check_and_hint_work_on_a_daily_puzzle_id(client: TestClient, frozen_today: date):
    body = get_daily(client, frozen_today, 1)
    puzzle_id = body["puzzle"]["puzzle_id"]
    _puzzle_type, puzzle = internal(client, puzzle_id)

    right = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check",
        json={"answer": puzzle.steps[0].answer, "context": "daily"},
    )
    hint = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/1")

    assert right.status_code == 200, right.text
    assert right.json()["correct"] is True
    assert hint.status_code == 200, hint.text
    assert hint.json()["tier"] == 1
    assert hint.json()["text"]


def test_the_context_is_stored_with_the_attempt_and_only_when_sent(
    client: TestClient, frozen_today: date
):
    player = uuid.uuid4()
    puzzle_id = get_daily(client, frozen_today, 1)["puzzle"]["puzzle_id"]
    puzzle_type, puzzle = internal(client, puzzle_id)
    answer = puzzle.steps[0].answer

    with_context = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check",
        json={"answer": answer, "context": "daily"},
        headers=as_player(player),
    )
    without = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check",
        json={"answer": answer},
        headers=as_player(player),
    )
    explicit_null = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check",
        json={"answer": answer, "context": None},
        headers=as_player(player),
    )

    assert with_context.status_code == without.status_code == explicit_null.status_code == 200
    # The result does not depend on the context.
    assert with_context.json() == without.json() == explicit_null.json()
    daily_attempt, plain, nulled = attempts_of(client, player)
    expected_details = puzzle_type.attempt_details(puzzle, 0)
    assert daily_attempt.details == {**expected_details, "context": "daily"}
    assert plain.details == expected_details
    assert "context" not in plain.details
    assert nulled.details == expected_details
    # Daily attempts are ordinary evidence: same game, level and topics.
    assert daily_attempt.game == plain.game == puzzle_type.game
    assert daily_attempt.level == plain.level == 1
    assert daily_attempt.topic_ids == plain.topic_ids
    assert daily_attempt.correct is True


def test_an_unknown_context_is_a_422(client: TestClient, frozen_today: date):
    puzzle_id = get_daily(client, frozen_today, 1)["puzzle"]["puzzle_id"]

    response = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check", json={"answer": 1, "context": "homework"}
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "context"]


# ---- budget and documentation ----


def test_daily_runs_no_sql_statements(client: TestClient, frozen_today: date):
    for level in (1, 2, 3):
        with count_statements(client) as statements:
            get_daily(client, frozen_today, level)
        assert statements == [], statements


def test_daily_is_documented(client: TestClient):
    document = client.get("/openapi.json").json()
    operation = document["paths"][DAILY]["get"]

    assert operation["tags"] == ["Daily"]
    parameters = {p["name"]: p for p in operation["parameters"]}
    assert parameters["date"]["required"] is True
    assert parameters["date"]["schema"]["format"] == "date"
    assert parameters["level"]["required"] is True
    assert (parameters["level"]["schema"]["minimum"], parameters["level"]["schema"]["maximum"]) == (
        1,
        3,
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DailyPuzzle"
    )
    schema = document["components"]["schemas"]["DailyPuzzle"]
    assert schema["required"] == ["date", "game", "level", "puzzle"]
    puzzle = schema["properties"]["puzzle"]
    assert puzzle["discriminator"]["propertyName"] == "game"
    assert sorted(ref["$ref"].rsplit("/", 1)[1] for ref in puzzle["oneOf"]) == [
        "PuzzlePublic",
        "SequencePublic",
        "SumGridPublic",
    ]
    check = document["components"]["schemas"]["CheckRequest"]
    assert check["required"] == ["answer"]
    assert check["properties"]["context"]["anyOf"] == [
        {"type": "string", "const": "daily"},
        {"type": "null"},
    ]
