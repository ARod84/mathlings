"""GET /players/me/next, and mastery in the summary, on hand-built attempt histories."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adaptive.constants import DEFAULT_BKT
from app.puzzles.levels import (
    TOPIC_EQUALS_SIGN,
    TOPIC_INVERSE,
    TOPIC_MISSING_NUMBER,
    TOPIC_UNKNOWN_ADD_SUB,
)
from app.taxonomy.importer import run_import
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.test_adaptive import store_first_tries
from tests.test_api import api_client, count_statements
from tests.test_players import HEADER, PLAYERS, as_player, check, hint
from tests.test_puzzle_api import PUZZLES, internal, new_puzzle

NEXT = f"{PLAYERS}/me/next"
GAME = {"game": "missing-number"}
UNKNOWN_NAME = "Unknown in Addition & Subtraction"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    database_path = tmp_path_factory.mktemp("next") / "next.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def get_next(client: TestClient, player: uuid.UUID) -> dict:
    response = client.get(NEXT, params=GAME, headers=as_player(player))
    assert response.status_code == 200, response.text
    return response.json()


def test_cold_start_for_a_player_the_server_has_never_seen(client: TestClient):
    body = get_next(client, uuid.uuid4())

    assert body == {
        "level": 1,
        "length": 2,
        "reason_code": "cold_start",
        "reason": "No practice recorded yet, so start at level 1 with chains of 2 steps.",
        "focus_rule": None,
        "focus": None,
        "mastery": [
            {
                "topic_id": TOPIC_UNKNOWN_ADD_SUB,
                "name": UNKNOWN_NAME,
                "level": 1,
                "p_known": DEFAULT_BKT.p_init,
                "observations": 0,
            },
            {
                "topic_id": TOPIC_EQUALS_SIGN,
                "name": "What the equals sign means",
                "level": 1,
                "p_known": DEFAULT_BKT.p_init,
                "observations": 0,
            },
        ],
    }


def test_cold_start_for_a_known_player_with_no_attempts(client: TestClient):
    player = uuid.uuid4()
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    hint(client, puzzle_id, 0, 1, player)  # the player row exists; nothing was checked

    body = get_next(client, player)

    assert (body["level"], body["length"], body["reason_code"]) == (1, 2, "cold_start")


def test_promote(client: TestClient):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, True)] * 6)

    body = get_next(client, player)

    assert (body["level"], body["length"], body["reason_code"]) == (2, 2, "promote")
    assert "Move up to level 2" in body["reason"]
    assert body["focus_rule"] is None
    by_key = {(m["topic_id"], m["level"]): m for m in body["mastery"]}
    # What was practised: the topic at level 1.
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 1)]["observations"] == 6
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 1)]["p_known"] >= 0.95
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 1)]["name"] == UNKNOWN_NAME
    # What comes next: level 2, starting from the prior. It is listed first.
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 2)] == body["mastery"][0]
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 2)]["p_known"] == 0.3
    assert by_key[(TOPIC_UNKNOWN_ADD_SUB, 2)]["observations"] == 0


def test_step_down_with_a_focus_rule(client: TestClient):
    player = uuid.uuid4()
    # Six wrong first tries at level 3; store_first_tries marks each as ADD_VISIBLE.
    store_first_tries(client, player, [(3, False)] * 6)

    body = get_next(client, player)

    assert (body["level"], body["length"], body["reason_code"]) == (2, 2, "step_down")
    assert "Step back to level 2" in body["reason"]
    assert body["focus_rule"] == "ADD_VISIBLE"
    assert "ADD_VISIBLE (6 of the last 6 first tries)" in body["reason"]
    assert {(m["topic_id"], m["level"]) for m in body["mastery"]} == {
        (TOPIC_UNKNOWN_ADD_SUB, 2),
        (TOPIC_EQUALS_SIGN, 2),
        (TOPIC_MISSING_NUMBER, 3),
        (TOPIC_INVERSE, 3),
    }
    assert [m["level"] for m in body["mastery"]] == [2, 2, 3, 3]


def test_consolidate_after_real_play(client: TestClient):
    player = uuid.uuid4()
    puzzle = internal(client, new_puzzle(client, level=2, length=3, seed=5)["puzzle_id"])
    check(client, puzzle.puzzle_id, 0, puzzle.steps[0].answer, player)
    check(client, puzzle.puzzle_id, 1, puzzle.steps[1].distractors[0].value, player)
    check(client, puzzle.puzzle_id, 1, puzzle.steps[1].answer, player)  # a retry: not evidence

    body = get_next(client, player)

    assert (body["level"], body["reason_code"]) == (2, "consolidate")
    assert body["length"] in (2, 3, 4)
    assert "Keep practising level 2" in body["reason"]
    primary = body["mastery"][0]
    assert (primary["topic_id"], primary["level"], primary["observations"]) == (
        TOPIC_UNKNOWN_ADD_SUB,
        2,
        2,
    )


def test_the_header_and_the_game_are_required(client: TestClient):
    player = uuid.uuid4()

    assert client.get(NEXT, params=GAME).status_code == 422
    assert client.get(NEXT, params=GAME, headers={HEADER: "nope"}).status_code == 422
    assert client.get(NEXT, headers=as_player(player)).status_code == 422
    other = client.get(NEXT, params={"game": "number-pyramid"}, headers=as_player(player))
    assert other.status_code == 422


def test_next_stores_nothing_sets_no_cookie_and_does_not_echo_the_id(client: TestClient):
    player = uuid.uuid4()

    response = client.get(NEXT, params=GAME, headers=as_player(player))

    assert "set-cookie" not in response.headers
    assert str(player) not in response.text
    # Asking does not create the player.
    assert client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).status_code == 404


def test_next_uses_three_statements_whatever_the_history(client: TestClient):
    small, large, nobody = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store_first_tries(client, small, [(1, True)])
    store_first_tries(client, large, [(1 + index % 3, index % 4 != 0) for index in range(450)])

    for player in (small, large, nobody):
        with count_statements(client) as seen:
            get_next(client, player)
        # The taxonomy freshness check, the player's first tries, the topic names.
        assert len(seen) == 3, seen


def test_next_is_documented(client: TestClient):
    operation = client.get("/openapi.json").json()["paths"][NEXT]["get"]

    assert operation["tags"] == ["Players"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/NextPuzzle"
    )
    parameters = {p["name"]: p for p in operation["parameters"]}
    assert parameters[HEADER]["required"] is True
    assert parameters["game"]["required"] is True


def test_the_summary_includes_mastery_per_topic_and_level(client: TestClient):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, True)] * 3 + [(2, False)] * 2)

    summary = client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).json()

    assert [(m["topic_id"], m["level"], m["observations"]) for m in summary["mastery"]] == [
        (TOPIC_UNKNOWN_ADD_SUB, 1, 3),
        (TOPIC_UNKNOWN_ADD_SUB, 2, 2),
    ]
    level_1, level_2 = summary["mastery"]
    assert level_1["p_known"] > 0.9 > 0.3 > level_2["p_known"]
    assert level_1["last_practised"].endswith("Z")
    assert set(level_1) == {"topic_id", "level", "p_known", "observations", "last_practised"}


# ---- focus: the rule to generate the next puzzle with ----


def test_next_gives_a_focus_when_a_targetable_mistake_keeps_coming_up(client: TestClient):
    player = uuid.uuid4()
    # store_first_tries marks each wrong first try as ADD_VISIBLE.
    store_first_tries(client, player, [(1, True), (1, False), (1, False)])

    body = get_next(client, player)

    assert body["focus_rule"] == "ADD_VISIBLE"
    assert body["focus"] == "ADD_VISIBLE"
    assert "The next puzzle targets it." in body["reason"]


def test_focus_is_null_after_a_focused_puzzle_and_comes_back_after_an_ordinary_one(
    client: TestClient,
):
    """At most every other puzzle is focused, worked out from the stored attempts alone."""
    player = uuid.uuid4()
    headers = as_player(player)
    store_first_tries(client, player, [(1, False), (1, False)])
    assert get_next(client, player)["focus"] == "ADD_VISIBLE"

    # The game plays the focused puzzle it was told to.
    focused = client.post(
        f"{PUZZLES}/missing-number",
        json={"level": 1, "length": 2, "focus": "ADD_VISIBLE"},
        headers=headers,
    ).json()
    assert "-av-" in focused["puzzle_id"]
    puzzle = internal(client, focused["puzzle_id"])
    # Asked again before anything was answered: nothing has changed yet.
    assert get_next(client, player)["focus"] == "ADD_VISIBLE"
    check(client, puzzle.puzzle_id, 0, puzzle.steps[0].answer, player)

    after_focused = get_next(client, player)
    assert after_focused["focus_rule"] == "ADD_VISIBLE"  # still noticed
    assert after_focused["focus"] is None  # but not two in a row
    assert "so the next one is an ordinary one" in after_focused["reason"]

    # An ordinary puzzle next, and then the focus is offered again.
    plain = internal(client, new_puzzle(client, level=1, length=2, seed=77)["puzzle_id"])
    check(client, plain.puzzle_id, 0, plain.steps[0].answer, player)
    assert get_next(client, player)["focus"] == "ADD_VISIBLE"


def test_focus_is_released_once_the_mistake_stops(client: TestClient):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, False), (1, False)])
    assert get_next(client, player)["focus"] == "ADD_VISIBLE"

    store_first_tries(client, player, [(1, True)] * 8, start_minute=10)

    body = get_next(client, player)
    assert body["focus_rule"] is None
    assert body["focus"] is None


def test_a_mistake_the_generator_cannot_target_is_reported_but_never_a_focus(
    client: TestClient,
):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, False), (1, False)], rule="OFF_BY_ONE_OVER")

    body = get_next(client, player)

    assert body["focus_rule"] == "OFF_BY_ONE_OVER"
    assert body["focus"] is None


def test_next_with_a_focus_still_uses_three_statements(client: TestClient):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, False)] * 3)

    with count_statements(client) as seen:
        assert get_next(client, player)["focus"] == "ADD_VISIBLE"
    assert len(seen) == 3, seen


# ---- POST /puzzles/missing-number with a focus ----


@pytest.mark.parametrize(
    ("focus", "code"),
    [("ADD_VISIBLE", "av"), ("ANSWER_LEFT_BACKWARDS", "ab"), ("POSITION_CONFUSION", "pc")],
)
def test_a_new_puzzle_can_be_focused_and_does_not_say_so(client: TestClient, focus, code):
    response = client.post(
        f"{PUZZLES}/missing-number", json={"level": 2, "length": 3, "seed": 9, "focus": focus}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert f"-{code}-" in body["puzzle_id"]
    # The public puzzle has the same keys as ever, and no rule name anywhere.
    assert set(body) == {"puzzle_id", "level", "length", "topic_ids", "steps"}
    assert "focus" not in response.text
    assert focus not in response.text
    puzzle = internal(client, body["puzzle_id"])
    assert puzzle.focus is not None and puzzle.focus.value == focus
    # It is rebuilt from its id like any other puzzle, and plays the same way.
    assert client.get(f"{PUZZLES}/{body['puzzle_id']}").json() == body
    assert check(client, body["puzzle_id"], 0, puzzle.steps[0].answer)["correct"] is True
    hint = client.get(f"{PUZZLES}/{body['puzzle_id']}/steps/0/hints/1").json()
    assert hint["text"] == puzzle.steps[0].hints[0]


def test_focus_null_or_missing_is_an_ordinary_puzzle(client: TestClient):
    plain = new_puzzle(client, level=1, length=3, seed=4)

    with_null = client.post(
        f"{PUZZLES}/missing-number", json={"level": 1, "length": 3, "seed": 4, "focus": None}
    )

    assert with_null.status_code == 201
    assert with_null.json() == plain
    assert len(plain["puzzle_id"].split("-")) == 6


def test_a_rule_name_that_cannot_be_targeted_is_accepted_and_changes_nothing(client: TestClient):
    plain = new_puzzle(client, level=1, length=3, seed=4)

    for rule in ("OFF_BY_ONE_OVER", "OFF_BY_ONE_UNDER", "PLACE_VALUE_SLIP", "NEAR_MISS"):
        response = client.post(
            f"{PUZZLES}/missing-number", json={"level": 1, "length": 3, "seed": 4, "focus": rule}
        )
        assert response.status_code == 201, rule
        assert response.json() == plain


@pytest.mark.parametrize("bad", ["add_visible", "ADD", "EVERYTHING", "", 7, ["ADD_VISIBLE"]])
def test_an_unknown_focus_is_422(client: TestClient, bad):
    response = client.post(f"{PUZZLES}/missing-number", json={"level": 1, "focus": bad})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "focus"]


def test_a_focused_id_with_a_tampered_code_is_404(client: TestClient):
    focused = client.post(
        f"{PUZZLES}/missing-number", json={"level": 1, "length": 3, "focus": "ADD_VISIBLE"}
    ).json()["puzzle_id"]

    for bad in (focused.replace("-av-", "-pc-"), focused.replace("-av-", "-zz-")):
        response = client.get(f"{PUZZLES}/{bad}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Puzzle not found", "puzzle_id": bad}


def test_the_new_puzzle_route_documents_focus(client: TestClient):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert "focus" in schemas["NewPuzzleRequest"]["properties"]
    assert "focus" in schemas["NextPuzzle"]["properties"]
    assert "focus" not in schemas["PuzzlePublic"]["properties"]
    assert set(schemas["MistakeRule"]["enum"]) >= {
        "ADD_VISIBLE",
        "ANSWER_LEFT_BACKWARDS",
        "POSITION_CONFUSION",
    }
