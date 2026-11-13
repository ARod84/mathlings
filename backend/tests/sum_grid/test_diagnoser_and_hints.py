"""The diagnoser, the rule catalog and the hint templates, on hand-built grids."""

import pytest

from app.puzzles.core.catalog import MisconceptionResolutionError
from app.puzzles.types.sum_grid.diagnoser import Diagnosis, diagnose
from app.puzzles.types.sum_grid.hints import build_hints, line_name, quoted_numbers
from app.puzzles.types.sum_grid.levels import (
    TOPIC_ADD_SUBTRACT_7,
    TOPIC_ADDING_WITHIN_100,
    TOPIC_FLUENT_WITHIN_20,
    TOPIC_THREE_SMALL_NUMBERS,
    TOPIC_UNKNOWN_ADD_SUB,
)
from app.puzzles.types.sum_grid.misconceptions import RULE_PATTERNS, resolve_catalog
from app.puzzles.types.sum_grid.models import Line, SumGridPuzzle
from app.puzzles.types.sum_grid.models import MistakeRule as R
from app.puzzles.types.sum_grid.report import format_catalog, format_puzzle
from app.puzzles.types.sum_grid.rules import StepView
from tests.sum_grid.support import (
    ERROR_PATTERN_ROWS,
    TOPIC_EQUALS_SIGN,
    TOPIC_GROUPING,
    TOPIC_TWO_DIGITS,
    TOPIC_WITHIN_1000,
    large,
    make_catalog,
    make_puzzle,
    medium,
    small,
    step_back,
)

CATALOG = make_catalog()


def answer(puzzle: SumGridPuzzle, value: int, step: int = 0) -> Diagnosis:
    return diagnose(puzzle, step, value, catalog=CATALOG, step_back=step_back)


# ---- the catalog ----


def test_the_rule_table_is_the_hand_reviewed_one():
    table = [
        (
            rule.value,
            pattern.error_pattern_id if pattern else None,
            pattern and pattern.reteach_topic_id,
        )
        for rule, pattern in CATALOG.table()
    ]

    assert table == [
        ("ADD_VISIBLE", f"{TOPIC_UNKNOWN_ADD_SUB}#0", TOPIC_EQUALS_SIGN),
        ("FORGOT_ONE", f"{TOPIC_THREE_SMALL_NUMBERS}#2", None),
        ("PLACE_VALUE_SLIP", f"{TOPIC_ADD_SUBTRACT_7}#1", TOPIC_WITHIN_1000),
        ("CARRY_DROPPED", f"{TOPIC_ADD_SUBTRACT_7}#2", None),
        ("TENS_AS_ONES", f"{TOPIC_ADDING_WITHIN_100}#0", TOPIC_TWO_DIGITS),
        ("WRONG_LINE", None, None),
        ("OFF_BY_ONE_OVER", None, None),
        ("OFF_BY_ONE_UNDER", None, None),
        ("NEAR_MISS", None, None),
    ]
    assert "WRONG_LINE         (none)" in format_catalog(CATALOG)
    assert R.WRONG_LINE not in RULE_PATTERNS


def test_a_missing_pattern_fails_loudly():
    def without_tens(topic_id):
        return [row for row in ERROR_PATTERN_ROWS[topic_id] if "multiple of ten" not in row.pattern]

    with pytest.raises(MisconceptionResolutionError, match=r"TENS_AS_ONES.*found 0"):
        resolve_catalog(without_tens)


# ---- the diagnoser ----


def test_a_right_answer_and_an_unexplained_wrong_one():
    puzzle = small()

    assert answer(puzzle, 6) == Diagnosis(correct=True)
    assert answer(puzzle, 30) == Diagnosis(correct=False, unrecognized=True)


def test_add_visible_maps_to_its_pattern_and_the_patterns_own_reteach_topic():
    # 3 + □ = 9 answered with 12. The pattern is on "Unknown in Addition &
    # Subtraction", which a level 1 step practises, so its reteach topic is used.
    diagnosis = answer(small(), 12)

    assert diagnosis.matched_rules == [R.ADD_VISIBLE]
    assert diagnosis.error_pattern_id == f"{TOPIC_UNKNOWN_ADD_SUB}#0"
    assert diagnosis.reteach_topic_id == TOPIC_EQUALS_SIGN


def test_forgot_one_maps_to_its_pattern_and_steps_back_through_the_graph():
    # □ + 4 + 7 = 13 (the left column) answered with 13 − 7 = 6.
    puzzle = medium()

    diagnosis = answer(puzzle, 6)

    assert diagnosis.matched_rules == [R.FORGOT_ONE]
    assert diagnosis.error_pattern_id == f"{TOPIC_THREE_SMALL_NUMBERS}#2"
    # That pattern names no topic, so the prerequisite graph decides.
    assert diagnosis.reteach_topic_id == step_back(TOPIC_THREE_SMALL_NUMBERS) == TOPIC_GROUPING


def test_place_value_slip_maps_to_smaller_from_larger_and_its_reteach_topic():
    # 20 + 37 + □ = 85 answered with 32: 85 − 57 done column by column.
    diagnosis = answer(large(), 32)

    assert diagnosis.matched_rules == [R.PLACE_VALUE_SLIP]
    assert diagnosis.error_pattern_id == f"{TOPIC_ADD_SUBTRACT_7}#1"
    assert diagnosis.reteach_topic_id == TOPIC_WITHIN_1000


