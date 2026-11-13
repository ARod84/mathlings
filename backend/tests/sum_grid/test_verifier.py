"""The verifier on grids written by hand: one solution, no guessing, and every other rule."""

from pathlib import Path

import pytest

from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import GENERATOR_VERSION, TOPIC_UNKNOWN_ADD_SUB
from app.puzzles.types.sum_grid.models import (
    Cell,
    Distractor,
    Line,
    MistakeRule,
    SumGridPuzzle,
)
from app.puzzles.types.sum_grid.verifier import FailureName as F
from app.puzzles.types.sum_grid.verifier import VerificationResult, count_solutions, verify
from tests.sum_grid.support import (
    LARGE,
    MEDIUM,
    MEDIUM_BLANKS,
    SMALL,
    large,
    make_catalog,
    make_puzzle,
    medium,
    small,
    topic_exists,
)

CATALOG = make_catalog()


def check(puzzle: SumGridPuzzle) -> VerificationResult:
    return verify(puzzle, catalog=CATALOG, topic_exists=topic_exists)


def names(puzzle: SumGridPuzzle) -> set[F]:
    return check(puzzle).names


# ---- valid grids ----


def test_hand_built_valid_grids_pass_at_every_level():
    for puzzle in (small(), medium(), large()):
        result = check(puzzle)
        assert result.ok, result.failures

    # The example from the spec: 3 | □ | 9 over □ | 5 | 7, columns 5 and 11.
    example = small()
    assert example.cells == [[3, None], [None, 5]]
    assert (example.row_targets, example.col_targets) == ([9, 7], [5, 11])
    assert [step.answer for step in example.steps] == [6, 2]


def test_a_blank_may_be_solved_from_its_column_and_a_later_one_from_a_row_it_completed():
    puzzle = large()

    assert [(s.cell.row, s.cell.col, s.line.kind) for s in puzzle.steps] == [
        (0, 2, "row"),
        (1, 0, "row"),
        (2, 1, "col"),  # the bottom row still has another blank at this point
        (2, 2, "row"),  # and now it does not
    ]
    assert check(puzzle).ok


# ---- how many solutions ----


def test_count_solutions_finds_the_one_solution_of_a_valid_grid():
    puzzle = medium()

    found = count_solutions(puzzle.cells, puzzle.row_targets, puzzle.col_targets, 1, 9)

    assert found.count == 1
    assert found.first == MEDIUM
    assert 1 <= found.nodes <= 20


def test_count_solutions_stops_at_the_second_and_reports_none_when_there_is_none():
    # Rows 1–2 × columns 1–2 blank: every one of those lines has two unknowns.
    cells = [[None, None, 9], [None, None, 8], [7, 6, 1]]
    two = count_solutions(cells, [16, 15, 14], [13, 14, 18], 1, 9)
    assert two.count == 2

    # A target no numbers in range can reach.
    none = count_solutions([[3, None], [None, 5]], [30, 7], [5, 11], 1, 9)
    assert (none.count, none.first) == (0, None)
    # A 2×2 with two blanks is always unique: each blank is alone in its row.
    assert count_solutions([[3, None], [None, 5]], [9, 7], [5, 11], 1, 9).count == 1


def test_a_grid_with_more_than_one_solution_is_rejected():
    # The four blanks are the corners of a rectangle. Adding 1 to two opposite
    # corners and taking 1 from the other two keeps every target:
    #   2 5      3 4
    #   4 3  ->  3 4
    corners = [(0, 0, "row"), (0, 1, "row"), (1, 0, "row"), (1, 1, "row")]
    result = check(make_puzzle(MEDIUM, corners, level=2))

    assert F.MULTIPLE_SOLUTIONS in result.names
    # And no order can solve it without guessing: the first step already has
    # two unknowns in its line.
    assert F.NEEDS_A_GUESS in result.names
    first_guess = next(f for f in result.failures if f.name is F.NEEDS_A_GUESS)
    assert first_guess.step == 0
    assert F.WRONG_ANSWER not in result.names


def test_its_counterpart_with_one_corner_visible_passes():
    # The same grid with one of the four corners on show has one solution.
    assert check(medium()).ok
    assert len(medium().steps) == 3


# ---- no guessing ----


