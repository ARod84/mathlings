import logging
import random
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import app.puzzles.verified as verified_module
from app.puzzles.equations import visible_numbers
from app.puzzles.generator import GenerationError, generate
from app.puzzles.ids import MAX_SEED, InvalidPuzzleId, derive_seed, make_puzzle_id, parse_puzzle_id
from app.puzzles.levels import ANSWER_LEFT_FORMS, GENERATOR_VERSION, LEVELS
from app.puzzles.models import MistakeRule, Puzzle
from app.puzzles.verified import (
    PuzzleGenerationFailed,
    PuzzleRejected,
    generate_verified,
    generate_verified_outcome,
    regenerate,
)
from app.puzzles.verifier import verify
from tests.puzzles.support import make_catalog, topic_exists

CATALOG = make_catalog()
seeds = st.integers(min_value=0, max_value=MAX_SEED)
levels = st.sampled_from(sorted(LEVELS))
lengths = st.integers(min_value=1, max_value=4)


def build(seed: int, level: int, length: int) -> Puzzle:
    return generate_verified(seed, level, length, catalog=CATALOG, topic_exists=topic_exists)


# ---- properties ----


@settings(max_examples=400, deadline=None)
@given(seed=seeds, level=levels, length=lengths)
def test_generate_verified_always_returns_a_puzzle_that_passes_verification(seed, level, length):
    puzzle = build(seed, level, length)

    result = verify(puzzle, catalog=CATALOG, topic_exists=topic_exists)
    assert result.ok, result.failures
    assert puzzle.level == level
    assert len(puzzle.steps) == length


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels, length=lengths)
def test_the_same_inputs_give_a_byte_identical_puzzle(seed, level, length):
    first = build(seed, level, length).model_dump_json()
    second = build(seed, level, length).model_dump_json()

    assert first == second


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels, length=lengths)
def test_a_puzzle_can_be_rebuilt_from_its_id_alone(seed, level, length):
    puzzle = build(seed, level, length)

    rebuilt = regenerate(puzzle.puzzle_id, catalog=CATALOG, topic_exists=topic_exists)
    assert rebuilt == puzzle
    key = parse_puzzle_id(puzzle.puzzle_id)
    assert (key.generator_version, key.level, key.length, key.seed) == (
        GENERATOR_VERSION,
        level,
        length,
        puzzle.seed,
    )


@settings(max_examples=300, deadline=None)
@given(seed=seeds, level=levels, length=lengths)
def test_the_constraints_hold_checked_directly(seed, level, length):
    """The same rules as the verifier, written again here in the plainest way."""
    puzzle = build(seed, level, length)
    spec = LEVELS[level]

    previous = None
    for step in puzzle.steps:
        visible = visible_numbers(step.equation)
        values = [*visible, step.answer]
        assert all(isinstance(value, int) and 1 <= value <= spec.max_value for value in values)
        if level == 3:
            assert any(100 <= value <= 999 for value in values)
        if previous is None:
            assert step.link_position is None
        else:
            assert visible[step.link_position] == previous.answer
            assert step.form != previous.form
        options = [d.value for d in step.distractors]
        assert len(set(options)) == 3
        assert step.answer not in options
        assert all(0 <= value <= spec.max_value for value in options)
        # Hints: the first two never show the answer as a number of its own; the last does.
        for hint in step.hints[:2]:
            assert step.answer not in [int(n) for n in re.findall(r"\d+", hint)]
        assert step.answer in [int(n) for n in re.findall(r"\d+", step.hints[2])]
        previous = step

    answer_left = sum(step.form in ANSWER_LEFT_FORMS for step in puzzle.steps)
    if level < 3:
        assert answer_left <= 1
        assert puzzle.topic_ids[0] == "mt_3JgrHY221M"
        assert ("mt_oIzycTBeE4" in puzzle.topic_ids) == (answer_left == 1)
    else:
        assert puzzle.topic_ids == ["mt_XuHmIn2xje", "mt_ehGS_uVSJv"]