def test_a_dropped_carry_maps_to_its_own_pattern_not_to_smaller_from_larger():
    # 31 + 12 + □ = 73 is safe. A line with a carry in its known cells:
    # 28 + 37 + □ = 99 answered with 99 − 55 = 44.
    grid = [[28, 37, 34], [15, 20, 22], [31, 12, 30]]
    puzzle = make_puzzle(
        grid, [(0, 2, "row"), (1, 0, "row"), (2, 1, "col"), (2, 2, "row")], level=3
    )

    diagnosis = answer(puzzle, 44)

    assert diagnosis.matched_rules == [R.CARRY_DROPPED]
    assert diagnosis.error_pattern_id == f"{TOPIC_ADD_SUBTRACT_7}#2"
    # The pattern names no topic; the graph steps back from the level's topic.
    assert diagnosis.reteach_topic_id == step_back(TOPIC_ADD_SUBTRACT_7) == TOPIC_WITHIN_1000


def test_tens_as_ones_maps_to_its_pattern_on_the_levels_second_topic():
    # The same step answered with 46: the 20 read as 2.
    diagnosis = answer(large(), 46)

    assert diagnosis.matched_rules == [R.TENS_AS_ONES]
    assert diagnosis.error_pattern_id == f"{TOPIC_ADDING_WITHIN_100}#0"
    # "Adding within 100" is not the level's primary topic, but the step
    # practises it, so the pattern's own reteach topic is the one to use.
    assert diagnosis.reteach_topic_id == TOPIC_TWO_DIGITS


def test_add_visible_at_level_three_keeps_its_pattern_but_reteaches_for_the_levels_topic():
    # Its pattern belongs to a topic level 3 does not practise.
    diagnosis = answer(large(), 142)

    assert diagnosis.matched_rules == [R.ADD_VISIBLE]
    assert diagnosis.error_pattern_id == f"{TOPIC_UNKNOWN_ADD_SUB}#0"
    assert diagnosis.reteach_topic_id == step_back(TOPIC_ADD_SUBTRACT_7) == TOPIC_WITHIN_1000


def test_an_unlinked_mistake_is_still_named_and_still_has_somewhere_to_step_back_to():
    # 3 + □ = 9 answered from the other line's target: 11 − 3 = 8.
    diagnosis = answer(small(), 8)

    assert diagnosis.matched_rules == [R.WRONG_LINE]
    assert diagnosis.error_pattern_id is None
    assert diagnosis.reteach_topic_id == step_back(TOPIC_FLUENT_WITHIN_20)
    assert diagnosis.unrecognized is False


def test_each_step_is_diagnosed_with_the_earlier_answers_in_place():
    puzzle = large()

    # The bottom row's last blank: 31 + 12 + □ = 73, the 12 solved one step before.
    assert answer(puzzle, 30, step=3).correct is True
    assert answer(puzzle, 73 + 43, step=3).matched_rules == [R.ADD_VISIBLE]
    assert answer(puzzle, 73 - 31, step=3).matched_rules == [R.FORGOT_ONE]
    # The middle column: 37 + 40 + □ = 89; the 40 read as 4 gives 89 − 41.
    assert answer(puzzle, 48, step=2).matched_rules == [R.TENS_AS_ONES]


# ---- hints ----


def test_lines_are_named_in_words_so_no_number_is_on_show():
    assert [line_name(Line(kind="row", index=i), 3) for i in range(3)] == [
        "the top row",
        "the middle row",
        "the bottom row",
    ]
    assert [line_name(Line(kind="col", index=i), 3) for i in range(3)] == [
        "the left column",
        "the middle column",
        "the right column",
    ]
    assert line_name(Line(kind="row", index=1), 2) == "the bottom row"
    assert line_name(Line(kind="col", index=1), 2) == "the right column"


def test_hints_for_a_two_by_two_line():
    view = StepView(target=9, known_cells=(3,), crossing_target=11)

    assert build_hints(Line(kind="row", index=0), 2, view) == [
        "Look at the top row. Only one number is missing there.",
        "The top row must make 9. The other number is 3. What do you add to 3 to make 9?",
        "9 − 3 = 6, so the missing number is 6.",
    ]


def test_hints_for_a_three_by_three_line():
    view = StepView(target=85, known_cells=(20, 37), crossing_target=80)

    assert build_hints(Line(kind="col", index=2), 3, view) == [
        "Look at the right column. Only one number is missing there.",
        "The right column must make 85. The other numbers make 57. "
        "What do you add to 57 to make 85?",
        "85 − 57 = 28, so the missing number is 28.",
    ]
    assert quoted_numbers(Line(kind="col", index=2), 3, view) == {85, 57}


def test_the_first_hint_has_no_number_even_when_the_answer_is_one_two_or_three():
    for puzzle in (small(), medium(), large()):
        for step in puzzle.steps:
            assert not any(character.isdigit() for character in step.hints[0])


# ---- the report's printing ----


def test_format_puzzle_shows_the_grid_the_order_and_the_lines():
    text = format_puzzle(large())

    assert "20 | 37 |  □ | 85" in text
    assert " □ | 40 | 22 | 77" in text
    assert "66 | 89 | 80" in text
    assert "step 1: row 1, column 3, from the top row -> 28" in text
    assert "step 3: row 3, column 2, from the middle column -> 12" in text
    assert "PLACE_VALUE_SLIP  -> mt_SrrsLiJkr3#1" in text
