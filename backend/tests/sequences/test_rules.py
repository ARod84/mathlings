"""Each mistake rule on each kind of sequence, against a table written out by hand."""

import pytest

from app.puzzles.types.sequences.levels import LEVELS, OPTION_CEILING, OPTION_FLOOR
from app.puzzles.types.sequences.models import MistakeRule as R
from app.puzzles.types.sequences.rules import (
    RULES,
    distractor_value,
    is_near_miss,
    rule_output,
)

NONE = {rule: None for rule in RULES}

# (what it is, kind, the whole sequence, which term is blank, what each rule gives).
# A rule that is not named gives None: it does not apply, or it lands on the answer.
TABLE = [
    (
        "constant up: 4, 8, 12, □, 20",
        "constant",
        [4, 8, 12, 16, 20],
        3,
        {R.COUNT_BY_ONE: 13, R.SKIPPED_TERM: 20, R.OFF_BY_ONE_OVER: 17, R.OFF_BY_ONE_UNDER: 15},
    ),
    (
        "constant up by 1: counting by one is the right answer",
        "constant",
        [5, 6, 7, 8, 9],
        4,
        {R.SKIPPED_TERM: 10, R.OFF_BY_ONE_OVER: 10, R.OFF_BY_ONE_UNDER: 8},
    ),
    (
        "constant up over a hundreds boundary: 350, 400, 450, □",
        "constant",
        [350, 400, 450, 500, 550],
        3,
        {
            R.BOUNDARY_SLIP: 400,  # 450 + 50 with the carry dropped
            R.COUNT_BY_ONE: 451,
            R.SKIPPED_TERM: 550,
            R.OFF_BY_ONE_OVER: 501,
            R.OFF_BY_ONE_UNDER: 499,
        },
    ),
    (
        "constant up in 25s over a boundary: 475 + 25",
        "constant",
        [425, 450, 475, 500, 525],
        3,
        {
            R.BOUNDARY_SLIP: 490,
            R.COUNT_BY_ONE: 476,
            R.SKIPPED_TERM: 525,
            R.OFF_BY_ONE_OVER: 501,
            R.OFF_BY_ONE_UNDER: 499,
        },
    ),
    (
        "constant up inside one hundred: no boundary, no slip",
        "constant",
        [410, 420, 430, 440, 450],
        4,
        {
            R.COUNT_BY_ONE: 441,
            R.SKIPPED_TERM: 460,
            R.OFF_BY_ONE_OVER: 451,
            R.OFF_BY_ONE_UNDER: 449,
        },
    ),
    (
        "constant up from below 100 into it: not the slip the taxonomy describes",
        "constant",
        [70, 80, 90, 100, 110],
        3,
        {
            R.COUNT_BY_ONE: 91,
            R.SKIPPED_TERM: 110,
            R.OFF_BY_ONE_OVER: 101,
            R.OFF_BY_ONE_UNDER: 99,
        },
    ),
    (
        "constant up into 1000: a thousands boundary, not a hundreds one",
        "constant",
        [600, 700, 800, 900, 1000],
        4,
        {
            R.COUNT_BY_ONE: 901,
            R.SKIPPED_TERM: 1100,
            R.OFF_BY_ONE_OVER: 1001,
            R.OFF_BY_ONE_UNDER: 999,
        },
    ),
    (
        "constant down: 20, 17, 14, 11, □",
        "constant",
        [20, 17, 14, 11, 8],
        4,
        {
            R.WRONG_DIRECTION: 14,  # 11 + 3
            R.COUNT_BY_ONE: 10,
            R.SKIPPED_TERM: 5,
            R.OFF_BY_ONE_OVER: 9,
            R.OFF_BY_ONE_UNDER: 7,
        },
    ),
    (
        "constant down over a hundreds boundary: 500 − 50",
        "constant",
        [600, 550, 500, 450, 400],
        3,
        {
            R.WRONG_DIRECTION: 550,
            R.BOUNDARY_SLIP: 550,  # 500 − 50 column by column, smaller from larger
            R.COUNT_BY_ONE: 499,
            R.SKIPPED_TERM: 400,
            R.OFF_BY_ONE_OVER: 451,
            R.OFF_BY_ONE_UNDER: 449,
        },
    ),
    (
        "constant down over a boundary where the slip goes nowhere: 501 − 2",
        "constant",
        [505, 503, 501, 499, 497],
        3,
        {
            R.WRONG_DIRECTION: 503,
            R.COUNT_BY_ONE: 500,
            R.SKIPPED_TERM: 497,
            R.OFF_BY_ONE_OVER: 500,
            R.OFF_BY_ONE_UNDER: 498,
        },
    ),
    (
        "through zero, the blank below zero: 9, 6, 3, 0, □",
        "constant",
        [9, 6, 3, 0, -3],
        4,
        {
            R.STOPS_AT_ZERO: 0,
            R.SIGN_DROPPED: 3,
            R.WRONG_DIRECTION: 3,  # 0 + 3
            R.COUNT_BY_ONE: -1,
            R.SKIPPED_TERM: -6,
            R.OFF_BY_ONE_OVER: -2,
            R.OFF_BY_ONE_UNDER: -4,
        },
    ),
    (
        "through zero, further down: 10, 6, 2, −2, □",
        "constant",
        [10, 6, 2, -2, -6],
        4,
        {
            R.STOPS_AT_ZERO: 0,
            R.SIGN_DROPPED: 6,
            R.WRONG_DIRECTION: 2,  # −2 + 4
            R.COUNT_BY_ONE: -3,
            R.SKIPPED_TERM: -10,
            R.OFF_BY_ONE_OVER: -5,
            R.OFF_BY_ONE_UNDER: -7,
        },
    ),
    (
        "through zero, the blank at zero itself: nothing has stopped, there is no sign",
        "constant",
        [9, 6, 3, 0, -3],
        3,
        {
            R.WRONG_DIRECTION: 6,
            R.COUNT_BY_ONE: 2,
            R.SKIPPED_TERM: -3,
            R.OFF_BY_ONE_OVER: 1,
            R.OFF_BY_ONE_UNDER: -1,
        },
    ),
    (
        "growing: 1, 2, 4, 7, □",
        "growing",
        [1, 2, 4, 7, 11],
        4,
        {
            R.CONSTANT_GAP: 10,  # +3 again
            R.COUNT_BY_ONE: 8,
            R.SKIPPED_TERM: 16,  # 11 + 5
            R.OFF_BY_ONE_OVER: 12,
            R.OFF_BY_ONE_UNDER: 10,
        },
    ),
    (
        "growing by 2: 10, 13, 18, 25, □, 45",
        "growing",
        [10, 13, 18, 25, 34, 45],
        4,
        {
            R.CONSTANT_GAP: 32,  # +7 again
            R.COUNT_BY_ONE: 26,
            R.SKIPPED_TERM: 45,
            R.OFF_BY_ONE_OVER: 35,
            R.OFF_BY_ONE_UNDER: 33,
        },
    ),
    (
        "growing, the second term blank: there is no step before to repeat",
        "growing",
        [3, 5, 8, 12, 17, 23],
        1,
        {
            R.COUNT_BY_ONE: 4,
            R.SKIPPED_TERM: 8,
            R.OFF_BY_ONE_OVER: 6,
            R.OFF_BY_ONE_UNDER: 4,
        },
    ),
]