# ---- determinism and the generator's own contract ----


def test_generate_is_deterministic_and_seeds_differ():
    assert generate(42, 2, 4, CATALOG) == generate(42, 2, 4, CATALOG)
    assert generate(42, 2, 4, CATALOG) != generate(43, 2, 4, CATALOG)
    assert generate(42, 2, 4, CATALOG) != generate(42, 1, 4, CATALOG)


def test_generate_does_not_touch_the_global_random_state():
    random.seed(1234)
    before = random.getstate()
    generate(5, 3, 4, CATALOG)
    assert random.getstate() == before

    # And the global state does not leak in.
    random.seed(1)
    first = generate(5, 3, 4, CATALOG)
    random.seed(2)
    assert generate(5, 3, 4, CATALOG) == first


def test_puzzle_metadata():
    puzzle = generate(7, 1, 3, CATALOG)

    assert puzzle.puzzle_type == "missing_number_chain"
    assert puzzle.generator_version == GENERATOR_VERSION
    assert (puzzle.seed, puzzle.level, len(puzzle.steps)) == (7, 1, 3)
    assert puzzle.puzzle_id == make_puzzle_id(GENERATOR_VERSION, 1, 3, 7)
    assert puzzle.topic_ids[0] == "mt_3JgrHY221M"


@pytest.mark.parametrize(
    ("seed", "level", "length"), [(1, 0, 3), (1, 4, 3), (1, 1, 0), (1, 1, 5), (-1, 1, 3)]
)
def test_generate_rejects_bad_arguments(seed, level, length):
    with pytest.raises(ValueError):
        generate(seed, level, length, CATALOG)


def test_all_six_forms_and_every_rule_turn_up():
    forms, rules, linked = set(), set(), set()
    for seed in range(300):
        for level in LEVELS:
            for step in generate(seed, level, 4, CATALOG).steps:
                forms.add(step.form)
                for distractor in step.distractors:
                    rules.add(distractor.rule)
                    if distractor.error_pattern_id:
                        linked.add((distractor.rule, distractor.error_pattern_id))

    assert forms == {"a+?=c", "?+b=c", "a-?=c", "?-b=c", "c=a+?", "c=?-b"}
    assert rules == set(MistakeRule)
    assert linked == {
        (MistakeRule.ADD_VISIBLE, "mt_3JgrHY221M#0"),
        (MistakeRule.ADD_VISIBLE, "mt_XuHmIn2xje#0"),
        (MistakeRule.ANSWER_LEFT_BACKWARDS, "mt_3JgrHY221M#1"),
        (MistakeRule.POSITION_CONFUSION, "mt_XuHmIn2xje#2"),
    }


def test_linked_rules_are_preferred_and_hint_source_carries_the_taxonomy_text():
    for seed in range(200):
        for step in generate(seed, 1, 4, CATALOG).steps:
            tagged = [d for d in step.distractors if d.error_pattern_id]
            # Linked distractors come before the others.
            assert step.distractors[: len(tagged)] == tagged
            assert [source.error_pattern_id for source in step.hint_source] == [
                d.error_pattern_id for d in tagged
            ]
            for source in step.hint_source:
                assert source.next_move == CATALOG.get(source.error_pattern_id).next_move
                # Raw tutor guidance stays out of what the child reads.
                assert source.next_move not in " ".join(step.hints)


# ---- retries ----


