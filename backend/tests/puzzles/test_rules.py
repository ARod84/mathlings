import pytest

from app.puzzles.types.missing_number.levels import LEVELS
from app.puzzles.types.missing_number.models import MistakeRule
from app.puzzles.types.missing_number.rules import (
    RULES,
    add_without_carry,
    distractor_value,
    is_near_miss,
    rule_output,
    subtract_without_exchange,
)
from tests.puzzles.support import make_step

ADD = MistakeRule.ADD_VISIBLE
BACKWARDS = MistakeRule.ANSWER_LEFT_BACKWARDS
POSITION = MistakeRule.POSITION_CONFUSION
SLIP = MistakeRule.PLACE_VALUE_SLIP
OVER = MistakeRule.OFF_BY_ONE_OVER
UNDER = MistakeRule.OFF_BY_ONE_UNDER

# One row per form: the equation, its right answer, and what each rule gives.
# Written out by hand. None means the rule does not apply.
#
#   level 1                              answer  ADD   BACKWARDS  POSITION  OVER  UNDER
LEVEL_1_TABLE = [
    ("a+?=c", 8, 11, "8 + □ = 11", 3, 19, None, None, 4, 2),
    ("?+b=c", 5, 12, "□ + 5 = 12", 7, 17, None, None, 8, 6),
    ("a-?=c", 14, 6, "14 − □ = 6", 8, None, None, None, 9, 7),
    ("?-b=c", 3, 5, "□ − 3 = 5", 8, None, None, 2, 9, 7),
    ("c=a+?", 11, 8, "11 = 8 + □", 3, 19, None, None, 4, 2),
    ("c=?-b", 5, 3, "5 = □ − 3", 8, None, 2, None, 9, 7),
]

#   level 3                                    answer  ADD   BACKWARDS  POSITION  SLIP
LEVEL_3_TABLE = [
    ("a+?=c", 245, 380, "245 + □ = 380", 135, 625, None, None, 145),
    ("?+b=c", 148, 423, "□ + 148 = 423", 275, 571, None, None, 325),
    ("a-?=c", 502, 276, "502 − □ = 276", 226, None, None, None, 374),
    ("?-b=c", 148, 275, "□ − 148 = 275", 423, None, None, 127, 313),
    ("c=a+?", 380, 245, "380 = 245 + □", 135, 625, None, None, 145),
    ("c=?-b", 275, 148, "275 = □ − 148", 423, None, 127, None, 313),
]


@pytest.mark.parametrize("row", LEVEL_1_TABLE, ids=[row[3] for row in LEVEL_1_TABLE])
def test_every_rule_on_every_form_at_level_1(row):
    form, first, second, _text, answer, add, backwards, position, over, under = row
    spec = LEVELS[1]
    step = make_step(form, first, second, level=1)

    assert step.answer == answer
    assert rule_output(ADD, step, spec) == add
    assert rule_output(BACKWARDS, step, spec) == backwards
    assert rule_output(POSITION, step, spec) == position
    assert rule_output(OVER, step, spec) == over
    assert rule_output(UNDER, step, spec) == under
    # The column slip is a level-3 rule.
    assert rule_output(SLIP, step, spec) is None


@pytest.mark.parametrize("row", LEVEL_3_TABLE, ids=[row[3] for row in LEVEL_3_TABLE])
def test_every_rule_on_every_form_at_level_3(row):
    form, first, second, _text, answer, add, backwards, position, slip = row
    spec = LEVELS[3]
    step = make_step(form, first, second, level=3)

    assert step.answer == answer
    assert rule_output(ADD, step, spec) == add
    assert rule_output(BACKWARDS, step, spec) == backwards
    assert rule_output(POSITION, step, spec) == position
    assert rule_output(SLIP, step, spec) == slip
    assert rule_output(OVER, step, spec) == answer + 1
    assert rule_output(UNDER, step, spec) == answer - 1


def test_the_examples_from_the_spec():
    assert rule_output(ADD, make_step("a+?=c", 8, 11), LEVELS[1]) == 19
    assert rule_output(BACKWARDS, make_step("c=?-b", 5, 3), LEVELS[1]) == 2
    assert rule_output(POSITION, make_step("?-b=c", 120, 250, level=3), LEVELS[3]) == 130
    assert rule_output(SLIP, make_step("a+?=c", 245, 380, level=3), LEVELS[3]) == 145


def test_subtraction_slips_give_nothing_when_they_would_go_below_zero():
    # 5 = □ − 9 and □ − 9 = 5: "5 − 9" has no answer for these children.
    assert rule_output(BACKWARDS, make_step("c=?-b", 5, 9), LEVELS[1]) is None
    assert rule_output(POSITION, make_step("?-b=c", 9, 5), LEVELS[1]) is None


def test_place_value_slip_gives_nothing_when_no_column_needs_work():
    # 120 + 250 has no carry, 380 − 240 has no exchange: the slip lands on the right answer.
    assert rule_output(SLIP, make_step("?-b=c", 120, 250, level=3), LEVELS[3]) is None
    assert rule_output(SLIP, make_step("a+?=c", 240, 380, level=3), LEVELS[3]) is None