def test_a_stored_order_that_needs_a_guess_is_rejected_though_the_grid_has_one_solution():
    good = medium()
    assert [(s.cell.row, s.cell.col, s.line.kind) for s in good.steps] == MEDIUM_BLANKS

    # The same blanks and answers, with the first two steps the other way
    # round: the top row is asked for while it still has two blanks.
    swapped = good.model_copy(update={"steps": [good.steps[1], good.steps[0], good.steps[2]]})
    result = check(swapped)

    assert result.names == {F.NEEDS_A_GUESS}
    (failure,) = result.failures
    assert failure.step == 0
    assert "(0, 0), (0, 1)" in failure.detail
    # The search still finds exactly one solution: the grid is fine, the order is not.
    found = count_solutions(swapped.cells, swapped.row_targets, swapped.col_targets, 1, 9)
    assert found.count == 1


def test_the_line_of_a_step_must_be_one_the_cell_is_in():
    good = medium()
    wrong_line = good.steps[2].model_copy(update={"line": Line(kind="row", index=2)})
    result = check(good.model_copy(update={"steps": [*good.steps[:2], wrong_line]}))

    assert result.names == {F.NEEDS_A_GUESS}
    off_grid = good.steps[2].model_copy(update={"line": Line(kind="col", index=7)})
    assert names(good.model_copy(update={"steps": [*good.steps[:2], off_grid]})) == {
        F.NEEDS_A_GUESS
    }


# ---- answers and targets ----


def test_a_wrong_stored_answer_is_caught_by_the_search():
    good = small()
    wrong = good.steps[0].model_copy(update={"answer": 7})
    result = check(good.model_copy(update={"steps": [wrong, good.steps[1]]}))

    assert {F.WRONG_ANSWER, F.TARGET_MISMATCH} <= result.names
    detail = next(f.detail for f in result.failures if f.name is F.WRONG_ANSWER)
    assert "the grid solves to [6, 2]" in detail


def test_targets_must_be_the_sums_of_the_solution():
    good = small()

    # A row target that the stored numbers do not add up to, and that nothing can meet.
    impossible = good.model_copy(update={"row_targets": [9, 8]})
    assert {F.NO_SOLUTION, F.TARGET_MISMATCH} <= names(impossible)

    # Row and column changed together: there is a solution, but not the stored one.
    shifted = good.model_copy(update={"row_targets": [10, 7], "col_targets": [5, 12]})
    assert {F.WRONG_ANSWER, F.TARGET_MISMATCH} <= names(shifted)


def test_values_and_targets_must_be_in_the_levels_range():
    # Level 1 cells are 1 to 9 and its targets at most 18.
    assert F.VALUE_OUT_OF_RANGE in names(
        make_puzzle([[12, 6], [2, 5]], [(0, 1, "row"), (1, 0, "row")], level=1)
    )
    answer_too_big = make_puzzle([[3, 11], [2, 5]], [(0, 1, "row"), (1, 0, "row")], level=1)
    assert F.VALUE_OUT_OF_RANGE in names(answer_too_big)
    assert F.TARGET_OUT_OF_RANGE in names(
        make_puzzle([[9, 9], [9, 9]], [(0, 1, "row"), (1, 0, "row")], level=1).model_copy(
            update={"row_targets": [19, 18]}
        )
    )

    # Level 3 cells are 10 to 60 and no line may pass 100.
    heavy = [[50, 37, 28], [15, 40, 22], [31, 12, 30]]
    found = names(
        make_puzzle(heavy, [(0, 2, "row"), (1, 0, "row"), (2, 1, "col"), (2, 2, "row")], level=3)
    )
    assert F.TARGET_OUT_OF_RANGE in found
    small_cell = [[20, 37, 28], [15, 40, 22], [31, 12, 9]]
    assert F.VALUE_OUT_OF_RANGE in names(
        make_puzzle(
            small_cell, [(0, 2, "row"), (1, 0, "row"), (2, 1, "col"), (0, 0, "row")], level=3
        )
    )


# ---- where the blanks are ----


def test_the_number_of_blanks():
    one = make_puzzle(SMALL, [(0, 1, "row")], level=1)
    assert names(one) == {F.BAD_BLANK_COUNT}
    two = make_puzzle(MEDIUM, [(0, 0, "row"), (1, 1, "row")], level=2)
    assert names(two) == {F.BAD_BLANK_COUNT}
    six = make_puzzle(
        LARGE,
        [(0, 0, "row"), (1, 1, "row"), (2, 2, "row"), (0, 1, "col"), (1, 2, "col"), (2, 0, "col")],
        level=3,
    )
    assert F.BAD_BLANK_COUNT in names(six)


