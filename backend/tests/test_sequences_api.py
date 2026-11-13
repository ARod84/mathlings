""" "Next in Line" through the generic routes: the contract, with the real type.

generate -> verify -> serve -> check -> hint, attempts, /next, ids, and the
one thing this type needed from the framework: answers below zero.
"""

import re
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import get_settings
from app.db import make_engine
from app.puzzles.core.taxonomy_link import topic_exists
from app.puzzles.types.missing_number import MissingNumberChains
from app.puzzles.types.sequences import NumberSequences
from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import (
    GENERATOR_VERSION,
    LEVELS,
    MAX_ANSWER,
    MIN_ANSWER,
    TOPIC_GENERALISING,
    TOPIC_GROWING_PATTERNS,
    TOPIC_LINEAR_SEQUENCES,
    TOPIC_NEGATIVE_NUMBERS,
    TOPIC_SKIP_COUNTING,
)
from app.puzzles.types.sequences.misconceptions import resolve_catalog
from app.puzzles.types.sequences.models import MistakeRule, SequencePuzzle
from app.puzzles.types.sequences.verified import generate_verified, regenerate
from app.puzzles.types.sequences.verifier import verify
from app.taxonomy.importer import run_import
from app.taxonomy.service import TaxonomyService, reload_graph
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.test_api import api_client, count_statements
from tests.test_players import PLAYERS, as_player, attempts_of

