"""The generator with the verifier: every puzzle is valid, and the same seed gives the same one."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import app.puzzles.types.sequences.generator as generator_module
from app.puzzles.core import GenerationError
from app.puzzles.core.ids import MAX_SEED, InvalidPuzzleId, OutdatedPuzzleId, derive_seed
from app.puzzles.types.sequences.generator import generate
from app.puzzles.types.sequences.hints import MINUS
from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import (
    EVIDENCE,
    GENERATOR_VERSION,
    LEVELS,
    OPTION_CEILING,
    OPTION_FLOOR,
    longest_visible_run,
    step_topic_ids,
)
from app.puzzles.types.sequences.models import MistakeRule, SequencePuzzle
from app.puzzles.types.sequences.public import to_public
from app.puzzles.types.sequences.verified import (
    PuzzleGenerationFailed,
    PuzzleRejected,
    generate_verified,
    generate_verified_outcome,
    regenerate,
)
from app.puzzles.types.sequences.verifier import verify
from tests.sequences.support import make_catalog, make_puzzle, topic_exists

CATALOG = make_catalog()
SNAPSHOT = Path(__file__).parent.parent / "snapshots" / "sequences_v1.json"
SNAPSHOT_SEEDS = 600

seeds = st.integers(min_value=0, max_value=MAX_SEED)
levels = st.sampled_from(sorted(LEVELS))


def build(seed: int, level: int) -> SequencePuzzle:
    return generate_verified(seed, level, catalog=CATALOG, topic_exists=topic_exists)


def written(text: str) -> set[int]:
    """The numbers in a hint, read here on purpose and not with the library's own reader.

    A minus sign directly before the digits makes the number negative; with a
    space after it, it is a subtraction.
    """
    numbers = set()
    for match in re.finditer(r"\d+", text):
        negative = match.start() > 0 and text[match.start() - 1] in (MINUS, "-")
        numbers.add(-int(match.group()) if negative else int(match.group()))
    return numbers


# ---- properties, for any seed ----


@settings(max_examples=300, deadline=None)
@given(seed=seeds, level=levels)
def test_every_generated_puzzle_verifies(seed, level):
    puzzle = build(seed, level)

    result = verify(puzzle, catalog=CATALOG, topic_exists=topic_exists)
    assert result.ok, result.failures


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels)
def test_regeneration_from_the_id_is_byte_identical(seed, level):
    puzzle = build(seed, level)

    again = regenerate(puzzle.puzzle_id, catalog=CATALOG, topic_exists=topic_exists)

    assert again.model_dump_json() == puzzle.model_dump_json()
    assert to_public(again).model_dump_json() == to_public(puzzle).model_dump_json()
    # And asking for the same seed again is the same puzzle, not just an equal one.
    assert build(seed, level).model_dump_json() == puzzle.model_dump_json()


@settings(max_examples=300, deadline=None)
@given(seed=seeds, level=levels)
def test_the_shape_of_every_puzzle(seed, level):
    puzzle = build(seed, level)
    spec = LEVELS[level]

    assert 5 <= len(puzzle.terms) <= 6
    assert all(spec.min_value <= term <= spec.max_value for term in puzzle.terms)
    assert 1 <= len(puzzle.steps) <= spec.max_blanks
    assert 0 not in puzzle.blanks
    assert puzzle.blanks == sorted(set(puzzle.blanks))
    assert longest_visible_run(len(puzzle.terms), puzzle.blanks) >= EVIDENCE[puzzle.kind]
    assert puzzle.topic_ids == step_topic_ids(level, puzzle.kind)
    if level == 1:
        assert puzzle.blanks == [len(puzzle.terms) - 1]
        assert puzzle.terms == sorted(puzzle.terms)
    for step in puzzle.steps:
        assert step.answer == puzzle.terms[step.position]
        values = [d.value for d in step.distractors]
        assert len(values) == 3 and len({step.answer, *values}) == 4
        assert all(OPTION_FLOOR <= value <= OPTION_CEILING for value in values)
        assert all(spec.option_min <= value <= spec.option_max for value in values)


@settings(max_examples=300, deadline=None)
@given(seed=seeds, level=levels)
def test_only_the_last_hint_shows_the_answer(seed, level):
    puzzle = build(seed, level)

    for step in puzzle.steps:
        look, rule, worked = step.hints
        assert written(look) == set()
        # The answer as it is written: 16, or −3 with its sign.
        assert step.answer not in written(rule), (rule, step.answer)
        assert step.answer in written(worked), (worked, step.answer)
        if step.answer < 0:
            # The negative form never appears early, with either kind of minus sign.
            for early in (look, rule):
                assert f"{MINUS}{-step.answer}" not in early
                assert f"-{-step.answer}" not in early


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels)
def test_the_public_puzzle_hides_the_blanks_and_offers_the_answer_once(seed, level):
    puzzle = build(seed, level)
    public = to_public(puzzle)

    assert public.game == "sequences"
    assert public.length == len(puzzle.steps) == len(public.steps)
    assert [term is None for term in public.terms] == [
        position in puzzle.blanks for position in range(len(puzzle.terms))
    ]
    for shown, step in zip(public.steps, puzzle.steps, strict=True):
        assert shown.position == step.position
        assert shown.options.count(step.answer) == 1
        assert sorted(shown.options) == sorted([step.answer, *(d.value for d in step.distractors)])
    text = public.model_dump_json()
    for forbidden in ('"answer"', "rule", "error_pattern", "hint_source", '"hints"', '"seed"'):
        assert forbidden not in text
    assert '"kind"' not in text


# ---- what the levels make, over many seeds ----


def test_every_sort_of_sequence_each_level_allows_is_made():
    sorts: dict[int, Counter] = {level: Counter() for level in LEVELS}
    blanks: dict[int, Counter] = {level: Counter() for level in LEVELS}
    lengths: Counter = Counter()
    for level in LEVELS:
        for seed in range(400):
            puzzle = build(seed, level)
            up = puzzle.terms[1] > puzzle.terms[0]
            sorts[level][(puzzle.kind, "up" if up else "down")] += 1
            blanks[level][len(puzzle.steps)] += 1
            lengths[len(puzzle.terms)] += 1

    assert set(sorts[1]) == {("constant", "up")}
    assert set(sorts[2]) == {("constant", "up"), ("constant", "down")}
    assert set(sorts[3]) == {("constant", "down"), ("growing", "up")}
    assert set(blanks[1]) == {1}
    assert set(blanks[2]) == set(blanks[3]) == {1, 2}
    assert set(lengths) == {5, 6}
    # Neither sort crowds the other out.
    assert min(sorts[2].values()) > 120 and min(sorts[3].values()) > 120


def test_level_three_through_zero_always_asks_for_a_number_below_zero():
    made = 0
    for seed in range(600):
        puzzle = build(seed, 3)
        if puzzle.kind != "constant":
            continue
        made += 1
        assert puzzle.terms[0] > 0 > puzzle.terms[-1] >= -50
        assert any(step.answer < 0 for step in puzzle.steps)
        negative = next(step for step in puzzle.steps if step.answer < 0)
        rules = {d.rule for d in negative.distractors}
        # The two mistakes about zero are always on offer where the answer is negative.
        assert {MistakeRule.STOPS_AT_ZERO, MistakeRule.SIGN_DROPPED} <= rules
    assert made > 200


def test_linked_rules_come_before_the_others_and_fillers_last():
    order = {MistakeRule.NEAR_MISS: 2}
    for level in LEVELS:
        for seed in range(300):
            for step in build(seed, level).steps:
                tiers = [
                    order.get(d.rule, 0 if CATALOG.is_linked(d.rule) else 1)
                    for d in step.distractors
                ]
                assert tiers == sorted(tiers), step.distractors
                for distractor in step.distractors:
                    assert (distractor.error_pattern_id is not None) == CATALOG.is_linked(
                        distractor.rule
                    )
                sources = {source.error_pattern_id for source in step.hint_source}
                assert sources == {
                    d.error_pattern_id for d in step.distractors if d.error_pattern_id
                }
                for source in step.hint_source:
                    assert source.next_move == CATALOG.get(source.error_pattern_id).next_move


def test_the_generator_does_not_use_the_verifier():
    package = Path(generator_module.__file__).parent
    source = (package / "generator.py").read_text("utf-8")

    assert "sequences.verifier" not in source
    assert "fitting_rules" not in source


# ---- seeds, ids, retries ----


def test_the_same_seed_always_gives_the_same_puzzle_and_levels_differ():
    assert generate(41, 2, CATALOG) == generate(41, 2, CATALOG)
    assert generate(41, 2, CATALOG) != generate(42, 2, CATALOG)
    assert generate(41, 2, CATALOG).puzzle_id == make_sequence_id(GENERATOR_VERSION, 2, 41)
    assert generate(41, 2, CATALOG).puzzle_id.startswith("seq-1-2-")
    assert build(MAX_SEED, 1).seed == MAX_SEED


def test_bad_inputs_are_refused():
    for seed, level in ((-1, 1), (MAX_SEED + 1, 1), (5, 0), (5, 4)):
        with pytest.raises(ValueError):
            generate(seed, level, CATALOG)


def test_a_seed_the_generator_gives_up_on_is_retried_with_a_derived_seed(monkeypatch):
    real_generate = generator_module.generate
    calls: list[int] = []

    def flaky(seed, level, catalog):
        calls.append(seed)
        if len(calls) <= 2:
            raise GenerationError("no place for a blank")
        return real_generate(seed, level, catalog)

    monkeypatch.setattr(generator_module, "generate", flaky)
    outcome = generate_verified_outcome(11, 3, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 2
    assert calls == [11, derive_seed(11, 1), derive_seed(11, 2)]
    # The puzzle carries the seed that built it, so its id rebuilds it directly.
    assert outcome.puzzle.seed == derive_seed(11, 2)
    monkeypatch.undo()
    assert (
        regenerate(outcome.puzzle.puzzle_id, catalog=CATALOG, topic_exists=topic_exists)
        == outcome.puzzle
    )


def test_an_ambiguous_candidate_is_retried_not_returned(monkeypatch):
    real_generate = generator_module.generate
    attempts: list[int] = []

    def sometimes_ambiguous(seed, level, catalog):
        attempts.append(seed)
        puzzle = real_generate(seed, level, catalog)
        if len(attempts) == 1:
            # 1, 2, 4, □, □ reads two ways.
            return make_puzzle([1, 2, 4, 7, 11], [3, 4], level=3, kind="growing", seed=seed)
        return puzzle

    monkeypatch.setattr(generator_module, "generate", sometimes_ambiguous)
    outcome = generate_verified_outcome(3, 3, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 1
    assert verify(outcome.puzzle, catalog=CATALOG, topic_exists=topic_exists).ok


def test_nothing_is_returned_when_every_attempt_fails():
    with pytest.raises(PuzzleGenerationFailed, match=r"sequences.*unknown_topic"):
        generate_verified(1, 1, catalog=CATALOG, topic_exists=lambda _id: False, max_attempts=3)


def test_regenerate_rejects_bad_and_old_ids():
    puzzle = build(9, 2)

    with pytest.raises(InvalidPuzzleId):
        regenerate(puzzle.puzzle_id[:-4] + "0000", catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(OutdatedPuzzleId):
        regenerate(make_sequence_id("0", 2, 9), catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(InvalidPuzzleId, match="generator version"):
        regenerate(make_sequence_id("9", 2, 9), catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(InvalidPuzzleId):
        regenerate("mnc-3-1-2-16-8889", catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(PuzzleRejected, match="unknown_topic"):
        regenerate(puzzle.puzzle_id, catalog=CATALOG, topic_exists=lambda _id: False)


# ---- the fingerprint: what version 1 makes, seed by seed ----


def fingerprints() -> list[str]:
    prints = []
    for seed in range(SNAPSHOT_SEEDS):
        puzzle = build(seed, seed % 3 + 1)
        prints.append(hashlib.sha256(puzzle.model_dump_json().encode("utf-8")).hexdigest()[:16])
    return prints


def test_the_output_for_a_seed_does_not_change_without_a_version_bump():
    """Written by `uv run python -m tests.sequences.test_generation`.

    If this fails, the generator (or the rules, hints or levels it uses) now
    gives another puzzle for the same seed. Bump GENERATOR_VERSION, so ids
    already handed out answer 410, and write the file again.
    """
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert snapshot["generator_version"] == GENERATOR_VERSION
    assert snapshot["seeds"] == SNAPSHOT_SEEDS
    now = fingerprints()
    changed = [
        seed
        for seed, (old, new) in enumerate(zip(snapshot["fingerprints"], now, strict=True))
        if old != new
    ]
    assert changed == [], f"{len(changed)} seeds changed, first: {changed[:5]}"


if __name__ == "__main__":
    payload = {
        "generator_version": GENERATOR_VERSION,
        "seeds": SNAPSHOT_SEEDS,
        "fingerprints": fingerprints(),
    }
    SNAPSHOT.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {SNAPSHOT_SEEDS} fingerprints from generator version {GENERATOR_VERSION}")