def test_every_row_and_column_keeps_a_visible_number():
    # A whole row blank in a 2×2. The columns still pin both numbers down, so
    # the grid has one solution; it is rejected because the row shows nothing.
    row = make_puzzle(SMALL, [(0, 0, "col"), (0, 1, "col")], level=1)
    assert names(row) == {F.LINE_WITHOUT_A_NUMBER}
    assert check(row).failures[0].detail == "row 0 is blank from end to end"
    # Asked for from the row itself, each blank would also be a guess.
    from_row = make_puzzle(SMALL, [(0, 0, "row"), (0, 1, "row")], level=1)
    assert {F.LINE_WITHOUT_A_NUMBER, F.NEEDS_A_GUESS} <= names(from_row)

    # A whole column blank in a 3×3: each blank is alone in its row, so the
    # grid has one solution and needs no guess, and is still not allowed.
    column = make_puzzle(MEDIUM, [(0, 1, "row"), (1, 1, "row"), (2, 1, "row")], level=2)
    result = check(column)
    assert result.names == {F.LINE_WITHOUT_A_NUMBER}
    assert result.failures[0].detail == "col 1 is blank from end to end"


def test_the_steps_must_be_the_blanks_each_once():
    good = medium()

    assert names(good.model_copy(update={"steps": good.steps[:2]})) == {F.BAD_STEPS}
    twice = [good.steps[0], good.steps[0], good.steps[2]]
    assert names(good.model_copy(update={"steps": twice})) == {F.BAD_STEPS}
    elsewhere = good.steps[2].model_copy(update={"cell": Cell(row=2, col=2)})
    assert names(good.model_copy(update={"steps": [*good.steps[:2], elsewhere]})) == {F.BAD_STEPS}


def test_the_grid_must_have_the_levels_shape():
    good = medium()

    assert names(good.model_copy(update={"level": 1})) == {F.PUZZLE_ID_MISMATCH, F.BAD_GRID}
    ragged = [good.cells[0], good.cells[1][:2], good.cells[2]]
    assert names(good.model_copy(update={"cells": ragged})) == {F.BAD_GRID}
    assert names(good.model_copy(update={"col_targets": [13, 14]})) == {F.BAD_GRID}
    assert names(good.model_copy(update={"size": 2})) == {F.BAD_GRID}


# ---- identity, topics ----


def test_the_id_must_describe_the_puzzle():
    good = small()

    assert names(good.model_copy(update={"seed": 8})) == {F.PUZZLE_ID_MISMATCH}
    other = good.model_copy(update={"puzzle_id": make_sum_grid_id(GENERATOR_VERSION, 2, 7)})
    assert names(other) == {F.PUZZLE_ID_MISMATCH}
    assert names(good.model_copy(update={"generator_version": "0"})) == {F.UNSUPPORTED_PUZZLE}
    assert names(good.model_copy(update={"level": 9})) == {F.UNSUPPORTED_PUZZLE}


def test_topics_are_the_levels_and_must_exist():
    good = small()

    swapped = good.model_copy(update={"topic_ids": medium().topic_ids})
    assert names(swapped) == {F.WRONG_TOPICS}
    result = verify(good, catalog=CATALOG, topic_exists=lambda _topic_id: False)
    assert result.names == {F.UNKNOWN_TOPIC}


# ---- options ----


def with_distractors(puzzle: SumGridPuzzle, distractors: list[Distractor]) -> SumGridPuzzle:
    step = puzzle.steps[0].model_copy(update={"distractors": distractors})
    return puzzle.model_copy(update={"steps": [step, *puzzle.steps[1:]]})


def test_distractors_recompute_from_their_rules():
    good = small()  # 3 + □ = 9, the other line's target is 11
    add_visible, wrong_line, over = good.steps[0].distractors
    assert [(d.value, d.rule) for d in (add_visible, wrong_line, over)] == [
        (12, MistakeRule.ADD_VISIBLE),
        (8, MistakeRule.WRONG_LINE),
        (7, MistakeRule.OFF_BY_ONE_OVER),
    ]
    assert add_visible.error_pattern_id == f"{TOPIC_UNKNOWN_ADD_SUB}#0"

    assert names(with_distractors(good, [add_visible, wrong_line])) == {F.DISTRACTOR_COUNT}
    twice = [add_visible, wrong_line, wrong_line]
    assert F.DUPLICATE_DISTRACTOR in names(with_distractors(good, twice))
    is_answer = [add_visible, wrong_line, Distractor(value=6, rule=MistakeRule.OFF_BY_ONE_OVER)]
    assert names(with_distractors(good, is_answer)) == {F.DISTRACTOR_EQUALS_ANSWER}
    invented = [add_visible, wrong_line, Distractor(value=4, rule=MistakeRule.OFF_BY_ONE_OVER)]
    assert names(with_distractors(good, invented)) == {F.DISTRACTOR_RULE_MISMATCH}
    # FORGOT_ONE needs two known numbers; a 2×2 line has one.
    not_applicable = [
        add_visible,
        wrong_line,
        Distractor(value=1, rule=MistakeRule.FORGOT_ONE, error_pattern_id="mt_Zx1xZM-RbX#2"),
    ]
    assert names(with_distractors(good, not_applicable)) == {F.DISTRACTOR_RULE_MISMATCH}


