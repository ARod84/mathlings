"""The proof that the puzzle framework carries a second type.

A dummy type (tests/puzzles/dummy.py: "type the number shown") is registered
next to the real ones, and played through the generic routes. No test here
asks a missing-number chain for anything except to still be there: whatever
passes, passes because of app/puzzles/core, the registry, the shared service
and the shared routes.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.main import create_app
from app.puzzles.core import GenerationError
from app.puzzles.core.ids import make_id, split_id
from app.puzzles.core.verified import (
    PuzzleGenerationFailed,
    generate_verified,
    generate_verified_outcome,
    regenerate,
)
from app.puzzles.registry import PuzzleRegistry, UnknownGame, default_registry
from app.puzzles.service import PuzzleService
from app.taxonomy.graph import PrerequisiteGraph
from app.taxonomy.importer import run_import
from app.taxonomy.service import TaxonomyService
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.puzzles.dummy import (
    DUMMY_TOPIC,
    ONE_MORE,
    DummyParams,
    DummyPuzzle,
    DummyType,
    UnloadableDummyType,
    dummy_id,
)
from tests.test_api import count_statements
from tests.test_players import HEADER, PLAYERS, as_player, attempts_of

PUZZLES = "/api/v1/puzzles"
# Whatever the real app serves, then the two test types the fixture adds.
REAL_GAMES = default_registry().games
ALL_GAMES = [*REAL_GAMES, "dummy", "dummy-unloadable"]
NEXT = f"{PLAYERS}/me/next"


@pytest.fixture(scope="module")
def registry() -> PuzzleRegistry:
    """The real types, plus the dummy and a dummy that can never load."""
    registry = default_registry()
    registry.register(DummyType)
    registry.register(UnloadableDummyType)
    return registry


@pytest.fixture(scope="module")
def client(
    tmp_path_factory: pytest.TempPathFactory, registry: PuzzleRegistry
) -> Iterator[TestClient]:
    database_path = tmp_path_factory.mktemp("contract") / "contract.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    app = create_app(
        Settings(_env_file=None, database_path=database_path),
        graph=PrerequisiteGraph(),
        registry=registry,
    )
    with TestClient(app) as test_client:
        yield test_client


def new_dummy(client: TestClient, **body) -> dict:
    response = client.post(f"{PUZZLES}/dummy", json={"level": 1, **body})
    assert response.status_code == 201, response.text
    return response.json()


def dummy_type(client: TestClient) -> DummyType:
    return client.app.state.puzzles.require("dummy")


def internal(client: TestClient, puzzle_id: str) -> DummyPuzzle:
    """The server-side puzzle behind an id."""
    return regenerate(dummy_type(client), split_id(puzzle_id), puzzle_id)


def check(client: TestClient, puzzle_id: str, answer: int, player: uuid.UUID | None = None) -> dict:
    response = client.post(
        f"{PUZZLES}/{puzzle_id}/steps/0/check",
        json={"answer": answer},
        headers=as_player(player) if player else None,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---- generate, verify, serve ----


def test_the_generic_route_makes_a_verified_puzzle_of_the_dummy_type(client: TestClient):
    body = new_dummy(client, seed=5, digits=3)

    assert set(body) == {"game", "puzzle_id", "level", "shown", "hint_tiers"}
    assert body["game"] == "dummy"
    assert body["puzzle_id"].startswith("dum-2-1-3-")
    assert 100 <= body["shown"] <= 999

    puzzle = internal(client, body["puzzle_id"])
    assert dummy_type(client).verify(puzzle).ok
    assert puzzle.steps[0].shown == body["shown"]
    # The seed that built it is the one in its id, so the id alone rebuilds it.
    assert puzzle.puzzle_id == dummy_id("2", 1, 3, puzzle.seed) == body["puzzle_id"]


def test_the_same_seed_gives_the_same_puzzle_and_no_seed_gives_different_ones(client: TestClient):
    assert new_dummy(client, seed=11, digits=2) == new_dummy(client, seed=11, digits=2)
    assert new_dummy(client, seed=12, digits=2) != new_dummy(client, seed=11, digits=2)
    assert len({new_dummy(client, digits=3)["puzzle_id"] for _ in range(6)}) > 1


def test_the_type_default_parameters_are_used_when_none_are_sent(client: TestClient):
    assert new_dummy(client, seed=3)["puzzle_id"].startswith("dum-2-1-1-")
    assert 1 <= new_dummy(client, seed=3)["shown"] <= 9


def test_get_rebuilds_the_puzzle_and_finds_the_type_from_the_id(client: TestClient):
    created = new_dummy(client, seed=21, digits=2)

    response = client.get(f"{PUZZLES}/{created['puzzle_id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_a_seed_the_type_cannot_use_is_retried_with_a_derived_seed(client: TestClient):
    kind = dummy_type(client)
    # Find a seed whose first number ends in 9: the generator refuses it.
    seed = next(s for s in range(500) if _refused(kind, s))

    outcome = generate_verified_outcome(kind, seed, 1, DummyParams(digits=2))

    assert outcome.retries >= 1
    assert outcome.puzzle.seed != seed
    assert kind.verify(outcome.puzzle).ok
    # Through the route, the same request gives that same puzzle, under the seed that worked.
    served = new_dummy(client, seed=seed, digits=2)
    assert served["puzzle_id"] == outcome.puzzle.puzzle_id
    assert client.get(f"{PUZZLES}/{served['puzzle_id']}").json() == served


def _refused(kind: DummyType, seed: int) -> bool:
    try:
        kind.generate(seed, 1, DummyParams(digits=2))
    except GenerationError:
        return True
    return False


def test_a_puzzle_that_fails_verification_never_comes_out(client: TestClient):
    # A dummy whose taxonomy has lost its topic: every puzzle it makes fails verification.
    broken = DummyType(lambda _topic_id: False)

    with pytest.raises(PuzzleGenerationFailed, match=r"dummy.*unknown_topic"):
        generate_verified(broken, 1, 1, max_attempts=3)


def test_each_game_has_its_own_request_body(client: TestClient):
    # `length` belongs to chains, `digits` to the dummy. Neither takes the other's.
    assert client.post(f"{PUZZLES}/dummy", json={"level": 1, "length": 2}).status_code == 422
    chain = client.post(f"{PUZZLES}/missing-number", json={"level": 1, "digits": 2})
    assert chain.status_code == 422

    for body in ({}, {"level": 2}, {"level": 1, "digits": 4}, {"level": 1, "seed": -1}, [1]):
        response = client.post(f"{PUZZLES}/dummy", json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"][0]["loc"][0] == "body"
    not_json = client.post(
        f"{PUZZLES}/dummy", content=b"{level", headers={"content-type": "application/json"}
    )
    assert not_json.status_code == 422


def test_an_unknown_game_is_404_with_a_clear_detail(client: TestClient):
    # 404 whatever the body is: the game is looked up first.
    for body in ({"level": 1}, {}, {"anything": True}):
        response = client.post(f"{PUZZLES}/sudoku", json=body)

        assert response.status_code == 404
        assert response.json() == {
            "detail": f"Unknown game: sudoku. Known games: {', '.join(ALL_GAMES)}.",
            "game": "sudoku",
            "games": ALL_GAMES,
        }


# ---- check and hint ----


def test_check_right_wrong_with_a_known_mistake_and_wrong_without(client: TestClient):
    created = new_dummy(client, seed=8, digits=2)
    shown = created["shown"]

    assert check(client, created["puzzle_id"], shown) == {
        "correct": True,
        "feedback": "correct",
        "diagnosis": {"matched_rules": [], "unrecognized": False, "reteach_topic": None},
        # One step: there is no next one.
        "next_step": None,
    }
    assert check(client, created["puzzle_id"], shown + 1) == {
        "correct": False,
        "feedback": "try_again",
        "diagnosis": {"matched_rules": [ONE_MORE], "unrecognized": False, "reteach_topic": None},
        "next_step": None,
    }
    assert check(client, created["puzzle_id"], shown + 5)["diagnosis"] == {
        "matched_rules": [],
        "unrecognized": True,
        "reteach_topic": None,
    }


def test_hint_and_the_tier_and_step_limits_the_type_declares(client: TestClient):
    created = new_dummy(client, seed=8, digits=2)
    puzzle_id = created["puzzle_id"]

    hint = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/1")
    assert hint.status_code == 200
    assert hint.json() == {
        "tier": 1,
        "text": f"Type the number you can see: {created['shown']}.",
    }

    # The dummy has one tier and one step; chains have three and up to four.
    for tier in (0, 2):
        missing = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/{tier}")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Hint tier not found: tiers are 1 to 1", "tier": tier}
    for response in (
        client.get(f"{PUZZLES}/{puzzle_id}/steps/1/hints/1"),
        client.post(f"{PUZZLES}/{puzzle_id}/steps/1/check", json={"answer": 1}),
    ):
        assert response.status_code == 404
        assert response.json()["detail"] == "Step not found: this puzzle has steps 0 to 0"


# ---- attempts ----


def test_attempts_store_the_types_own_details(client: TestClient):
    player = uuid.uuid4()
    created = new_dummy(client, seed=14, digits=3)
    shown = created["shown"]

    client.get(f"{PUZZLES}/{created['puzzle_id']}/steps/0/hints/1", headers=as_player(player))
    check(client, created["puzzle_id"], shown + 1, player)
    check(client, created["puzzle_id"], shown, player)

    wrong, right = attempts_of(client, player)
    assert (wrong.game, wrong.level, wrong.step_index) == ("dummy", 1, 0)
    assert (wrong.puzzle_id, wrong.generator_version) == (created["puzzle_id"], "2")
    assert wrong.details == right.details == {"shown": shown, "digits": 3}
    # The old chain-only column stays empty for a type that has no form.
    assert wrong.form is None and right.form is None
    assert wrong.topic_ids == [DUMMY_TOPIC]
    assert (wrong.correct, wrong.matched_rules, wrong.answer) == (False, [ONE_MORE], shown + 1)
    assert (wrong.error_pattern_ids, wrong.reteach_topic_id) == ([], None)
    assert (wrong.attempt_on_step, wrong.hint_tier_before) == (1, 1)
    assert (right.correct, right.matched_rules, right.attempt_on_step) == (True, [], 2)


def test_without_a_player_nothing_is_stored(client: TestClient):
    created = new_dummy(client, seed=15)
    with Session(client.app.state.engine) as session:
        before = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()

    check(client, created["puzzle_id"], created["shown"])

    with Session(client.app.state.engine) as session:
        after = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()
    assert after == before


def test_the_summary_counts_the_dummy_attempts_under_their_topic(client: TestClient):
    player = uuid.uuid4()
    created = new_dummy(client, seed=16)
    check(client, created["puzzle_id"], created["shown"] + 1, player)

    summary = client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).json()

    assert summary["totals"]["attempts"] == 1
    assert [topic["topic_id"] for topic in summary["topics"]] == [DUMMY_TOPIC]
    assert summary["topics"][0]["top_mistakes"] == [{"rule": ONE_MORE, "count": 1}]
    # Mastery is still estimated from Missing Number Chains alone.
    assert summary["mastery"] == []


# ---- /next ----


def test_next_for_a_game_without_a_policy_is_its_default_with_no_policy(client: TestClient):
    player = uuid.uuid4()
    expected = {
        "level": 1,
        "length": None,
        "reason_code": "no_policy",
        "reason": "dummy has no recommendation policy yet, so this is its default: "
        "level 1 with the game's default settings.",
        "focus_rule": None,
        "focus": None,
        "params": {"digits": 1},
        "mastery": [],
    }

    response = client.get(NEXT, params={"game": "dummy"}, headers=as_player(player))
    assert response.status_code == 200, response.text
    assert response.json() == expected

    # It does not depend on what the player has done, in this game or another.
    created = new_dummy(client, seed=17)
    check(client, created["puzzle_id"], created["shown"], player)
    assert client.get(NEXT, params={"game": "dummy"}, headers=as_player(player)).json() == expected

    # What it recommends is a request the generic route accepts as it is.
    body = {"level": expected["level"], **expected["params"]}
    assert client.post(f"{PUZZLES}/dummy", json=body).status_code == 201


def test_next_without_a_policy_does_not_read_the_history(client: TestClient):
    with count_statements(client) as seen:
        client.get(NEXT, params={"game": "dummy"}, headers=as_player(uuid.uuid4()))
    # Only the taxonomy freshness check.
    assert len(seen) == 1, seen


def test_next_for_the_game_with_a_policy_is_unchanged_and_ignores_dummy_attempts(
    client: TestClient,
):
    player = uuid.uuid4()
    created = new_dummy(client, seed=18)
    check(client, created["puzzle_id"], created["shown"] + 1, player)

    body = client.get(NEXT, params={"game": "missing-number"}, headers=as_player(player)).json()

    # The player has dummy attempts only, so for chains this is still a cold start.
    assert (body["reason_code"], body["level"], body["length"]) == ("cold_start", 1, 2)
    assert body["params"] == {"length": 2}
    assert body["focus_rule"] is None


def test_next_rejects_a_game_nobody_registered(client: TestClient):
    response = client.get(NEXT, params={"game": "sudoku"}, headers={HEADER: str(uuid.uuid4())})
    assert response.status_code == 422


# ---- ids: tampered, old, unknown ----


def test_a_tampered_id_is_404(client: TestClient):
    good = new_dummy(client, seed=30, digits=2)["puzzle_id"]
    other_digits = good.replace("-1-2-", "-1-3-")  # another puzzle under the old checksum
    wrong_checksum = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
    impossible = dummy_id("2", 1, 9, 30)  # a real checksum, digits the type never makes
    unknown_level = dummy_id("2", 7, 1, 30)
    not_these_fields = make_id("dum", "2", ["1", "2", "3", "4"])
    no_such_type = make_id("zzz", "2", ["1", "1", "u"])

    for bad in (other_digits, wrong_checksum, impossible, unknown_level, not_these_fields):
        for response in (
            client.get(f"{PUZZLES}/{bad}"),
            client.post(f"{PUZZLES}/{bad}/steps/0/check", json={"answer": 1}),
            client.get(f"{PUZZLES}/{bad}/steps/0/hints/1"),
        ):
            assert response.status_code == 404, bad
            assert response.json() == {"detail": "Puzzle not found", "puzzle_id": bad}
    assert client.get(f"{PUZZLES}/{no_such_type}").status_code == 404


def test_an_id_from_an_older_version_is_410_with_the_types_own_current_version(
    client: TestClient,
):
    old = dummy_id("1", 1, 2, 30)

    for response in (
        client.get(f"{PUZZLES}/{old}"),
        client.post(f"{PUZZLES}/{old}/steps/0/check", json={"answer": 1}),
        client.get(f"{PUZZLES}/{old}/steps/0/hints/1"),
    ):
        assert response.status_code == 410
        # "2" is the dummy's version. The chain generator's is something else.
        assert response.json() == {
            "detail": "Puzzle version is no longer available",
            "current_version": "2",
        }


def test_an_id_from_a_version_the_type_never_had_is_404_not_410(client: TestClient):
    for version in ("3", "999", "beta"):
        assert client.get(f"{PUZZLES}/{dummy_id(version, 1, 2, 30)}").status_code == 404


# ---- a type that cannot load does not take the others down ----


def test_a_type_that_cannot_load_is_503_and_the_others_keep_working(client: TestClient):
    runtime = client.app.state.puzzles
    assert set(runtime.types) == {*REAL_GAMES, "dummy"}
    assert "mt_not_a_topic" in runtime.errors["dummy-unloadable"]

    response = client.post(f"{PUZZLES}/dummy-unloadable", json={"level": 1})
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]
    its_id = make_id("dmx", "2", ["1", "1", "u"])
    assert client.get(f"{PUZZLES}/{its_id}").status_code == 503

    assert client.post(f"{PUZZLES}/dummy", json={"level": 1}).status_code == 201
    chain = client.post(f"{PUZZLES}/missing-number", json={"level": 1})
    assert chain.status_code == 201
    assert chain.json()["game"] == "missing-number"


# ---- the registry ----


def test_the_registry_finds_types_by_game_and_by_id_prefix(registry: PuzzleRegistry):
    assert registry.games == ALL_GAMES
    assert registry.by_game("dummy") is DummyType
    assert registry.by_code("dum") is DummyType
    assert registry.by_code("nope") is None
    with pytest.raises(UnknownGame) as error:
        registry.by_game("sudoku")
    assert error.value.games == registry.games


def test_the_registry_refuses_a_second_type_with_the_same_code_or_game():
    registry = PuzzleRegistry([DummyType])

    class SameCode(DummyType):
        game = "another-game"

    class SameGame(DummyType):
        type_code = "oth"

    class BadCode(DummyType):
        type_code = "du-m"
        game = "third-game"

    for clash in (DummyType, SameCode, SameGame):
        with pytest.raises(ValueError, match="already registered"):
            registry.register(clash)
    with pytest.raises(ValueError, match="type_code"):
        registry.register(BadCode)
    assert registry.games == ["dummy"]


def test_the_real_app_knows_nothing_about_the_dummy():
    assert "missing-number" in REAL_GAMES
    assert not {"dummy", "dummy-unloadable"} & set(REAL_GAMES)
    assert default_registry().by_code("dum") is None


# ---- the service on its own ----


def test_the_service_serves_the_dummy_without_http(client: TestClient):
    with Session(client.app.state.engine) as session:
        taxonomy = TaxonomyService(session, client.app.state.graph)
        service = PuzzleService(taxonomy, client.app.state.puzzles)

        puzzle = service.new_puzzle("dummy", level=1, params=DummyParams(digits=2), seed=4)

        assert service.get_puzzle(puzzle.puzzle_id) == puzzle
        assert service.check(puzzle.puzzle_id, 0, puzzle.shown).correct is True
        assert service.hint(puzzle.puzzle_id, 0, 1).text.endswith(f"{puzzle.shown}.")
        with pytest.raises(UnknownGame):
            service.new_puzzle("sudoku", level=1)


# ---- the document ----


def test_openapi_tells_the_games_apart(client: TestClient):
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    new_puzzle = document["paths"]["/api/v1/puzzles/{game}"]["post"]

    # The response is one of the public shapes, discriminated by `game`.
    for operation in (new_puzzle, document["paths"]["/api/v1/puzzles/{puzzle_id}"]["get"]):
        success = "201" if "201" in operation["responses"] else "200"
        schema = operation["responses"][success]["content"]["application/json"]["schema"]
        assert schema["discriminator"]["propertyName"] == "game"
        mapping = schema["discriminator"]["mapping"]
        assert list(mapping) == ALL_GAMES
        assert mapping["missing-number"] == "#/components/schemas/PuzzlePublic"
        assert mapping["dummy"] == "#/components/schemas/DummyPublic"
        assert mapping["dummy-unloadable"] == "#/components/schemas/UnloadableDummyPublic"
    assert schemas["DummyPublic"]["properties"]["game"]["const"] == "dummy"

    # The request body is one of the games' request models, and each is in the document.
    body = new_puzzle["requestBody"]["content"]["application/json"]["schema"]
    # One per game, in order; the two dummies share a model, which is listed once.
    assert len(body["oneOf"]) == len(REAL_GAMES) + 1
    assert body["oneOf"][0] == {"$ref": "#/components/schemas/NewPuzzleRequest"}
    assert body["oneOf"][-1] == {"$ref": "#/components/schemas/DummyNewPuzzle"}
    for reference in body["oneOf"]:
        assert reference["$ref"].rsplit("/", 1)[-1] in schemas
    assert set(schemas["DummyNewPuzzle"]["properties"]) == {"level", "seed", "digits"}
    assert schemas["DummyNewPuzzle"]["additionalProperties"] is False
    assert "default" not in schemas["DummyNewPuzzle"]["properties"]["seed"]
    # A default that is a value stays: only a null one is dropped.
    assert schemas["DummyNewPuzzle"]["properties"]["digits"]["default"] == 1
    assert "404" in new_puzzle["responses"] and "422" in new_puzzle["responses"]

    # The first route stays, marked as deprecated.
    alias = document["paths"]["/api/v1/puzzles/missing-number"]["post"]
    assert alias["deprecated"] is True
    assert "deprecated" not in new_puzzle

    # /next lists every registered game.
    parameters = document["paths"][NEXT]["get"]["parameters"]
    game = next(p for p in parameters if p["name"] == "game")
    assert game["schema"]["enum"] == ALL_GAMES
