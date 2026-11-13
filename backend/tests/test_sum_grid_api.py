"""Sum Grid through the generic routes: the contract, with the real type.

generate -> verify -> serve -> check -> hint, attempts, /next and ids.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import get_settings
from app.db import make_engine
from app.puzzles.core.taxonomy_link import topic_exists
from app.puzzles.types.sum_grid import SumGrid
from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import (
    GENERATOR_VERSION,
    LEVELS,
    TOPIC_ADD_SUBTRACT_7,
    TOPIC_ADDING_WITHIN_100,
    TOPIC_FLUENT_WITHIN_20,
    TOPIC_THREE_SMALL_NUMBERS,
    TOPIC_UNKNOWN_ADD_SUB,
)
from app.puzzles.types.sum_grid.misconceptions import resolve_catalog
from app.puzzles.types.sum_grid.models import MistakeRule, SumGridPuzzle
from app.puzzles.types.sum_grid.rules import rule_output, step_view
from app.puzzles.types.sum_grid.verified import generate_verified, regenerate
from app.puzzles.types.sum_grid.verifier import verify
from app.taxonomy.importer import run_import
from app.taxonomy.service import TaxonomyService, reload_graph
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.test_api import api_client, count_statements
from tests.test_players import PLAYERS, as_player, attempts_of

PUZZLES = "/api/v1/puzzles"
NEXT = f"{PLAYERS}/me/next"
EQUALS_SIGN = {"id": "mt_oIzycTBeE4", "name": "What the equals sign means"}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The real app, with the real registry, on the puzzle fixture taxonomy."""
    database_path = tmp_path_factory.mktemp("sumgrid") / "sumgrid.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def new_grid(client: TestClient, **body) -> dict:
    response = client.post(f"{PUZZLES}/sum-grid", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def sum_grid(client: TestClient) -> SumGrid:
    return client.app.state.puzzles.require("sum-grid")


def internal(client: TestClient, puzzle_id: str) -> SumGridPuzzle:
    """The full server-side puzzle behind an id, for working out expected values."""
    kind = sum_grid(client)
    return regenerate(puzzle_id, catalog=kind.catalog, topic_exists=kind._topic_exists)


def check(client: TestClient, puzzle_id: str, step: int, answer: int, player=None):
    return client.post(
        f"{PUZZLES}/{puzzle_id}/steps/{step}/check",
        json={"answer": answer},
        headers=as_player(player) if player else None,
    )


def find_mistake(
    client: TestClient, level: int, rule: MistakeRule
) -> tuple[SumGridPuzzle, int, int]:
    """A puzzle, a step and the wrong answer that only `rule` gives there."""
    spec = LEVELS[level]
    for seed in range(300):
        puzzle = internal(client, new_grid(client, level=level, seed=seed)["puzzle_id"])
        for index in range(len(puzzle.steps)):
            view = step_view(puzzle, index)
            value = rule_output(rule, view, spec)
            others = {rule_output(other, view, spec) for other in MistakeRule if other is not rule}
            if value is not None and value not in others and 0 <= value <= spec.option_max:
                return puzzle, index, value
    raise AssertionError(f"no step where only {rule} applies at level {level}")


# ---- generate, verify, serve ----


def test_the_generic_route_makes_a_verified_grid_at_every_level(client: TestClient):
    for level, spec in LEVELS.items():
        for seed in range(25):
            body = new_grid(client, level=level, seed=seed)

            assert set(body) == {
                "game",
                "puzzle_id",
                "level",
                "size",
                "length",
                "topic_ids",
                "cells",
                "row_targets",
                "col_targets",
                "steps",
            }
            assert body["game"] == "sum-grid"
            assert body["puzzle_id"] == make_sum_grid_id(GENERATOR_VERSION, level, seed)
            assert (body["level"], body["size"]) == (level, spec.size)
            assert len(body["cells"]) == spec.size == len(body["row_targets"])
            assert len(body["col_targets"]) == spec.size
            blanks = sum(value is None for row in body["cells"] for value in row)
            assert body["length"] == len(body["steps"]) == blanks
            for index, step in enumerate(body["steps"]):
                assert set(step) == {"index", "cell", "line", "options", "hint_tiers"}
                assert (step["index"], step["hint_tiers"]) == (index, 3)
                assert body["cells"][step["cell"]["row"]][step["cell"]["col"]] is None
                assert step["line"]["kind"] in ("row", "col")
                # The line passes through the cell.
                key = "row" if step["line"]["kind"] == "row" else "col"
                assert step["line"]["index"] == step["cell"][key]
                assert len(set(step["options"])) == 4

            puzzle = internal(client, body["puzzle_id"])
            kind = sum_grid(client)
            assert verify(puzzle, catalog=kind.catalog, topic_exists=kind._topic_exists).ok
            assert body["cells"] == puzzle.cells


def test_the_same_seed_gives_the_same_grid_and_get_rebuilds_it(client: TestClient):
    first = new_grid(client, level=3, seed=77)

    assert new_grid(client, level=3, seed=77) == first
    assert new_grid(client, level=3, seed=78) != first
    response = client.get(f"{PUZZLES}/{first['puzzle_id']}")
    assert response.status_code == 200
    assert response.json() == first
    assert len({new_grid(client, level=2)["puzzle_id"] for _ in range(5)}) == 5


def test_the_public_grid_gives_nothing_away(client: TestClient):
    for level in LEVELS:
        for seed in range(15):
            response = client.post(f"{PUZZLES}/sum-grid", json={"level": level, "seed": seed})
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
    assert client.post(f"{PUZZLES}/sum-grid", json=body).status_code == 422


# ---- check ----


def test_right_answers_walk_the_blanks_in_the_stored_order(client: TestClient):
    puzzle = internal(client, new_grid(client, level=3, seed=4)["puzzle_id"])

    for index, step in enumerate(puzzle.steps):
        body = check(client, puzzle.puzzle_id, index, step.answer).json()
        last = index == len(puzzle.steps) - 1
        assert body == {
            "correct": True,
            "feedback": "correct",
            "diagnosis": {"matched_rules": [], "unrecognized": False, "reteach_topic": None},
            "next_step": None if last else index + 1,
        }


def test_adding_instead_of_finding_the_part_is_named_with_its_reteach_topic(client: TestClient):
    puzzle, index, wrong = find_mistake(client, 1, MistakeRule.ADD_VISIBLE)

    body = check(client, puzzle.puzzle_id, index, wrong).json()

    assert body["correct"] is False
    assert body["feedback"] == "try_again"
    assert body["diagnosis"]["matched_rules"] == ["ADD_VISIBLE"]
    assert body["diagnosis"]["unrecognized"] is False
    # From the taxonomy error pattern: step back to what the equals sign means.
    assert body["diagnosis"]["reteach_topic"] == EQUALS_SIGN
    assert body["next_step"] is None


def test_the_level_three_mistakes_are_recognised(client: TestClient):
    slip, slip_step, slip_value = find_mistake(client, 3, MistakeRule.PLACE_VALUE_SLIP)
    body = check(client, slip.puzzle_id, slip_step, slip_value).json()
    assert body["diagnosis"]["matched_rules"] == ["PLACE_VALUE_SLIP"]
    assert body["diagnosis"]["reteach_topic"] == {
        "id": "mt_ewmuMMPAzP",
        "name": "Addition and subtraction within 1000",
    }

    tens, tens_step, tens_value = find_mistake(client, 3, MistakeRule.TENS_AS_ONES)
    body = check(client, tens.puzzle_id, tens_step, tens_value).json()
    assert body["diagnosis"]["matched_rules"] == ["TENS_AS_ONES"]
    assert body["diagnosis"]["reteach_topic"] == {
        "id": "mt_THl9GLxwoL",
        "name": "The two digits of a two-digit number",
    }


def test_a_wrong_check_never_says_the_answer(client: TestClient):
    for seed in range(15):
        puzzle = internal(client, new_grid(client, level=2, seed=seed)["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            for distractor in step.distractors:
                body = check(client, puzzle.puzzle_id, index, distractor.value).json()
                assert body["correct"] is False
                assert set(body) == {"correct", "feedback", "diagnosis", "next_step"}
                assert body["next_step"] is None
                assert set(body["diagnosis"]) == {"matched_rules", "unrecognized", "reteach_topic"}


def test_answers_outside_the_types_bounds_are_422(client: TestClient):
    puzzle_id = new_grid(client, level=1, seed=5)["puzzle_id"]
    assert (SumGrid.answer_min, SumGrid.answer_max) == (0, 1000)
    assert max(spec.option_max for spec in LEVELS.values()) <= SumGrid.answer_max

    for inside in (0, 1000):
        assert check(client, puzzle_id, 0, inside).status_code == 200
    for outside in (-1, 1001):
        response = check(client, puzzle_id, 0, outside)
        assert response.status_code == 422
        assert response.json()["detail"][0]["msg"] == "Input should be between 0 and 1000"


# ---- hints ----


def test_hint_tiers(client: TestClient):
    for level in LEVELS:
        for seed in range(10):
            puzzle = internal(client, new_grid(client, level=level, seed=seed)["puzzle_id"])
            for index, step in enumerate(puzzle.steps):
                texts = []
                for tier in (1, 2, 3):
                    response = client.get(
                        f"{PUZZLES}/{puzzle.puzzle_id}/steps/{index}/hints/{tier}"
                    )
                    assert response.status_code == 200
                    assert response.json() == {"tier": tier, "text": step.hints[tier - 1]}
                    texts.append(response.json()["text"])
                assert texts[0].startswith("Look at the ")
                assert f" {step.answer}." not in texts[1] and f" {step.answer} " not in texts[1]
                assert texts[2].endswith(f"so the missing number is {step.answer}.")

    puzzle_id = new_grid(client, level=1, seed=3)["puzzle_id"]
    for tier in (0, 4):
        missing = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/{tier}")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Hint tier not found: tiers are 1 to 3", "tier": tier}
    # Level 1 has two blanks, so two steps.
    assert client.get(f"{PUZZLES}/{puzzle_id}/steps/2/hints/1").status_code == 404
    assert check(client, puzzle_id, 2, 5).status_code == 404


# ---- attempts ----


def test_an_attempt_stores_the_cell_the_line_and_the_levels_topics(client: TestClient):
    player = uuid.uuid4()
    puzzle, index, wrong = find_mistake(client, 1, MistakeRule.ADD_VISIBLE)
    step = puzzle.steps[index]
    three = internal(client, new_grid(client, level=3, seed=2)["puzzle_id"])

    check(client, puzzle.puzzle_id, index, wrong, player)
    check(client, puzzle.puzzle_id, index, step.answer, player)
    check(client, three.puzzle_id, 0, three.steps[0].answer, player)

    mistake, right, other = attempts_of(client, player)
    assert (mistake.game, mistake.level, mistake.step_index) == ("sum-grid", 1, index)
    assert mistake.generator_version == GENERATOR_VERSION
    assert (
        mistake.details
        == right.details
        == {
            "size": 2,
            "cell": [step.cell.row, step.cell.col],
            "line": step.line.kind,
            "line_index": step.line.index,
        }
    )
    assert mistake.form is None
    assert mistake.topic_ids == [TOPIC_FLUENT_WITHIN_20, TOPIC_UNKNOWN_ADD_SUB]
    assert (mistake.correct, mistake.answer, mistake.matched_rules) == (
        False,
        wrong,
        ["ADD_VISIBLE"],
    )
    assert mistake.error_pattern_ids == [f"{TOPIC_UNKNOWN_ADD_SUB}#0"]
    assert mistake.reteach_topic_id == EQUALS_SIGN["id"]
    assert (right.correct, right.attempt_on_step) == (True, 2)
    assert other.topic_ids == [TOPIC_ADD_SUBTRACT_7, TOPIC_ADDING_WITHIN_100]
    assert other.details["size"] == 3


def test_without_a_player_nothing_is_stored(client: TestClient):
    with Session(client.app.state.engine) as session:
        before = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()

    puzzle_id = new_grid(client, level=1, seed=4)["puzzle_id"]
    check(client, puzzle_id, 0, 1)
    client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/2")

    with Session(client.app.state.engine) as session:
        after = session.connection().exec_driver_sql("SELECT count(*) FROM attempt").scalar_one()
    assert after == before


# ---- /next: no policy yet ----


def test_next_for_sum_grid_is_the_default_with_no_policy(client: TestClient):
    player = uuid.uuid4()

    with count_statements(client) as seen:
        response = client.get(NEXT, params={"game": "sum-grid"}, headers=as_player(player))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "level": 1,
        "length": None,
        "reason_code": "no_policy",
        "reason": "sum-grid has no recommendation policy yet, so this is its default: "
        "level 1 with the game's default settings.",
        "focus_rule": None,
        "focus": None,
        "params": {},
        "mastery": [],
    }
    assert len(seen) == 1, seen
    body = {"level": response.json()["level"], **response.json()["params"]}
    assert client.post(f"{PUZZLES}/sum-grid", json=body).status_code == 201


# ---- ids ----


def test_tampered_ids_are_404(client: TestClient):
    good = new_grid(client, level=1, seed=6)["puzzle_id"]
    other_level = good.replace("sg-1-1-", "sg-1-2-")  # another level under the old checksum
    wrong_checksum = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
    impossible = make_sum_grid_id(GENERATOR_VERSION, 9, 6)

    for bad in (other_level, wrong_checksum, impossible, "sg-1-1"):
        for response in (
            client.get(f"{PUZZLES}/{bad}"),
            check(client, bad, 0, 1),
            client.get(f"{PUZZLES}/{bad}/steps/0/hints/1"),
        ):
            assert response.status_code == 404, bad
            assert response.json() == {"detail": "Puzzle not found", "puzzle_id": bad}


def test_an_id_from_an_older_version_is_410_and_from_an_unknown_one_404(client: TestClient):
    older = make_sum_grid_id("0", 1, 6)
    for response in (
        client.get(f"{PUZZLES}/{older}"),
        check(client, older, 0, 1),
        client.get(f"{PUZZLES}/{older}/steps/0/hints/1"),
    ):
        assert response.status_code == 410
        assert response.json() == {
            "detail": "Puzzle version is no longer available",
            "current_version": GENERATOR_VERSION,
        }
    assert client.get(f"{PUZZLES}/{make_sum_grid_id('7', 1, 6)}").status_code == 404


# ---- the document ----


def test_openapi_has_the_sum_grid_shapes(client: TestClient):
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    new_puzzle = document["paths"]["/api/v1/puzzles/{game}"]["post"]

    schema = new_puzzle["responses"]["201"]["content"]["application/json"]["schema"]
    assert schema["discriminator"]["mapping"]["sum-grid"] == "#/components/schemas/SumGridPublic"
    bodies = new_puzzle["requestBody"]["content"]["application/json"]["schema"]["oneOf"]
    assert {"$ref": "#/components/schemas/NewSumGridRequest"} in bodies
    assert schemas["NewSumGridRequest"]["required"] == ["level"]
    assert "default" not in schemas["NewSumGridRequest"]["properties"]["seed"]
    public = schemas["SumGridPublic"]["properties"]
    assert public["game"]["const"] == "sum-grid"
    assert set(public) == {
        "game",
        "puzzle_id",
        "level",
        "size",
        "length",
        "topic_ids",
        "cells",
        "row_targets",
        "col_targets",
        "steps",
    }
    assert set(schemas["SumGridStepPublic"]["properties"]) == {
        "index",
        "cell",
        "line",
        "options",
        "hint_tiers",
    }
    parameters = document["paths"][NEXT]["get"]["parameters"]
    game = next(p for p in parameters if p["name"] == "game")
    assert "sum-grid" in game["schema"]["enum"]


# ---- the real taxonomy ----


@pytest.mark.slow
def test_the_rule_catalog_resolves_against_the_real_database():
    if not get_settings().database_path.is_file():
        pytest.skip("no database; run the migration and the importer first")
    engine = make_engine()
    with Session(engine) as session:
        service = TaxonomyService(session, reload_graph(session))
        if TOPIC_THREE_SMALL_NUMBERS not in service.graph:
            engine.dispose()
            pytest.skip("the real taxonomy is not imported")
        catalog = resolve_catalog(service.get_error_patterns)
        exists = topic_exists(service)
        names = {
            topic_id: summary.name
            for topic_id, summary in service.get_summaries(
                [topic for spec in LEVELS.values() for topic in spec.topic_ids]
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
        ("ADD_VISIBLE", "mt_3JgrHY221M#0", "mt_oIzycTBeE4"),
        ("FORGOT_ONE", "mt_Zx1xZM-RbX#2", None),
        ("PLACE_VALUE_SLIP", "mt_SrrsLiJkr3#1", "mt_ewmuMMPAzP"),
        ("CARRY_DROPPED", "mt_SrrsLiJkr3#2", None),
        ("TENS_AS_ONES", "mt_glPPG-kTQY#0", "mt_THl9GLxwoL"),
        ("WRONG_LINE", None, None),
        ("OFF_BY_ONE_OVER", None, None),
        ("OFF_BY_ONE_UNDER", None, None),
        ("NEAR_MISS", None, None),
    ]
    assert names == {
        TOPIC_FLUENT_WITHIN_20: "Fluent adding and subtracting within 20",
        TOPIC_UNKNOWN_ADD_SUB: "Unknown in Addition & Subtraction",
        TOPIC_THREE_SMALL_NUMBERS: "Adding Three Small Numbers",
        TOPIC_ADD_SUBTRACT_7: "Adding and subtracting (age 7+)",
        TOPIC_ADDING_WITHIN_100: "Adding within 100",
    }
    # And with the real catalog, real puzzles verify at every level.
    for level in LEVELS:
        for seed in range(300):
            puzzle = generate_verified(seed, level, catalog=catalog, topic_exists=exists)
            assert verify(puzzle, catalog=catalog, topic_exists=exists).ok