def test_place_value_slip_is_off_below_level_3():
    step = make_step("a+?=c", 45, 82, level=2)  # 82 − 45 needs an exchange
    assert rule_output(SLIP, step, LEVELS[2]) is None
    assert rule_output(SLIP, step, LEVELS[3]) == 43


def test_a_rule_never_returns_the_right_answer_or_a_negative():
    # Answer 1: one under is 0, which is still a wrong answer a child can give.
    step = make_step("a+?=c", 7, 8)
    assert rule_output(UNDER, step, LEVELS[1]) == 0
    for form, first, second, *_ in LEVEL_1_TABLE + LEVEL_3_TABLE:
        level = 3 if first > 20 or second > 20 else 1
        step = make_step(form, first, second, level=level)
        for rule in RULES:
            value = rule_output(rule, step, LEVELS[level])
            assert value is None or (value >= 0 and value != step.answer)


def test_a_mistake_past_the_level_range_is_offered_up_to_the_cap():
    # 8 + □ = 15: a child who adds the visible numbers writes 23. That is past
    # level 1's 20, and it is exactly the option worth showing.
    step = make_step("a+?=c", 8, 15)
    assert rule_output(ADD, step, LEVELS[1]) == 23
    assert distractor_value(ADD, step, LEVELS[1]) == 23
    assert 23 in [d.value for d in step.distractors]
    assert step.distractors[0].rule is ADD
    assert step.distractors[0].error_pattern_id == "mt_3JgrHY221M#0"

    # The largest sum two level-1 numbers can make is still under the cap of 40.
    assert distractor_value(ADD, make_step("a+?=c", 19, 20), LEVELS[1]) == 39


def test_a_mistake_past_the_cap_is_diagnosable_but_not_offered():
    # 25 + □ = 30 is not a level-1 step; it is here to push the sum past 40.
    step = make_step("a+?=c", 25, 30)
    assert rule_output(ADD, step, LEVELS[1]) == 55
    assert distractor_value(ADD, step, LEVELS[1]) is None
    assert 55 not in [d.value for d in step.distractors]


@pytest.mark.parametrize(
    ("level", "max_value", "distractor_max"), [(1, 20, 40), (2, 100, 200), (3, 1000, 2000)]
)
def test_each_level_has_a_cap_above_its_range(level, max_value, distractor_max):
    spec = LEVELS[level]
    assert (spec.max_value, spec.distractor_max) == (max_value, distractor_max)

    # Exactly at the cap is offered; one more is not.
    at_cap = make_step("a+?=c", distractor_max // 2, distractor_max // 2, level=level)
    over = make_step("a+?=c", distractor_max // 2, distractor_max // 2 + 1, level=level)
    assert distractor_value(ADD, at_cap, spec) == distractor_max
    assert distractor_value(ADD, over, spec) is None
    assert rule_output(ADD, over, spec) == distractor_max + 1


def test_fillers_and_negatives_do_not_get_the_higher_cap():
    step = make_step("a+?=c", 1, 20)  # answer 19
    # 21 and 22 are near the answer but past level 1's range: not valid fillers.
    assert not is_near_miss(21, step, LEVELS[1])
    assert not is_near_miss(22, step, LEVELS[1])
    assert is_near_miss(17, step, LEVELS[1])
    # One over the answer is the off-by-one rule, and it may be 21 > 20.
    assert distractor_value(OVER, make_step("a+?=c", 0, 20), LEVELS[1]) == 21
    assert distractor_value(POSITION, make_step("?-b=c", 9, 5), LEVELS[1]) is None


def test_near_miss_is_a_filler_not_a_rule():
    step = make_step("a+?=c", 8, 11)  # answer 3
    assert MistakeRule.NEAR_MISS not in RULES
    assert rule_output(MistakeRule.NEAR_MISS, step, LEVELS[1]) is None
    assert is_near_miss(5, step, LEVELS[1])  # 2 away
    assert is_near_miss(0, step, LEVELS[1])  # 3 away
    assert not is_near_miss(4, step, LEVELS[1])  # 1 away is the off-by-one rule
    assert not is_near_miss(3, step, LEVELS[1])  # the answer
    assert not is_near_miss(-2, step, LEVELS[1])
    assert not is_near_miss(9, step, LEVELS[1])  # 6 away: not a listed offset


@pytest.mark.parametrize(
    ("minuend", "subtrahend", "expected"),
    [(380, 245, 145), (502, 276, 374), (82, 45, 43), (423, 148, 325), (713, 37, 724), (9, 4, 5)],
)
def test_subtract_without_exchange(minuend, subtrahend, expected):
    assert subtract_without_exchange(minuend, subtrahend) == expected


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [(275, 148, 313), (148, 275, 313), (120, 250, 370), (50, 60, 10), (999, 1, 990), (8, 5, 3)],
)
def test_add_without_carry(first, second, expected):
    assert add_without_carry(first, second) == expected
