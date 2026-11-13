"""Each mistake rule on 2×2 and 3×3 lines, against a table written out by hand."""

import pytest

from app.puzzles.types.sum_grid.levels import LEVELS
from app.puzzles.types.sum_grid.models import MistakeRule as R
from app.puzzles.types.sum_grid.rules import (
    RULES,
    StepView,
    distractor_value,
    is_near_miss,
    rule_output,
    step_view,
)
from tests.sum_grid.support import large, medium, small

NONE = {rule: None for rule in RULES}

# (what it is, level, line target, known cells, the other line's target, what each rule gives).
# A rule that is not named gives None: it does not apply, or it lands on the answer.
TABLE = [
    (
        "2×2: 3 + □ = 9",
        1,
        9,
        (3,),
        11,
        {R.ADD_VISIBLE: 12, R.WRONG_LINE: 8, R.OFF_BY_ONE_OVER: 7, R.OFF_BY_ONE_UNDER: 5},
    ),
    (
        "2×2 where the other target is smaller than the known number",
        1,
        14,
        (9,),
        6,
        {R.ADD_VISIBLE: 23, R.OFF_BY_ONE_OVER: 6, R.OFF_BY_ONE_UNDER: 4},
    ),
    (
        "2×2 where both targets are the same: the wrong line is the right answer",
        1,
        9,
        (3,),
        9,
        {R.ADD_VISIBLE: 12, R.OFF_BY_ONE_OVER: 7, R.OFF_BY_ONE_UNDER: 5},
    ),
    (
        "3×3 small numbers: 2 + □ + 9 = 16",
        2,
        16,
        (2, 9),
        14,
        {
            R.ADD_VISIBLE: 27,
            R.FORGOT_ONE: 7,  # 16 − 9, the 2 is lost
            R.WRONG_LINE: 3,
            R.OFF_BY_ONE_OVER: 6,
            R.OFF_BY_ONE_UNDER: 4,
        },
    ),
    (
        "3×3 small numbers with two equal known cells",
        2,
        15,
        (6, 6),
        20,
        {
            R.ADD_VISIBLE: 27,
            R.FORGOT_ONE: 9,
            R.WRONG_LINE: 8,
            R.OFF_BY_ONE_OVER: 4,
            R.OFF_BY_ONE_UNDER: 2,
        },
    ),
    (
        "level 3: 20 + 37 + □ = 85, where the subtraction needs an exchange",
        3,
        85,
        (20, 37),
        80,
        {
            R.ADD_VISIBLE: 142,
            R.FORGOT_ONE: 48,  # 85 − 37
            R.PLACE_VALUE_SLIP: 32,  # 85 − 57 column by column, smaller from larger
            R.TENS_AS_ONES: 46,  # the 20 read as 2: 85 − 39
            R.WRONG_LINE: 23,
            R.OFF_BY_ONE_OVER: 29,
            R.OFF_BY_ONE_UNDER: 27,
        },
    ),
    (
        "level 3: the subtraction is safe, the slip is in adding 28 and 37",
        3,
        99,
        (28, 37),
        70,
        {
            R.ADD_VISIBLE: 164,
            R.FORGOT_ONE: 62,
            R.CARRY_DROPPED: 44,  # 28 + 37 without the carry is 55; 99 − 55
            R.WRONG_LINE: 5,
            R.OFF_BY_ONE_OVER: 35,
            R.OFF_BY_ONE_UNDER: 33,
        },
    ),
    (
        "level 3: no column needs an exchange or a carry, so there is no slip",
        3,
        77,
        (40, 22),
        66,
        {
            R.ADD_VISIBLE: 139,
            R.FORGOT_ONE: 37,
            R.TENS_AS_ONES: 51,  # the 40 read as 4: 77 − 26
            R.WRONG_LINE: 4,
            R.OFF_BY_ONE_OVER: 16,
            R.OFF_BY_ONE_UNDER: 14,
        },
    ),
    (
        "level 3: two multiples of ten, the first one along the line is misread",
        3,
        90,
        (30, 40),
        95,
        {
            R.ADD_VISIBLE: 160,
            R.FORGOT_ONE: 50,
            R.TENS_AS_ONES: 47,  # the 30 read as 3: 90 − 43
            R.WRONG_LINE: 25,
            R.OFF_BY_ONE_OVER: 21,
            R.OFF_BY_ONE_UNDER: 19,
        },
    ),
]


@pytest.mark.parametrize(("_what", "level", "target", "known", "crossing", "expected"), TABLE)
def test_every_rule_gives_what_the_table_says(_what, level, target, known, crossing, expected):
    view = StepView(target=target, known_cells=known, crossing_target=crossing)

    for rule, value in {**NONE, **expected}.items():
        assert rule_output(rule, view, LEVELS[level]) == value, rule.value