@pytest.mark.parametrize(("_what", "kind", "terms", "position", "expected"), TABLE)
def test_every_rule_gives_what_the_table_says(_what, kind, terms, position, expected):
    for rule, value in {**NONE, **expected}.items():
        assert rule_output(rule, terms, position, kind) == value, rule.value


def test_the_table_covers_every_rule_on_every_kind_it_applies_to():
    seen = {
        (rule, kind, terms[1] > terms[0])
        for _what, kind, terms, _position, expected in TABLE
        for rule in expected
    }

    for rule in RULES:
        assert any(r is rule for r, _kind, _up in seen), rule.value
    # The rules that only make sense on one kind were never seen on another.
    assert {kind for rule, kind, _up in seen if rule is R.CONSTANT_GAP} == {"growing"}
    for rule in (R.STOPS_AT_ZERO, R.SIGN_DROPPED, R.WRONG_DIRECTION, R.BOUNDARY_SLIP):
        assert {kind for r, kind, _up in seen if r is rule} == {"constant"}
    assert not any(up for rule, _kind, up in seen if rule is R.WRONG_DIRECTION)


def test_near_miss_is_not_a_rule_and_the_first_term_is_never_a_blank():
    assert R.NEAR_MISS not in RULES
    assert rule_output(R.NEAR_MISS, [4, 8, 12, 16, 20], 3, "constant") is None
    for rule in RULES:
        assert rule_output(rule, [4, 8, 12, 16, 20], 0, "constant") is None


def test_an_option_stays_inside_the_level_range_and_the_overall_cap():
    for spec in LEVELS.values():
        assert OPTION_FLOOR <= spec.option_min <= spec.min_value
        assert spec.max_value <= spec.option_max <= OPTION_CEILING

    # Level 2 ends at 0: the term after the right one would be below zero, and is not offered.
    down = [8, 6, 4, 2, 0]
    assert rule_output(R.SKIPPED_TERM, down, 4, "constant") == -2
    assert distractor_value(R.SKIPPED_TERM, down, 4, "constant", LEVELS[2]) is None
    assert distractor_value(R.OFF_BY_ONE_UNDER, down, 4, "constant", LEVELS[2]) is None
    assert distractor_value(R.WRONG_DIRECTION, down, 4, "constant", LEVELS[2]) == 4
    # Level 1 may go a little past 100, and level 3 below zero.
    assert distractor_value(R.SKIPPED_TERM, [60, 70, 80, 90, 100], 4, "constant", LEVELS[1]) == 110
    assert distractor_value(R.SKIPPED_TERM, [9, 6, 3, 0, -3], 4, "constant", LEVELS[3]) == -6


def test_near_miss_fillers_stay_inside_the_term_range():
    spec = LEVELS[1]

    assert is_near_miss(18, 16, spec) and is_near_miss(11, 16, spec)
    assert not is_near_miss(16, 16, spec)
    assert not is_near_miss(17, 16, spec)  # 1 away is OFF_BY_ONE, not a filler
    assert not is_near_miss(102, 100, spec)  # past the level's terms
    assert is_near_miss(-5, -3, LEVELS[3])
