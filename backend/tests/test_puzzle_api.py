import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.puzzles.service as puzzle_service_module
from app.config import BACKEND_DIR
from app.puzzles.core.schemas import MAX_ANSWER
from app.puzzles.service import PuzzleNotFound, PuzzleRuntime, PuzzleService
from app.puzzles.types.missing_number import MissingNumberParams
from app.puzzles.types.missing_number.equations import visible_numbers
from app.puzzles.types.missing_number.ids import MAX_SEED, make_puzzle_id
from app.puzzles.types.missing_number.levels import GENERATOR_VERSION, LEVELS
from app.puzzles.types.missing_number.models import MistakeRule, Puzzle
from app.puzzles.types.missing_number.public import linked_token, shuffled_options, to_public
from app.puzzles.types.missing_number.rules import rule_output
from app.puzzles.types.missing_number.schemas import LinkedToken
from app.puzzles.types.missing_number.taxonomy_link import topic_exists
from app.puzzles.types.missing_number.verified import PuzzleGenerationFailed, regenerate
from app.puzzles.types.missing_number.verifier import verify
from app.taxonomy.importer import run_import
from app.taxonomy.service import TaxonomyService
from tests.conftest import FIXTURE_COMMIT, FIXTURE_TAXONOMY, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.puzzles.support import make_catalog, make_puzzle, make_step
from tests.test_api import api_client, count_statements