def test_retries_use_derived_seeds_and_are_logged(monkeypatch, caplog):
    real_generate = verified_module.generate
    calls: list[int] = []

    def flaky(seed, level, length, catalog):
        calls.append(seed)
        if len(calls) <= 2:
            raise GenerationError("no valid step")
        return real_generate(seed, level, length, catalog)

    monkeypatch.setattr(verified_module, "generate", flaky)
    with caplog.at_level(logging.INFO, logger="app.puzzles.verified"):
        outcome = generate_verified_outcome(11, 1, 3, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 2
    assert calls == [11, derive_seed(11, 1), derive_seed(11, 2)]
    # The puzzle records the seed that built it, so its id rebuilds it directly.
    assert outcome.puzzle.seed == derive_seed(11, 2)
    assert "took 2 retries" in caplog.text


def test_a_puzzle_that_fails_verification_is_retried_not_returned(monkeypatch):
    real_generate = verified_module.generate
    attempts = []

    def sometimes_broken(seed, level, length, catalog):
        attempts.append(seed)
        puzzle = real_generate(seed, level, length, catalog)
        if len(attempts) == 1:
            steps = [puzzle.steps[0].model_copy(update={"answer": puzzle.steps[0].answer + 1})]
            return puzzle.model_copy(update={"steps": steps + puzzle.steps[1:]})
        return puzzle

    monkeypatch.setattr(verified_module, "generate", sometimes_broken)
    outcome = generate_verified_outcome(3, 2, 2, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 1
    assert verify(outcome.puzzle, catalog=CATALOG, topic_exists=topic_exists).ok


def test_gives_up_after_the_attempt_limit(monkeypatch):
    def never(seed, level, length, catalog):
        raise GenerationError("no valid step")

    monkeypatch.setattr(verified_module, "generate", never)

    with pytest.raises(PuzzleGenerationFailed, match="5 attempts"):
        generate_verified(1, 1, 3, catalog=CATALOG, topic_exists=topic_exists, max_attempts=5)


def test_nothing_is_returned_when_a_topic_is_missing_from_the_database():
    with pytest.raises(PuzzleGenerationFailed, match="unknown_topic"):
        generate_verified(1, 1, 3, catalog=CATALOG, topic_exists=lambda _id: False, max_attempts=3)


def test_regenerate_rejects_bad_ids_and_failed_puzzles():
    puzzle = build(9, 1, 2)

    with pytest.raises(InvalidPuzzleId):
        regenerate("mnc-1-1-2-9-0000", catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(InvalidPuzzleId, match="generator version"):
        regenerate(make_puzzle_id("0", 1, 2, 9), catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(PuzzleRejected, match="unknown_topic"):
        regenerate(puzzle.puzzle_id, catalog=CATALOG, topic_exists=lambda _id: False)


# ---- ids ----


@given(seed=seeds, level=levels, length=lengths)
def test_puzzle_id_round_trip(seed, level, length):
    puzzle_id = make_puzzle_id(GENERATOR_VERSION, level, length, seed)
    key = parse_puzzle_id(puzzle_id)

    assert (key.generator_version, key.level, key.length, key.seed) == (
        GENERATOR_VERSION,
        level,
        length,
        seed,
    )
    assert re.fullmatch(r"mnc-1-\d-\d-[0-9a-z]+-[0-9a-f]{4}", puzzle_id)


def test_puzzle_id_examples_and_tampering():
    assert make_puzzle_id("1", 2, 3, 0).startswith("mnc-1-2-3-0-")
    assert make_puzzle_id("1", 2, 3, 35).startswith("mnc-1-2-3-z-")
    assert make_puzzle_id("1", 2, 3, 36).startswith("mnc-1-2-3-10-")
    good = make_puzzle_id("1", 2, 3, 12345)
    tampered = good.replace("-2-3-", "-3-3-")

    for bad in (tampered, "mnc-1-2-3", "xyz-1-2-3-9ix-0000", "", good + "-x"):
        with pytest.raises(InvalidPuzzleId):
            parse_puzzle_id(bad)
    with pytest.raises(ValueError):
        make_puzzle_id("1", 2, 3, -1)
    with pytest.raises(ValueError):
        make_puzzle_id("1.0", 2, 3, 1)


def test_derive_seed():
    assert derive_seed(11, 0) == 11
    assert derive_seed(11, 1) == derive_seed(11, 1)
    derived = {derive_seed(11, attempt) for attempt in range(20)}
    assert len(derived) == 20
    assert all(0 <= seed <= MAX_SEED for seed in derived)
    assert derive_seed(11, 1) != derive_seed(12, 1)