def test_a_distractor_carries_exactly_the_pattern_the_catalog_gives_its_rule():
    good = small()
    add_visible, wrong_line, over = good.steps[0].distractors

    unlinked = add_visible.model_copy(update={"error_pattern_id": None})
    assert names(with_distractors(good, [unlinked, wrong_line, over])) == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }
    invented = wrong_line.model_copy(update={"error_pattern_id": f"{TOPIC_UNKNOWN_ADD_SUB}#1"})
    assert names(with_distractors(good, [add_visible, invented, over])) == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }


def test_options_outside_the_range_and_bad_fillers():
    good = small()
    add_visible, wrong_line, _over = good.steps[0].distractors

    # Level 1 options stop at 40.
    too_big = Distractor(value=41, rule=MistakeRule.OFF_BY_ONE_OVER)
    assert F.DISTRACTOR_OUT_OF_RANGE in names(
        with_distractors(good, [add_visible, wrong_line, too_big])
    )
    filler = Distractor(value=9, rule=MistakeRule.NEAR_MISS)  # 3 away from 6
    assert check(with_distractors(good, [add_visible, wrong_line, filler])).ok
    not_near = Distractor(value=1, rule=MistakeRule.NEAR_MISS)  # 5 away is no offset
    assert names(with_distractors(good, [add_visible, wrong_line, not_near])) == {
        F.DISTRACTOR_RULE_MISMATCH
    }
    outside = Distractor(value=10, rule=MistakeRule.NEAR_MISS)  # past the cells of level 1
    assert names(with_distractors(good, [add_visible, wrong_line, outside])) == {
        F.DISTRACTOR_OUT_OF_RANGE
    }


# ---- hints ----


def with_hints(puzzle: SumGridPuzzle, hints: list[str]) -> SumGridPuzzle:
    step = puzzle.steps[0].model_copy(update={"hints": hints})
    return puzzle.model_copy(update={"steps": [step, *puzzle.steps[1:]]})


def test_hints_must_be_three_and_only_the_last_shows_the_answer():
    good = small()
    look, total, worked = good.steps[0].hints

    assert names(with_hints(good, [look, total])) == {F.HINT_COUNT}
    assert names(with_hints(good, [look, worked, worked])) == {F.HINT_REVEALS_ANSWER}
    assert names(with_hints(good, ["Look at row 6.", total, worked])) == {F.HINT_REVEALS_ANSWER}
    assert names(with_hints(good, [look, total, total])) == {F.HINT_MISSING_ANSWER}


def test_a_line_that_is_a_double_cannot_be_asked_about():
    # 6 + □ = 12: "the other number is 6" would say the answer.
    result = check(make_puzzle([[6, 6], [2, 5]], [(0, 1, "row"), (1, 0, "row")], level=1))

    assert result.names == {F.HINT_REVEALS_ANSWER}
    assert [failure.step for failure in result.failures] == [0]


# ---- independence ----


def test_the_verifier_does_not_import_the_generator():
    package = Path(__file__).parents[2] / "app" / "puzzles" / "types" / "sum_grid"
    source = (package / "verifier.py").read_text("utf-8")

    assert "sum_grid.generator" not in source
    assert "sum_grid.verified" not in source and "core.verified" not in source
    assert "sum_grid.puzzle_type" not in source
    # Not the generator's deduction, and not the replay the diagnoser uses either.
    assert "deduction_order" not in source and "step_view" not in source
    assert "from app.puzzles.types.sum_grid.rules import" in source
    assert "import_module" not in source and "from . import" not in source


@pytest.mark.parametrize("name", list(F))
def test_every_failure_name_is_exercised_by_a_test(name):
    source = Path(__file__).read_text("utf-8")
    assert f"F.{name.name}" in source, f"no test mentions {name.name}"
