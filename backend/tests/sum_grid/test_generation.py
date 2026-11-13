"""The generator with the verifier: every grid is valid, and the same seed gives the same one."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import app.puzzles.types.sum_grid.generator as generator_module
from app.puzzles.core import GenerationError
from app.puzzles.core.ids import MAX_SEED, InvalidPuzzleId, OutdatedPuzzleId, derive_seed
from app.puzzles.types.sum_grid.generator import deduction_order, generate
from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import GENERATOR_VERSION, LEVELS, step_topic_ids
from app.puzzles.types.sum_grid.models import Line, MistakeRule, SumGridPuzzle
from app.puzzles.types.sum_grid.public import to_public
from app.puzzles.types.sum_grid.verified import (
    PuzzleGenerationFailed,
    PuzzleRejected,
    generate_verified,
    generate_verified_outcome,
    regenerate,
)
from app.puzzles.types.sum_grid.verifier import count_solutions, verify
from tests.sum_grid.support import make_catalog, make_puzzle, topic_exists

CATALOG = make_catalog()
SNAPSHOT = Path(__file__).parent.parent / "snapshots" / "sum_grid_v1.json"
SNAPSHOT_SEEDS = 600

seeds = st.integers(min_value=0, max_value=MAX_SEED)
levels = st.sampled_from(sorted(LEVELS))


def build(seed: int, level: int) -> SumGridPuzzle:
    return generate_verified(seed, level, catalog=CATALOG, topic_exists=topic_exists)


def solved(puzzle: SumGridPuzzle) -> list[list[int]]:
    grid = [[value or 0 for value in row] for row in puzzle.cells]
    for step in puzzle.steps:
        grid[step.cell.row][step.cell.col] = step.answer
    return grid


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
    size = spec.size
    grid = solved(puzzle)

    assert puzzle.size == size == len(puzzle.cells)
    assert all(spec.min_value <= value <= spec.max_value for row in grid for value in row)
    assert puzzle.row_targets == [sum(row) for row in grid]
    assert puzzle.col_targets == [sum(grid[r][c] for r in range(size)) for c in range(size)]
    assert max(*puzzle.row_targets, *puzzle.col_targets) <= spec.max_target
    assert spec.min_blanks <= len(puzzle.steps) <= spec.max_blanks
    assert puzzle.topic_ids == step_topic_ids(level)
    # Every row and every column shows at least one number.
    for index in range(size):
        assert any(value is not None for value in puzzle.cells[index])
        assert any(puzzle.cells[r][index] is not None for r in range(size))
    for step in puzzle.steps:
        values = [d.value for d in step.distractors]
        assert len(values) == 3 and len({step.answer, *values}) == 4
        assert all(0 <= value <= spec.option_max for value in values)


@settings(max_examples=300, deadline=None)
@given(seed=seeds, level=levels)
def test_every_step_can_be_worked_out_when_its_turn_comes(seed, level):
    puzzle = build(seed, level)
    size = puzzle.size
    unknown = {(step.cell.row, step.cell.col) for step in puzzle.steps}

    for step in puzzle.steps:
        cell = (step.cell.row, step.cell.col)
        if step.line.kind == "row":
            assert step.line.index == cell[0]
            line = [(cell[0], c) for c in range(size)]
        else:
            assert step.line.index == cell[1]
            line = [(r, cell[1]) for r in range(size)]
            # A column is only recorded when the row still has another blank.
            assert any((cell[0], c) in unknown for c in range(size) if c != cell[1])
        assert [position for position in line if position in unknown] == [cell]
        unknown.remove(cell)
    assert not unknown


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels)
def test_only_the_last_hint_shows_the_answer(seed, level):
    puzzle = build(seed, level)

    for step in puzzle.steps:
        look, total, worked = step.hints
        # The numbers in a hint, read here and not with the library's reader.
        numbers = [{int(n) for n in re.findall(r"\d+", text)} for text in (look, total, worked)]
        assert numbers[0] == set(), look
        assert step.answer not in numbers[1], (total, step.answer)
        assert step.answer in numbers[2], (worked, step.answer)


@settings(max_examples=200, deadline=None)
@given(seed=seeds, level=levels)
def test_the_public_puzzle_hides_the_blanks_and_offers_the_answer_once(seed, level):
    puzzle = build(seed, level)
    public = to_public(puzzle)

    assert public.game == "sum-grid"
    assert public.cells == puzzle.cells
    assert (public.row_targets, public.col_targets) == (puzzle.row_targets, puzzle.col_targets)
    assert public.length == len(puzzle.steps) == len(public.steps)
    for shown, step in zip(public.steps, puzzle.steps, strict=True):
        assert (shown.cell, shown.line) == (step.cell, step.line)
        assert public.cells[step.cell.row][step.cell.col] is None
        assert shown.options.count(step.answer) == 1
        assert sorted(shown.options) == sorted([step.answer, *(d.value for d in step.distractors)])
    text = public.model_dump_json()
    for forbidden in ('"answer"', "rule", "error_pattern", "hint_source", '"hints"', '"seed"'):
        assert forbidden not in text


# ---- the deduction order ----


def test_deduction_order_takes_the_first_solvable_blank_and_prefers_its_row():
    #  □ □ .        (0,0) has another blank in its row, so it comes from its column;
    #  . □ .        then (0,1) is alone in the top row; (1,1) was alone in its row all along.
    #  . . .
    order = deduction_order(3, frozenset({(0, 0), (0, 1), (1, 1)}))

    assert order == [
        ((0, 0), Line(kind="col", index=0)),
        ((0, 1), Line(kind="row", index=0)),
        ((1, 1), Line(kind="row", index=1)),
    ]
    # Both lines work for a lone blank: the row is the one recorded.
    assert deduction_order(3, frozenset({(1, 1)})) == [((1, 1), Line(kind="row", index=1))]
    assert deduction_order(2, frozenset({(0, 1), (1, 0)})) == [
        ((0, 1), Line(kind="row", index=0)),
        ((1, 0), Line(kind="row", index=1)),
    ]


def test_deduction_order_is_none_when_every_line_has_two_unknowns():
    rectangle = frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})
    assert deduction_order(3, rectangle) is None
    assert deduction_order(2, rectangle) is None
    # One more blank elsewhere does not help; one corner visible does.
    assert deduction_order(3, rectangle | {(2, 2)}) is None
    assert deduction_order(3, rectangle - {(1, 1)}) is not None


# ---- what the levels make, over many seeds ----


def test_each_level_makes_what_it_says():
    for level, spec in LEVELS.items():
        blanks: Counter = Counter()
        kinds: Counter = Counter()
        for seed in range(300):
            puzzle = build(seed, level)
            blanks[len(puzzle.steps)] += 1
            kinds.update(step.line.kind for step in puzzle.steps)
        assert set(blanks) == set(range(spec.min_blanks, spec.max_blanks + 1)), level
        if spec.size == 3:
            # A 3 by 3 grid is solved in both directions.
            assert kinds["row"] > 100 and kinds["col"] > 100, level


def test_linked_rules_on_the_levels_own_topics_come_first_and_fillers_last():
    for level, spec in LEVELS.items():
        for seed in range(200):
            for step in build(seed, level).steps:
                tiers = []
                for distractor in step.distractors:
                    link = CATALOG.link_for(distractor.rule, spec.topic_ids[0])
                    if distractor.rule is MistakeRule.NEAR_MISS:
                        tiers.append(3)
                    elif link is None:
                        tiers.append(2)
                    else:
                        tiers.append(0 if link.topic_id in spec.topic_ids else 1)
                    assert distractor.error_pattern_id == (
                        link.error_pattern_id if link is not None else None
                    )
                assert tiers == sorted(tiers), step.distractors
                assert {source.error_pattern_id for source in step.hint_source} == {
                    d.error_pattern_id for d in step.distractors if d.error_pattern_id
                }
                for source in step.hint_source:
                    assert source.next_move == CATALOG.get(source.error_pattern_id).next_move


def test_level_three_usually_has_a_multiple_of_ten_to_misread():
    offered = steps = 0
    for seed in range(300):
        for step in build(seed, 3).steps:
            steps += 1
            offered += any(d.rule is MistakeRule.TENS_AS_ONES for d in step.distractors)
    # A preference, not a rule: most steps, never a promise of all.
    assert offered / steps > 0.7


def test_the_generator_does_not_use_the_verifier():
    source = Path(generator_module.__file__).read_text("utf-8")

    assert "sum_grid.verifier" not in source
    assert "count_solutions" not in source


# ---- seeds, ids, retries ----


def test_the_same_seed_always_gives_the_same_puzzle_and_levels_differ():
    assert generate(41, 2, CATALOG) == generate(41, 2, CATALOG)
    assert generate(41, 2, CATALOG) != generate(42, 2, CATALOG)
    assert generate(41, 2, CATALOG).puzzle_id == make_sum_grid_id(GENERATOR_VERSION, 2, 41)
    assert generate(41, 2, CATALOG).puzzle_id.startswith("sg-1-2-")
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
            raise GenerationError("no way to blank the cells")
        return real_generate(seed, level, catalog)

    monkeypatch.setattr(generator_module, "generate", flaky)
    outcome = generate_verified_outcome(11, 3, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 2
    assert calls == [11, derive_seed(11, 1), derive_seed(11, 2)]
    assert outcome.puzzle.seed == derive_seed(11, 2)


def test_a_grid_with_two_solutions_is_retried_not_returned(monkeypatch):
    real_generate = generator_module.generate
    attempts: list[int] = []

    def sometimes_ambiguous(seed, level, catalog):
        attempts.append(seed)
        if len(attempts) == 1:
            corners = [(0, 0, "row"), (0, 1, "row"), (1, 0, "row"), (1, 1, "row")]
            return make_puzzle([[2, 5, 9], [4, 3, 8], [7, 6, 1]], corners, level=2, seed=seed)
        return real_generate(seed, level, catalog)

    monkeypatch.setattr(generator_module, "generate", sometimes_ambiguous)
    outcome = generate_verified_outcome(3, 2, catalog=CATALOG, topic_exists=topic_exists)

    assert outcome.retries == 1
    puzzle = outcome.puzzle
    assert count_solutions(puzzle.cells, puzzle.row_targets, puzzle.col_targets, 1, 9).count == 1


def test_nothing_is_returned_when_every_attempt_fails():
    with pytest.raises(PuzzleGenerationFailed, match=r"sum-grid.*unknown_topic"):
        generate_verified(1, 1, catalog=CATALOG, topic_exists=lambda _id: False, max_attempts=3)


def test_regenerate_rejects_bad_and_old_ids():
    puzzle = build(9, 2)

    with pytest.raises(InvalidPuzzleId):
        regenerate(puzzle.puzzle_id[:-4] + "0000", catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(OutdatedPuzzleId):
        regenerate(make_sum_grid_id("0", 2, 9), catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(InvalidPuzzleId, match="generator version"):
        regenerate(make_sum_grid_id("9", 2, 9), catalog=CATALOG, topic_exists=topic_exists)
    with pytest.raises(InvalidPuzzleId):
        regenerate("seq-1-1-1-517c", catalog=CATALOG, topic_exists=topic_exists)
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
    """Written by `uv run python -m tests.sum_grid.test_generation`.

    If this fails, the generator (or the rules, hints or levels it uses) now
    gives another puzzle for the same seed. Bump GENERATOR_VERSION, so ids
    already handed out answer 410, and write the file again.
    """
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert snapshot["generator_version"] == GENERATOR_VERSION
    assert snapshot["seeds"] == SNAPSHOT_SEEDS
    pairs = zip(snapshot["fingerprints"], fingerprints(), strict=True)
    changed = [seed for seed, (old, new) in enumerate(pairs) if old != new]
    assert changed == [], f"{len(changed)} seeds changed, first: {changed[:5]}"


if __name__ == "__main__":
    payload = {
        "generator_version": GENERATOR_VERSION,
        "seeds": SNAPSHOT_SEEDS,
        "fingerprints": fingerprints(),
    }
    SNAPSHOT.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {SNAPSHOT_SEEDS} fingerprints from generator version {GENERATOR_VERSION}")