PUZZLES = "/api/v1/puzzles"
GAME = "missing-number"
EQUALS_SIGN = {"id": "mt_oIzycTBeE4", "name": "What the equals sign means"}


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """An app on a temporary database holding the puzzle fixture taxonomy."""
    database_path = tmp_path_factory.mktemp("puzzles") / "puzzles.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def new_puzzle(client: TestClient, **body) -> dict:
    response = client.post(f"{PUZZLES}/missing-number", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def internal(client: TestClient, puzzle_id: str) -> Puzzle:
    """The full server-side puzzle behind an id, for working out expected values."""
    with Session(client.app.state.engine) as session:
        taxonomy = TaxonomyService(session, client.app.state.graph)
        return regenerate(
            puzzle_id,
            catalog=client.app.state.puzzles.require(GAME).catalog,
            topic_exists=topic_exists(taxonomy),
        )


def check(client: TestClient, puzzle_id: str, step: int, answer: int) -> dict:
    response = client.post(f"{PUZZLES}/{puzzle_id}/steps/{step}/check", json={"answer": answer})
    assert response.status_code == 200, response.text
    return response.json()


def find_step(client: TestClient, level: int, rule: MistakeRule) -> tuple[Puzzle, int, int]:
    """A puzzle, a step index and the wrong answer `rule` gives there."""
    for seed in range(200):
        puzzle = internal(client, new_puzzle(client, level=level, length=4, seed=seed)["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            for distractor in step.distractors:
                if distractor.rule is rule:
                    return puzzle, index, distractor.value
    raise AssertionError(f"no {rule} distractor found at level {level}")


# ---- creating and fetching ----


def test_post_creates_a_puzzle_that_passes_verification(client: TestClient):
    body = new_puzzle(client, level=1, length=3, seed=42)

    assert body["level"] == 1
    assert body["length"] == 3
    assert len(body["steps"]) == 3
    assert body["topic_ids"][0] == "mt_3JgrHY221M"
    assert [step["index"] for step in body["steps"]] == [0, 1, 2]
    assert all(step["hint_tiers"] == 3 for step in body["steps"])

    puzzle = internal(client, body["puzzle_id"])
    with Session(client.app.state.engine) as session:
        taxonomy = TaxonomyService(session, client.app.state.graph)
        result = verify(
            puzzle,
            catalog=client.app.state.puzzles.require(GAME).catalog,
            topic_exists=topic_exists(taxonomy),
        )
    assert result.ok, result.failures
    assert (puzzle.seed, puzzle.level, len(puzzle.steps)) == (42, 1, 3)


def test_length_defaults_to_three_and_every_level_and_length_works(client: TestClient):
    assert new_puzzle(client, level=2)["length"] == 3
    for level in (1, 2, 3):
        for length in (1, 2, 3, 4):
            body = new_puzzle(client, level=level, length=length, seed=5)
            assert (body["level"], body["length"], len(body["steps"])) == (level, length, length)


def test_same_seed_gives_the_same_id_and_the_same_options_order(client: TestClient):
    first = new_puzzle(client, level=2, length=4, seed=1234)
    second = new_puzzle(client, level=2, length=4, seed=1234)

    assert first == second
    assert first["puzzle_id"] == make_puzzle_id(GENERATOR_VERSION, 2, 4, 1234)
    assert new_puzzle(client, level=2, length=4, seed=1235) != first


def test_without_a_seed_puzzles_differ(client: TestClient):
    ids = {new_puzzle(client, level=1)["puzzle_id"] for _ in range(5)}
    assert len(ids) == 5


def test_get_rebuilds_the_same_puzzle_from_its_id(client: TestClient):
    created = new_puzzle(client, level=3, length=4, seed=77)

    response = client.get(f"{PUZZLES}/{created['puzzle_id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_equation_tokens_are_sent_unchanged(client: TestClient):
    created = new_puzzle(client, level=1, length=2, seed=3)
    puzzle = internal(client, created["puzzle_id"])

    for public, step in zip(created["steps"], puzzle.steps, strict=True):
        assert public["equation"] == step.equation.model_dump()
        kinds = [t["kind"] for t in (*public["equation"]["left"], *public["equation"]["right"])]
        assert kinds.count("unknown") == 1
        assert kinds.count("number") == 2
        assert kinds.count("operator") == 1


# ---- the linked token ----


def test_linked_token_picks_the_right_one_when_the_value_appears_twice():
    # 14 − □ = 5 gives 9. The next step is □ − 9 = 9: both visible numbers are 9,
    # and only one of them is the 9 the child just found.
    first = make_step("a-?=c", 14, 5)
    link_is_first_nine = make_puzzle([first, make_step("?-b=c", 9, 9, link_position=0)])
    link_is_second_nine = make_puzzle([first, make_step("?-b=c", 9, 9, link_position=1)])
    for puzzle in (link_is_first_nine, link_is_second_nine):
        result = verify(puzzle, catalog=make_catalog(), topic_exists=lambda _topic_id: True)
        assert result.ok, result.failures

    as_first = to_public(link_is_first_nine).steps
    as_second = to_public(link_is_second_nine).steps

    assert as_first[0].linked_token is None
    # □ − 9 = 9 is  left: [box, −, 9]  right: [9]
    assert as_first[1].linked_token == LinkedToken(side="left", index=2)
    assert as_second[1].linked_token == LinkedToken(side="right", index=0)
    assert as_first[1].equation == as_second[1].equation


@pytest.mark.parametrize(
    ("form", "first", "second", "expected"),
    [
        # reads as          left tokens       right tokens
        ("a+?=c", 8, 11, [("left", 0), ("right", 0)]),  # 8 + □ = 11
        ("?+b=c", 5, 12, [("left", 2), ("right", 0)]),  # □ + 5 = 12
        ("a-?=c", 14, 6, [("left", 0), ("right", 0)]),  # 14 − □ = 6
        ("?-b=c", 3, 5, [("left", 2), ("right", 0)]),  # □ − 3 = 5
        ("c=a+?", 11, 8, [("left", 0), ("right", 0)]),  # 11 = 8 + □
        ("c=?-b", 5, 3, [("left", 0), ("right", 2)]),  # 5 = □ − 3
    ],
)
def test_linked_token_for_every_form_and_position(form, first, second, expected):
    equation = make_step(form, first, second).equation

    for position, (side, index) in enumerate(expected):
        token = linked_token(equation, position)
        assert token == LinkedToken(side=side, index=index)
        assert getattr(equation, side)[index].value == (first, second)[position]
    assert linked_token(equation, None) is None
    assert linked_token(equation, 2) is None  # there are only two visible numbers


def test_linked_token_in_the_api_points_at_the_previous_answer(client: TestClient):
    for level in (1, 2, 3):
        for seed in range(30):
            created = new_puzzle(client, level=level, length=4, seed=seed)
            puzzle = internal(client, created["puzzle_id"])
            assert created["steps"][0]["linked_token"] is None
            for index in range(1, 4):
                public = created["steps"][index]
                linked = public["linked_token"]
                token = public["equation"][linked["side"]][linked["index"]]
                assert token == {"kind": "number", "value": puzzle.steps[index - 1].answer}
                # It is the same number the internal link position names.
                numbers = [
                    (side, i)
                    for side in ("left", "right")
                    for i, t in enumerate(public["equation"][side])
                    if t["kind"] == "number"
                ]
                assert numbers[puzzle.steps[index].link_position] == (
                    linked["side"],
                    linked["index"],
                )


# ---- what the browser must not receive ----


def test_public_puzzle_has_no_internal_fields(client: TestClient):
    for level in (1, 2, 3):
        for seed in range(15):
            response = client.post(
                f"{PUZZLES}/missing-number", json={"level": level, "length": 4, "seed": seed}
            )
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
                '"form"',
                "link_position",
                "generator_version",
            ):
                assert forbidden not in text, forbidden
            for rule in MistakeRule:
                assert rule.value not in text
            puzzle = internal(client, response.json()["puzzle_id"])
            for step in puzzle.steps:
                for hint in step.hints:
                    assert hint not in text
                for source in step.hint_source:
                    assert source.next_move not in text
                    assert source.error_pattern_id not in text
            assert set(response.json()) == {
                "game",
                "puzzle_id",
                "level",
                "length",
                "topic_ids",
                "steps",
            }
            assert response.json()["game"] == GAME
            assert set(response.json()["steps"][0]) == {
                "index",
                "equation",
                "options",
                "hint_tiers",
                "linked_token",
            }


def test_options_are_the_answer_once_plus_the_three_distractors(client: TestClient):
    answer_positions = set()
    for level in (1, 2, 3):
        for seed in range(25):
            created = new_puzzle(client, level=level, length=4, seed=seed)
            puzzle = internal(client, created["puzzle_id"])
            for public, step in zip(created["steps"], puzzle.steps, strict=True):
                options = public["options"]
                assert len(options) == 4
                assert len(set(options)) == 4
                assert options.count(step.answer) == 1
                assert sorted(options) == sorted(
                    [step.answer, *(d.value for d in step.distractors)]
                )
                answer_positions.add(options.index(step.answer))

    # The shuffle does not park the answer in one place.
    assert answer_positions == {0, 1, 2, 3}


def test_options_order_depends_on_the_puzzle_and_the_step():
    values = [3, 4, 2, 19]
    again = shuffled_options("mnc-1-1-3-1-89f2", 0, values)

    assert again == shuffled_options("mnc-1-1-3-1-89f2", 0, list(reversed(values)))
    orders = {tuple(shuffled_options("mnc-1-1-3-1-89f2", step, values)) for step in range(12)}
    assert len(orders) > 1


# ---- checking answers ----


def test_correct_answers_walk_the_chain_to_the_end(client: TestClient):
    created = new_puzzle(client, level=1, length=3, seed=8)
    puzzle = internal(client, created["puzzle_id"])

    for index, step in enumerate(puzzle.steps):
        result = check(client, puzzle.puzzle_id, index, step.answer)
        assert result == {
            "correct": True,
            "feedback": "correct",
            "diagnosis": {"matched_rules": [], "unrecognized": False, "reteach_topic": None},
            "next_step": index + 1 if index < 2 else None,
        }


def test_a_known_mistake_is_named_with_its_reteach_topic(client: TestClient):
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    first, second = visible_numbers(puzzle.steps[index].equation)
    assert wrong == first + second

    result = check(client, puzzle.puzzle_id, index, wrong)

    assert result["correct"] is False
    assert result["feedback"] == "try_again"
    assert result["diagnosis"]["matched_rules"] == ["ADD_VISIBLE"]
    assert result["diagnosis"]["unrecognized"] is False
    # From the taxonomy error pattern: step back to what the equals sign means.
    assert result["diagnosis"]["reteach_topic"] == EQUALS_SIGN
    assert result["next_step"] is None


def test_a_mistake_without_a_pattern_steps_back_through_the_graph(client: TestClient):
    puzzle, index, wrong = find_step(client, 3, MistakeRule.PLACE_VALUE_SLIP)

    result = check(client, puzzle.puzzle_id, index, wrong)

    assert "PLACE_VALUE_SLIP" in result["diagnosis"]["matched_rules"]
    assert result["diagnosis"]["reteach_topic"] == {
        "id": "mt_yTWxkzzoOZ",
        "name": "Two-Step Word Problems",
    }


def test_an_unexplained_wrong_answer_is_unrecognized(client: TestClient):
    created = new_puzzle(client, level=2, length=1, seed=21)
    puzzle = internal(client, created["puzzle_id"])
    step = puzzle.steps[0]
    explained = {rule_output(rule, step, LEVELS[2]) for rule in MistakeRule}
    wrong = next(n for n in range(0, 10_000) if n != step.answer and n not in explained)

    result = check(client, puzzle.puzzle_id, 0, wrong)

    assert result == {
        "correct": False,
        "feedback": "try_again",
        "diagnosis": {"matched_rules": [], "unrecognized": True, "reteach_topic": None},
        "next_step": None,
    }


def test_a_wrong_check_never_says_the_answer(client: TestClient):
    for seed in range(20):
        created = new_puzzle(client, level=3, length=2, seed=seed)
        puzzle = internal(client, created["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            for wrong in [d.value for d in step.distractors]:
                response = client.post(
                    f"{PUZZLES}/{puzzle.puzzle_id}/steps/{index}/check", json={"answer": wrong}
                )
                numbers = [int(n) for n in re.findall(r"\d+", response.text)]
                assert step.answer not in numbers
                assert set(response.json()) == {"correct", "feedback", "diagnosis", "next_step"}


def test_each_check_writes_one_structured_log_line(client: TestClient, caplog):
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)

    with caplog.at_level(logging.INFO, logger="app.puzzles.checks"):
        check(client, puzzle.puzzle_id, index, wrong)
        check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer)

    records = [r for r in caplog.records if r.name == "app.puzzles.checks"]
    assert len(records) == 2
    wrong_fields, right_fields = (record.puzzle_check for record in records)
    assert wrong_fields == {
        "puzzle_id": puzzle.puzzle_id,
        "step": index,
        "correct": False,
        "matched_rules": ["ADD_VISIBLE"],
        "latency_ms": wrong_fields["latency_ms"],
    }
    assert isinstance(wrong_fields["latency_ms"], float) and wrong_fields["latency_ms"] >= 0
    assert right_fields["correct"] is True
    assert right_fields["matched_rules"] == []
    message = records[0].getMessage()
    assert message.startswith(f"puzzle_check puzzle_id={puzzle.puzzle_id} step={index} ")
    assert "correct=False matched_rules=ADD_VISIBLE latency_ms=" in message
    # The child's answer itself is not logged.
    assert f"answer={wrong}" not in message


def test_an_option_above_the_level_range_can_be_checked_and_is_diagnosed(client: TestClient):
    # The check body accepts answers up to MAX_ANSWER, which has to cover every
    # value a distractor can take.
    assert max(spec.distractor_max for spec in LEVELS.values()) <= MAX_ANSWER

    for seed in range(200):
        puzzle = internal(client, new_puzzle(client, level=1, length=4, seed=seed)["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            over = [d for d in step.distractors if d.value > LEVELS[1].max_value]
            if not over or over[0].rule is not MistakeRule.ADD_VISIBLE:
                continue
            public = client.get(f"{PUZZLES}/{puzzle.puzzle_id}").json()
            assert over[0].value in public["steps"][index]["options"]
            result = check(client, puzzle.puzzle_id, index, over[0].value)
            assert result["diagnosis"]["matched_rules"] == ["ADD_VISIBLE"]
            assert result["diagnosis"]["reteach_topic"] == EQUALS_SIGN
            return
    raise AssertionError("no above-range ADD_VISIBLE option found")


# ---- hints ----


def test_hint_tiers(client: TestClient):
    for level in (1, 2, 3):
        created = new_puzzle(client, level=level, length=4, seed=13)
        puzzle = internal(client, created["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            texts = []
            for tier in (1, 2, 3):
                response = client.get(f"{PUZZLES}/{puzzle.puzzle_id}/steps/{index}/hints/{tier}")
                assert response.status_code == 200
                assert response.json() == {"tier": tier, "text": step.hints[tier - 1]}
                texts.append(response.json()["text"])

            def numbers(text: str) -> list[int]:
                return [int(n) for n in re.findall(r"\d+", text)]

            # Only the third tier, which the child has to ask for, shows the answer.
            assert step.answer not in numbers(texts[0])
            assert step.answer not in numbers(texts[1])
            assert step.answer in numbers(texts[2])


# ---- errors ----


def test_tampered_or_malformed_id_is_404(client: TestClient):
    good = new_puzzle(client, level=1, length=3, seed=6)["puzzle_id"]
    tampered = good.replace("-1-3-", "-2-3-")  # a different level under the old checksum
    wrong_checksum = good[:-4] + ("0000" if not good.endswith("0000") else "1111")

    for bad in (tampered, wrong_checksum, "not-a-puzzle", "mnc-1-1-3", "x"):
        for response in (
            client.get(f"{PUZZLES}/{bad}"),
            client.post(f"{PUZZLES}/{bad}/steps/0/check", json={"answer": 1}),
            client.get(f"{PUZZLES}/{bad}/steps/0/hints/1"),
        ):
            assert response.status_code == 404
            assert response.json() == {"detail": "Puzzle not found", "puzzle_id": bad}


def test_an_id_with_a_valid_checksum_but_impossible_values_is_404(client: TestClient):
    for level, length in ((9, 3), (1, 9), (0, 1)):
        impossible = make_puzzle_id(GENERATOR_VERSION, level, length, 5)
        response = client.get(f"{PUZZLES}/{impossible}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Puzzle not found", "puzzle_id": impossible}


def test_an_id_from_an_older_generator_is_410(client: TestClient):
    # Real ids that the version 1 and version 2 generators handed out.
    assert make_puzzle_id("1", 1, 3, 2) == "mnc-1-1-3-2-b555"
    assert make_puzzle_id("2", 1, 2, 42) == "mnc-2-1-2-16-eb38"
    assert GENERATOR_VERSION == "3"

    for old in (make_puzzle_id("0", 1, 3, 42), "mnc-1-1-3-2-b555", "mnc-2-1-2-16-eb38"):
        for response in (
            client.get(f"{PUZZLES}/{old}"),
            client.post(f"{PUZZLES}/{old}/steps/0/check", json={"answer": 1}),
            client.get(f"{PUZZLES}/{old}/steps/0/hints/1"),
        ):
            assert response.status_code == 410
            assert response.json() == {
                "detail": "Puzzle version is no longer available",
                "current_version": GENERATOR_VERSION,
            }


def test_an_id_from_an_unknown_version_is_404_not_410(client: TestClient):
    # Not older: a version this server has never made. It cannot say "start again".
    for version in ("999", "beta"):
        response = client.get(f"{PUZZLES}/{make_puzzle_id(version, 1, 3, 42)}")
        assert response.status_code == 404


def test_step_out_of_range_is_404(client: TestClient):
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    for step in (2, 7, -1):
        for response in (
            client.post(f"{PUZZLES}/{puzzle_id}/steps/{step}/check", json={"answer": 1}),
            client.get(f"{PUZZLES}/{puzzle_id}/steps/{step}/hints/1"),
        ):
            assert response.status_code == 404
            assert response.json() == {
                "detail": "Step not found: this puzzle has steps 0 to 1",
                "puzzle_id": puzzle_id,
                "step_index": step,
            }


def test_hint_tier_out_of_range_is_404(client: TestClient):
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    for tier in (0, 4, 99):
        response = client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/{tier}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Hint tier not found: tiers are 1 to 3", "tier": tier}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"level": 0},
        {"level": 4},
        {"level": "one"},
        {"level": 1, "length": 0},
        {"level": 1, "length": 5},
        {"level": 1, "seed": -1},
        {"level": 1, "seed": MAX_SEED + 1},
        {"level": 1, "seed": "abc"},
        {"level": 1, "extra": True},
    ],
)
def test_bad_new_puzzle_bodies_are_422(client: TestClient, body):
    assert client.post(f"{PUZZLES}/missing-number", json=body).status_code == 422


def test_the_largest_seed_is_accepted(client: TestClient):
    body = new_puzzle(client, level=1, length=1, seed=MAX_SEED)
    assert internal(client, body["puzzle_id"]).level == 1


@pytest.mark.parametrize(
    "body", [{}, {"answer": -1}, {"answer": 10_001}, {"answer": "six"}, {"answer": 2.5}, {"a": 1}]
)
def test_bad_check_bodies_are_422(client: TestClient, body):
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]
    response = client.post(f"{PUZZLES}/{puzzle_id}/steps/0/check", json=body)

    assert response.status_code == 422


def test_non_numeric_step_or_tier_is_422(client: TestClient):
    puzzle_id = new_puzzle(client, level=1, length=2, seed=6)["puzzle_id"]

    assert client.get(f"{PUZZLES}/{puzzle_id}/steps/one/hints/1").status_code == 422
    assert client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/big").status_code == 422


def test_generation_running_out_of_retries_is_503_and_logged(client, monkeypatch, caplog):
    def exhausted(puzzle_type, seed, level, params):
        raise PuzzleGenerationFailed(f"{puzzle_type.game}, seed {seed}, level {level}: no luck")

    monkeypatch.setattr(puzzle_service_module, "generate_verified", exhausted)
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = client.post(f"{PUZZLES}/missing-number", json={"level": 1, "seed": 31337})

    assert response.status_code == 503
    assert response.json() == {"detail": "Could not make a puzzle. Please try again."}
    assert "seed 31337" in caplog.text


def test_puzzles_are_503_when_the_taxonomy_lacks_their_topics(tmp_path: Path):
    # The plain fixture has no puzzle topics: the app starts, taxonomy routes work,
    # puzzle routes say they are unavailable.
    engine = migrate(tmp_path / "plain.db")
    run_import(engine, FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()

    with api_client(tmp_path / "plain.db") as plain:
        assert plain.get("/health").json()["taxonomy_loaded"] is True
        assert plain.get("/api/v1/topics").status_code == 200
        response = plain.post(f"{PUZZLES}/missing-number", json={"level": 1})
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]
        assert plain.get(f"{PUZZLES}/{make_puzzle_id('1', 1, 3, 4)}").status_code == 503


def test_puzzles_are_503_before_any_import(tmp_path: Path):
    with api_client(tmp_path / "empty.db") as empty:
        response = empty.post(f"{PUZZLES}/missing-number", json={"level": 1})
        assert response.status_code == 503


# ---- the catalog is loaded once; queries stay few ----


def test_the_catalog_is_resolved_once_across_many_requests(client: TestClient):
    runtime: PuzzleRuntime = client.app.state.puzzles
    chains = runtime.require(GAME)
    before = runtime.load_count
    assert before >= 1  # resolved at startup, in the lifespan

    puzzle_id = new_puzzle(client, level=1, length=3, seed=2)["puzzle_id"]
    for request in range(20):
        client.get(f"{PUZZLES}/{puzzle_id}")
        client.post(f"{PUZZLES}/{puzzle_id}/steps/0/check", json={"answer": request})
        client.get(f"{PUZZLES}/{puzzle_id}/steps/0/hints/2")
        client.post(f"{PUZZLES}/missing-number", json={"level": 2})

    assert runtime.load_count == before
    assert runtime.require(GAME) is chains
    assert runtime.require(GAME).catalog is chains.catalog


def test_the_catalog_is_resolved_at_startup_not_on_the_first_request(tmp_path: Path):
    engine = migrate(tmp_path / "startup.db")
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()

    with api_client(tmp_path / "startup.db") as fresh:
        assert fresh.app.state.puzzles.load_count == 1
        assert fresh.app.state.puzzles.require(GAME).catalog is not None
        new_puzzle(fresh, level=1)
        assert fresh.app.state.puzzles.load_count == 1


def test_the_catalog_reloads_when_the_graph_reloads_after_a_reimport(
    tmp_path: Path, taxonomy_puzzles: Path, edit_puzzle_taxonomy
):
    database_path = tmp_path / "reimport.db"
    engine = migrate(database_path)
    run_import(engine, taxonomy_puzzles, FIXTURE_COMMIT)

    with api_client(database_path) as running:
        puzzle, index, wrong = find_step(running, 1, MistakeRule.ADD_VISIBLE)
        assert check(running, puzzle.puzzle_id, index, wrong)["diagnosis"]["reteach_topic"] == (
            EQUALS_SIGN
        )
        assert running.app.state.puzzles.load_count == 1

        # A new taxonomy version renames the reteach topic.
        def rename(data):
            for topic in data["topics"]:
                if topic["id"] == "mt_oIzycTBeE4":
                    topic["name"] = "The equals sign as a balance"

        edit_puzzle_taxonomy("topics.json", rename)
        run_import(engine, taxonomy_puzzles, "a" * 40)

        result = check(running, puzzle.puzzle_id, index, wrong)
        assert result["diagnosis"]["reteach_topic"]["name"] == "The equals sign as a balance"
        assert running.app.state.puzzles.load_count == 2
        check(running, puzzle.puzzle_id, index, wrong)
        assert running.app.state.puzzles.load_count == 2
    engine.dispose()


def test_statement_budgets(client: TestClient):
    puzzle, index, wrong = find_step(client, 1, MistakeRule.ADD_VISIBLE)
    puzzle_id = puzzle.puzzle_id

    def statements(method: str, path: str, **kwargs) -> list[str]:
        with count_statements(client) as seen:
            response = client.request(method, f"{PUZZLES}{path}", **kwargs)
        assert response.status_code in (200, 201), response.text
        return seen

    # Every request makes the one freshness check. Nothing else reads the
    # database, except naming the reteach topic after a recognized mistake.
    assert len(statements("GET", f"/{puzzle_id}")) == 1
    assert len(statements("POST", "/missing-number", json={"level": 3, "length": 4})) == 1
    assert len(statements("GET", f"/{puzzle_id}/steps/{index}/hints/3")) == 1
    right = puzzle.steps[index].answer
    assert len(statements("POST", f"/{puzzle_id}/steps/{index}/check", json={"answer": right})) == 1
    assert len(statements("POST", f"/{puzzle_id}/steps/{index}/check", json={"answer": wrong})) == 2


# ---- the service on its own ----


def test_the_service_works_without_http(client: TestClient):
    with Session(client.app.state.engine) as session:
        taxonomy = TaxonomyService(session, client.app.state.graph)
        service = PuzzleService(taxonomy, client.app.state.puzzles)

        puzzle = service.new_puzzle(GAME, level=1, params=MissingNumberParams(length=2), seed=4)
        assert service.get_puzzle(puzzle.puzzle_id) == puzzle
        assert service.hint(puzzle.puzzle_id, 0, 1).text.startswith("The = sign means")
        assert service.check(puzzle.puzzle_id, 0, 9_999).correct is False
        with pytest.raises(PuzzleNotFound) as error:
            service.get_puzzle("nonsense")
        assert error.value.puzzle_id == "nonsense"
        random_puzzle = service.new_puzzle(GAME, level=1)
        assert random_puzzle.length == 3


def test_service_modules_do_not_import_fastapi():
    puzzles = BACKEND_DIR / "app" / "puzzles"
    sources = [puzzles / "service.py", puzzles / "registry.py"]
    sources += sorted((puzzles / "core").glob("*.py"))
    sources += sorted((puzzles / "types" / "missing_number").glob("*.py"))
    assert len(sources) > 20
    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert "fastapi" not in source, path.name
        assert "starlette" not in source, path.name


def test_post_is_allowed_by_cors(client: TestClient):
    preflight = client.options(
        f"{PUZZLES}/missing-number",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in preflight.headers["access-control-allow-methods"]
    blocked = client.options(
        f"{PUZZLES}/missing-number",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert blocked.status_code == 400


def test_puzzle_routes_are_tagged_with_response_models(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    puzzle_paths = {path: operations for path, operations in paths.items() if "/puzzles" in path}

    assert {(path, method) for path, ops in puzzle_paths.items() for method in ops} == {
        ("/api/v1/puzzles/missing-number", "post"),
        ("/api/v1/puzzles/{game}", "post"),
        ("/api/v1/puzzles/{puzzle_id}", "get"),
        ("/api/v1/puzzles/{puzzle_id}/steps/{index}/check", "post"),
        ("/api/v1/puzzles/{puzzle_id}/steps/{index}/hints/{tier}", "get"),
    }
    for operations in puzzle_paths.values():
        for operation in operations.values():
            assert operation["tags"] == ["Puzzles"]
            assert operation["summary"]
    created = paths["/api/v1/puzzles/missing-number"]["post"]["responses"]["201"]
    assert created["content"]["application/json"]["schema"]["$ref"].endswith("/PuzzlePublic")
    assert "410" in paths["/api/v1/puzzles/{puzzle_id}"]["get"]["responses"]