PUZZLES = "/api/v1/puzzles"
NEXT = f"{PLAYERS}/me/next"
TEMPERATURE = {"id": "mt_RVK655t391", "name": "Measuring temperature"}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The real app, with the real registry, on the puzzle fixture taxonomy."""
    database_path = tmp_path_factory.mktemp("sequences") / "sequences.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def new_sequence(client: TestClient, **body) -> dict:
    response = client.post(f"{PUZZLES}/sequences", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def sequences(client: TestClient) -> NumberSequences:
    return client.app.state.puzzles.require("sequences")


def internal(client: TestClient, puzzle_id: str) -> SequencePuzzle:
    """The full server-side puzzle behind an id, for working out expected values."""
    kind = sequences(client)
    return regenerate(puzzle_id, catalog=kind.catalog, topic_exists=kind._topic_exists)


def check(client: TestClient, puzzle_id: str, step: int, answer: int, player=None):
    return client.post(
        f"{PUZZLES}/{puzzle_id}/steps/{step}/check",
        json={"answer": answer},
        headers=as_player(player) if player else None,
    )


def find(client: TestClient, level: int, wanted) -> SequencePuzzle:
    """The first puzzle of a level that `wanted` accepts."""
    for seed in range(400):
        puzzle = internal(client, new_sequence(client, level=level, seed=seed)["puzzle_id"])
        if wanted(puzzle):
            return puzzle
    raise AssertionError("no such puzzle in 400 seeds")


def through_zero(puzzle: SequencePuzzle) -> bool:
    return puzzle.kind == "constant" and puzzle.steps[-1].answer < 0


# ---- generate, verify, serve ----


def test_the_generic_route_makes_a_verified_sequence_at_every_level(client: TestClient):
    for level in LEVELS:
        for seed in range(25):
            body = new_sequence(client, level=level, seed=seed)

            assert set(body) == {
                "game",
                "puzzle_id",
                "level",
                "length",
                "topic_ids",
                "terms",
                "steps",
            }
            assert body["game"] == "sequences"
            assert body["puzzle_id"] == make_sequence_id(GENERATOR_VERSION, level, seed)
            assert body["level"] == level
            assert 5 <= len(body["terms"]) <= 6
            assert body["length"] == len(body["steps"]) == body["terms"].count(None)
            assert body["terms"][0] is not None
            for index, step in enumerate(body["steps"]):
                assert set(step) == {"index", "position", "options", "hint_tiers"}
                assert (step["index"], step["hint_tiers"]) == (index, 3)
                assert body["terms"][step["position"]] is None
                assert len(set(step["options"])) == 4

            puzzle = internal(client, body["puzzle_id"])
            kind = sequences(client)
            assert verify(puzzle, catalog=kind.catalog, topic_exists=kind._topic_exists).ok
            assert [t for t in body["terms"] if t is not None] == [
                term for position, term in enumerate(puzzle.terms) if position not in puzzle.blanks
            ]


def test_the_same_seed_gives_the_same_puzzle_and_get_rebuilds_it(client: TestClient):
    first = new_sequence(client, level=3, seed=77)

    assert new_sequence(client, level=3, seed=77) == first
    assert new_sequence(client, level=3, seed=78) != first
    response = client.get(f"{PUZZLES}/{first['puzzle_id']}")
    assert response.status_code == 200
    assert response.json() == first
    assert len({new_sequence(client, level=2)["puzzle_id"] for _ in range(5)}) == 5


def test_the_public_puzzle_gives_nothing_away(client: TestClient):
    for level in LEVELS:
        for seed in range(20):
            response = client.post(f"{PUZZLES}/sequences", json={"level": level, "seed": seed})
            text = response.text
            for forbidden in (
                '"answer"',
                "rule",
                "error_pattern",
                "hint_source",
                "distractor",
                '"hints"',
                "next_move",
                '"seed"',
                '"kind"',
                "generator_version",
            ):
                assert forbidden not in text, forbidden
            for rule in MistakeRule:
                assert rule.value not in text
            puzzle = internal(client, response.json()["puzzle_id"])
            for step in puzzle.steps:
                for hint in step.hints:
                    assert hint not in text


@pytest.mark.parametrize(
    "body",
    [{}, {"level": 0}, {"level": 4}, {"level": 1, "seed": -1}, {"level": 1, "length": 2}, [1]],
)
def test_bad_new_puzzle_bodies_are_422(client: TestClient, body):
    # `length` is a chain's parameter. A sequence has none of its own.
    assert client.post(f"{PUZZLES}/sequences", json=body).status_code == 422


# ---- check ----


def test_right_answers_walk_the_blanks_in_order(client: TestClient):
    puzzle = find(client, 2, lambda p: len(p.steps) == 2)

    first = check(client, puzzle.puzzle_id, 0, puzzle.steps[0].answer).json()
    second = check(client, puzzle.puzzle_id, 1, puzzle.steps[1].answer).json()

    assert first == {
        "correct": True,
        "feedback": "correct",
        "diagnosis": {"matched_rules": [], "unrecognized": False, "reteach_topic": None},
        "next_step": 1,
    }
    assert (second["correct"], second["next_step"]) == (True, None)


def test_a_negative_answer_is_accepted_and_can_be_right(client: TestClient):
    puzzle = find(client, 3, through_zero)
    step = len(puzzle.steps) - 1
    answer = puzzle.steps[step].answer
    assert answer < 0

    response = check(client, puzzle.puzzle_id, step, answer)

    assert response.status_code == 200, response.text
    assert response.json()["correct"] is True


def test_stopping_at_zero_is_named_with_its_pattern_topic(client: TestClient):
    puzzle = find(client, 3, through_zero)
    step = len(puzzle.steps) - 1

    body = check(client, puzzle.puzzle_id, step, 0).json()

    assert body["correct"] is False
    assert body["feedback"] == "try_again"
    assert body["diagnosis"]["matched_rules"][0] == "STOPS_AT_ZERO"
    assert body["diagnosis"]["unrecognized"] is False
    # From the taxonomy error pattern on linear sequences: step back to temperature.
    assert body["diagnosis"]["reteach_topic"] == TEMPERATURE
    assert body["next_step"] is None


def test_dropping_the_sign_is_recognised(client: TestClient):
    puzzle = find(client, 3, through_zero)
    step = len(puzzle.steps) - 1

    body = check(client, puzzle.puzzle_id, step, -puzzle.steps[step].answer).json()

    assert body["correct"] is False
    assert "SIGN_DROPPED" in body["diagnosis"]["matched_rules"]
    # Its pattern names no topic, so the step back is the prerequisite graph's
    # first choice for linear sequences, whatever that is in this taxonomy.
    graph = client.app.state.graph
    expected = graph.step_back_candidates(TOPIC_LINEAR_SEQUENCES)[0].topic_id
    assert body["diagnosis"]["reteach_topic"]["id"] == expected
    assert body["diagnosis"]["reteach_topic"]["name"]


def test_a_wrong_check_never_says_the_answer(client: TestClient):
    for seed in range(20):
        puzzle = internal(client, new_sequence(client, level=3, seed=seed)["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            for distractor in step.distractors:
                response = check(client, puzzle.puzzle_id, index, distractor.value)
                assert response.json()["correct"] is False
                assert set(response.json()) == {"correct", "feedback", "diagnosis", "next_step"}
                # Nothing in the body is a number at all, so the answer cannot be there.
                diagnosis = response.json()["diagnosis"]
                assert response.json()["next_step"] is None
                assert all(isinstance(rule, str) for rule in diagnosis["matched_rules"])
                assert set(diagnosis) == {"matched_rules", "unrecognized", "reteach_topic"}


# ---- answer bounds belong to the type ----


def test_sequences_accept_answers_from_minus_1000_to_10000(client: TestClient):
    puzzle_id = new_sequence(client, level=3, seed=5)["puzzle_id"]
    assert (NumberSequences.answer_min, NumberSequences.answer_max) == (-1000, 10_000)
    assert (MIN_ANSWER, MAX_ANSWER) == (-1000, 10_000)

    for inside in (-1000, -1, 0, 10_000):
        assert check(client, puzzle_id, 0, inside).status_code == 200, inside
    for outside in (-1001, 10_001, -(10**9)):
        response = check(client, puzzle_id, 0, outside)
        assert response.status_code == 422, outside
        assert response.json() == {
            "detail": [
                {
                    "type": "answer_out_of_bounds",
                    "loc": ["body", "answer"],
                    "msg": "Input should be between -1000 and 10000",
                    "input": outside,
                    "ctx": {"ge": -1000, "le": 10000},
                }
            ]
        }


def test_a_negative_answer_to_a_chain_is_still_422(client: TestClient):
    chain = client.post(f"{PUZZLES}/missing-number", json={"level": 1, "seed": 6}).json()
    assert (MissingNumberChains.answer_min, MissingNumberChains.answer_max) == (0, 10_000)

    for outside in (-1, -3, 10_001):
        response = check(client, chain["puzzle_id"], 0, outside)
        assert response.status_code == 422, outside
        assert response.json()["detail"][0]["msg"] == "Input should be between 0 and 10000"
        assert response.json()["detail"][0]["loc"] == ["body", "answer"]
    assert check(client, chain["puzzle_id"], 0, 0).status_code == 200
    assert check(client, chain["puzzle_id"], 0, 10_000).status_code == 200


def test_an_out_of_bounds_answer_stores_nothing_and_is_not_logged_as_a_check(
    client: TestClient, caplog
):
    player = uuid.uuid4()
    puzzle_id = new_sequence(client, level=3, seed=5)["puzzle_id"]

    with caplog.at_level("INFO", logger="app.puzzles.checks"):
        assert check(client, puzzle_id, 0, -5000, player).status_code == 422

    assert attempts_of(client, player) == []
    assert not [r for r in caplog.records if r.name == "app.puzzles.checks"]


@pytest.mark.parametrize("body", [{}, {"answer": "six"}, {"answer": 2.5}, {"a": 1}])
def test_other_bad_check_bodies_are_422(client: TestClient, body):
    puzzle_id = new_sequence(client, level=1, seed=6)["puzzle_id"]
    response = client.post(f"{PUZZLES}/{puzzle_id}/steps/0/check", json=body)
    assert response.status_code == 422


def test_the_bounds_of_a_type_cover_every_option_it_can_offer():
    for spec in LEVELS.values():
        assert spec.option_min >= MIN_ANSWER and spec.option_max <= MAX_ANSWER


# ---- hints ----


def test_hint_tiers(client: TestClient):
    for level in LEVELS:
        for seed in range(12):
            puzzle = internal(client, new_sequence(client, level=level, seed=seed)["puzzle_id"])
            for index, step in enumerate(puzzle.steps):
                texts = []
                for tier in (1, 2, 3):
                    response = client.get(
                        f"{PUZZLES}/{puzzle.puzzle_id}/steps/{index}/hints/{tier}"
                    )
                    assert response.status_code == 200
                    assert response.json() == {"tier": tier, "text": step.hints[tier - 1]}
                    texts.append(response.json()["text"])
                assert texts[0] == "Look at how much each number changes from one to the next."
                # The answer, written as a child would read it, is only in the last tier.
                shown = f"−{-step.answer}" if step.answer < 0 else str(step.answer)
                pattern = rf"(?<![\d−-]){re.escape(shown)}(?!\d)"
                assert not re.search(pattern, texts[1]), (texts[1], shown)
                assert re.search(pattern, texts[2]), (texts[2], shown)

    puzzle_id = new_sequence(client, level=1, seed=3)["puzzle_id"]
    for tier in (0, 4):
        missing = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/{tier}")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Hint tier not found: tiers are 1 to 3", "tier": tier}
    # Level 1 has one blank, so one step.
    assert client.get(f"{PUZZLES}/{puzzle_id}/steps/1/hints/1").status_code == 404
    assert check(client, puzzle_id, 1, 5).status_code == 404


# ---- attempts ----


def test_an_attempt_stores_the_kind_of_sequence_and_the_topics_of_that_kind(client: TestClient):
    player = uuid.uuid4()
    zero = find(client, 3, through_zero)
    growing = find(client, 3, lambda p: p.kind == "growing")
    skip = find(client, 2, lambda p: True)
    last = len(zero.steps) - 1

    check(client, zero.puzzle_id, last, 0, player)
    check(client, growing.puzzle_id, 0, growing.steps[0].answer, player)
    check(client, skip.puzzle_id, 0, skip.steps[0].answer, player)

    stopped, grew, counted = attempts_of(client, player)
    assert (stopped.game, stopped.level, stopped.step_index) == ("sequences", 3, last)
    assert stopped.generator_version == GENERATOR_VERSION
    assert stopped.details == {
        "kind": "constant",
        "position": zero.steps[last].position,
        "terms": len(zero.terms),
    }
    assert stopped.form is None
    assert stopped.topic_ids == [TOPIC_LINEAR_SEQUENCES, TOPIC_NEGATIVE_NUMBERS]
    assert (stopped.correct, stopped.answer) == (False, 0)
    assert stopped.matched_rules[0] == "STOPS_AT_ZERO"
    assert stopped.error_pattern_ids[0] == f"{TOPIC_LINEAR_SEQUENCES}#0"
    assert stopped.reteach_topic_id == TEMPERATURE["id"]

    assert grew.details["kind"] == "growing"
    assert grew.topic_ids == [TOPIC_GENERALISING, TOPIC_GROWING_PATTERNS]
    assert (grew.correct, grew.matched_rules, grew.error_pattern_ids) == (True, [], [])
    assert counted.topic_ids == [TOPIC_SKIP_COUNTING, TOPIC_GROWING_PATTERNS]


def test_a_negative_answer_is_stored_as_it_was_given(client: TestClient):
    player = uuid.uuid4()
    puzzle = find(client, 3, through_zero)
    step = len(puzzle.steps) - 1

    check(client, puzzle.puzzle_id, step, puzzle.steps[step].answer, player)

    (attempt,) = attempts_of(client, player)
    assert attempt.answer == puzzle.steps[step].answer < 0
    assert attempt.correct is True
    summary = client.get(f"{PLAYERS}/me/summary", headers=as_player(player)).json()
    assert summary["totals"] == {**summary["totals"], "attempts": 1, "correct": 1}
    assert {topic["topic_id"] for topic in summary["topics"]} == {
        TOPIC_LINEAR_SEQUENCES,
        TOPIC_NEGATIVE_NUMBERS,
    }


def test_without_a_player_nothing_is_stored(client: TestClient):
    with Session(client.app.state.engine) as session:
        before = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()

    puzzle_id = new_sequence(client, level=1, seed=4)["puzzle_id"]
    check(client, puzzle_id, 0, 1)
    client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/2")

    with Session(client.app.state.engine) as session:
        after = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()
    assert after == before


# ---- /next: no policy yet ----


def test_next_for_sequences_is_the_default_with_no_policy(client: TestClient):
    player = uuid.uuid4()
    puzzle = find(client, 3, through_zero)
    check(client, puzzle.puzzle_id, 0, 0, player)

    with count_statements(client) as seen:
        response = client.get(NEXT, params={"game": "sequences"}, headers=as_player(player))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "level": 1,
        "length": None,
        "reason_code": "no_policy",
        "reason": "sequences has no recommendation policy yet, so this is its default: "
        "level 1 with the game's default settings.",
        "focus_rule": None,
        "focus": None,
        "params": {},
        "mastery": [],
    }
    assert len(seen) == 1, seen
    # What it recommends is a body the route takes as it is.
    body = {"level": response.json()["level"], **response.json()["params"]}
    assert client.post(f"{PUZZLES}/sequences", json=body).status_code == 201


def test_sequence_attempts_do_not_move_the_chain_recommendation(client: TestClient):
    player = uuid.uuid4()
    puzzle = find(client, 2, lambda p: True)
    check(client, puzzle.puzzle_id, 0, puzzle.steps[0].answer, player)

    body = client.get(NEXT, params={"game": "missing-number"}, headers=as_player(player)).json()

    assert (body["reason_code"], body["level"], body["length"]) == ("cold_start", 1, 2)


# ---- ids ----


def test_tampered_ids_are_404(client: TestClient):
    good = new_sequence(client, level=1, seed=6)["puzzle_id"]
    other_level = good.replace("seq-1-1-", "seq-1-2-")  # another level under the old checksum
    wrong_checksum = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
    impossible = make_sequence_id(GENERATOR_VERSION, 9, 6)

    for bad in (other_level, wrong_checksum, impossible, "seq-1-1"):
        for response in (
            client.get(f"{PUZZLES}/{bad}"),
            check(client, bad, 0, 1),
            client.get(f"{PUZZLES}/{bad}/steps/0/hints/1"),
        ):
            assert response.status_code == 404, bad
            assert response.json() == {"detail": "Puzzle not found", "puzzle_id": bad}


def test_an_id_from_an_older_version_is_410_and_from_an_unknown_one_404(client: TestClient):
    older = make_sequence_id("0", 1, 6)
    for response in (
        client.get(f"{PUZZLES}/{older}"),
        check(client, older, 0, 1),
        client.get(f"{PUZZLES}/{older}/steps/0/hints/1"),
    ):
        assert response.status_code == 410
        # The sequence generator's own version, not the chain generator's.
        assert response.json() == {
            "detail": "Puzzle version is no longer available",
            "current_version": GENERATOR_VERSION,
        }
    assert client.get(f"{PUZZLES}/{make_sequence_id('7', 1, 6)}").status_code == 404


# ---- the document ----


def test_openapi_has_both_games_told_apart_by_game(client: TestClient):
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    new_puzzle = document["paths"]["/api/v1/puzzles/{game}"]["post"]

    for operation in (new_puzzle, document["paths"]["/api/v1/puzzles/{puzzle_id}"]["get"]):
        success = "201" if "201" in operation["responses"] else "200"
        schema = operation["responses"][success]["content"]["application/json"]["schema"]
        assert schema["discriminator"] == {
            "propertyName": "game",
            "mapping": {
                "missing-number": "#/components/schemas/PuzzlePublic",
                "sequences": "#/components/schemas/SequencePublic",
            },
        }
    assert new_puzzle["requestBody"]["content"]["application/json"]["schema"] == {
        "oneOf": [
            {"$ref": "#/components/schemas/NewPuzzleRequest"},
            {"$ref": "#/components/schemas/NewSequenceRequest"},
        ]
    }
    assert set(schemas["NewSequenceRequest"]["properties"]) == {"level", "seed"}
    assert schemas["SequencePublic"]["properties"]["game"]["const"] == "sequences"
    assert schemas["SequencePublic"]["properties"]["terms"]["items"] == {
        "anyOf": [{"type": "integer"}, {"type": "null"}]
    }
    # The answer bounds are the type's, so they are no longer in the schema.
    answer = schemas["CheckRequest"]["properties"]["answer"]
    assert "minimum" not in answer and "maximum" not in answer
    assert "-1000 to 10000 for sequences" in answer["description"]
    parameters = document["paths"][NEXT]["get"]["parameters"]
    game = next(p for p in parameters if p["name"] == "game")
    assert game["schema"]["enum"] == ["missing-number", "sequences"]


# ---- the real taxonomy ----


@pytest.mark.slow
def test_the_rule_catalog_resolves_against_the_real_database():
    if not get_settings().database_path.is_file():
        pytest.skip("no database; run the migration and the importer first")
    engine = make_engine()
    with Session(engine) as session:
        service = TaxonomyService(session, reload_graph(session))
        if TOPIC_LINEAR_SEQUENCES not in service.graph:
            engine.dispose()
            pytest.skip("the real taxonomy is not imported")
        catalog = resolve_catalog(service.get_error_patterns)
        exists = topic_exists(service)
        names = {
            topic_id: summary.name
            for topic_id, summary in service.get_summaries(
                [
                    topic
                    for spec in LEVELS.values()
                    for kind in spec.topic_ids.values()
                    for topic in kind
                ]
            ).items()
        }
    engine.dispose()

    table = [
        (
            rule.value,
            pattern.error_pattern_id if pattern else None,
            pattern and pattern.reteach_topic_id,
        )
        for rule, pattern in catalog.table()
    ]
    assert table == [
        ("STOPS_AT_ZERO", "mt_hBZwbst0ow#0", "mt_RVK655t391"),
        ("STOPS_AT_ZERO", "mt_vXRzMbiPff#1", "mt_M2v1A9OEuM"),
        ("SIGN_DROPPED", "mt_hBZwbst0ow#1", None),
        ("WRONG_DIRECTION", "mt_hBZwbst0ow#4", None),
        ("BOUNDARY_SLIP", "mt_IzQvs7k_sE#2", None),
        ("CONSTANT_GAP", "mt_fZTn0W_iZR#2", None),
        ("COUNT_BY_ONE", None, None),
        ("SKIPPED_TERM", None, None),
        ("OFF_BY_ONE_OVER", None, None),
        ("OFF_BY_ONE_UNDER", None, None),
        ("NEAR_MISS", None, None),
    ]
    assert names == {
        TOPIC_GROWING_PATTERNS: "Describing growing number patterns",
        TOPIC_SKIP_COUNTING: "Skip Counting (4s, 8s, 50s, 100s)",
        TOPIC_LINEAR_SEQUENCES: "Linear number sequences",
        TOPIC_NEGATIVE_NUMBERS: "Negative Numbers",
        TOPIC_GENERALISING: "Generalising Patterns",
    }
    # And with the real catalog, real puzzles verify at every level.
    for level in LEVELS:
        for seed in range(300):
            puzzle = generate_verified(seed, level, catalog=catalog, topic_exists=exists)
            assert verify(puzzle, catalog=catalog, topic_exists=exists).ok