def test_the_table_covers_every_rule_and_both_grid_sizes():
    seen = {(rule, len(known)) for _w, _l, _t, known, _c, expected in TABLE for rule in expected}

    for rule in RULES:
        assert any(r is rule for r, _cells in seen), rule.value
    # One known cell is a 2×2 line; two are a 3×3 line.
    assert {cells for _rule, cells in seen} == {1, 2}
    # The rules that need a 3×3 line, or level 3, were never seen without one.
    assert {cells for rule, cells in seen if rule is R.FORGOT_ONE} == {2}
    levels = {level for _w, level, _t, _k, _c, expected in TABLE if R.TENS_AS_ONES in expected}
    assert levels == {3}


def test_level_three_rules_do_nothing_below_level_three():
    # The same numbers as a level 3 line, read at level 2.
    view = StepView(target=85, known_cells=(20, 37), crossing_target=80)

    assert rule_output(R.PLACE_VALUE_SLIP, view, LEVELS[2]) is None
    carry = StepView(target=99, known_cells=(28, 37), crossing_target=70)
    assert rule_output(R.CARRY_DROPPED, carry, LEVELS[3]) == 44
    assert rule_output(R.CARRY_DROPPED, carry, LEVELS[2]) is None
    # Both slips on one line give two different wrong answers: 91 − 65.
    both = StepView(target=91, known_cells=(28, 37), crossing_target=70)
    assert rule_output(R.PLACE_VALUE_SLIP, both, LEVELS[3]) == 34
    assert rule_output(R.CARRY_DROPPED, both, LEVELS[3]) == 36
    assert rule_output(R.TENS_AS_ONES, view, LEVELS[2]) is None
    assert rule_output(R.FORGOT_ONE, view, LEVELS[2]) == 48
    assert R.NEAR_MISS not in RULES
    assert rule_output(R.NEAR_MISS, view, LEVELS[3]) is None


def test_an_option_is_never_below_zero_or_above_the_levels_cap():
    assert [spec.option_max for spec in LEVELS.values()] == [40, 60, 200]

    low = StepView(target=3, known_cells=(2,), crossing_target=9)  # the answer is 1
    assert rule_output(R.OFF_BY_ONE_UNDER, low, LEVELS[1]) == 0
    assert distractor_value(R.OFF_BY_ONE_UNDER, low, LEVELS[1]) == 0
    zero = StepView(target=2, known_cells=(2,), crossing_target=9)  # 0, which no grid has
    assert rule_output(R.OFF_BY_ONE_UNDER, zero, LEVELS[1]) == -1
    assert distractor_value(R.OFF_BY_ONE_UNDER, zero, LEVELS[1]) is None

    # At level 3 adding everything can pass 200.
    big = StepView(target=100, known_cells=(50, 55), crossing_target=90)
    assert rule_output(R.ADD_VISIBLE, big, LEVELS[3]) == 205
    assert distractor_value(R.ADD_VISIBLE, big, LEVELS[3]) is None
    assert distractor_value(R.ADD_VISIBLE, big.__class__(100, (50, 49), 90), LEVELS[3]) == 199


def test_near_miss_fillers_stay_inside_the_cell_range():
    assert is_near_miss(8, 6, LEVELS[1]) and is_near_miss(2, 6, LEVELS[1])
    assert not is_near_miss(6, 6, LEVELS[1])
    assert not is_near_miss(7, 6, LEVELS[1])  # 1 away is OFF_BY_ONE, not a filler
    assert not is_near_miss(11, 9, LEVELS[1])  # past the cells of the level
    assert is_near_miss(38, 28, LEVELS[3])
    assert not is_near_miss(8, 28, LEVELS[3])  # below the cells of level 3


def test_the_view_of_a_stored_step_uses_the_answers_of_the_steps_before_it():
    puzzle = large()

    # 20 | 37 | □ from the top row; the other line is the right column.
    assert step_view(puzzle, 0) == StepView(85, (20, 37), 80)
    assert step_view(puzzle, 1) == StepView(77, (40, 22), 66)
    # The middle column, top to bottom, without the blank itself.
    assert step_view(puzzle, 2) == StepView(89, (37, 40), 73)
    # The bottom row once its other blank (12) is solved.
    assert step_view(puzzle, 3) == StepView(73, (31, 12), 80)
    assert [step_view(puzzle, i).answer for i in range(4)] == [28, 15, 12, 30]

    assert step_view(small(), 0) == StepView(9, (3,), 11)
    assert step_view(medium(), 0) == StepView(13, (4, 7), 16)
    # The top row after its first blank (2) is solved.
    assert step_view(medium(), 1) == StepView(16, (2, 9), 14)
