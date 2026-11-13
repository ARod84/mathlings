import pytest

from app.puzzles.diagnoser import Diagnosis, diagnose
from app.puzzles.models import MistakeRule, Puzzle
from tests.puzzles.support import (
    TOPIC_WITHIN_1000,
    example_chain,
    make_catalog,
    make_puzzle,
    make_step,
    step_back,
)

EQUALS_SIGN = "mt_oIzycTBeE4"


def run(puzzle: Puzzle, answer: int, step_index: int = 0, lookup=step_back) -> Diagnosis:
    return diagnose(puzzle, step_index, answer, catalog=make_catalog(), step_back=lookup)


def no_step_back(_topic_id: str) -> str | None:
    raise AssertionError("step_back should not be needed here")


def test_correct_answer():
    result = run(example_chain(), 3, lookup=no_step_back)

    assert result == Diagnosis(correct=True)
    assert result.matched_rules == []
    assert result.error_pattern_id is None
    assert result.reteach_topic_id is None
    assert result.unrecognized is False


def test_adding_the_visible_numbers():
    # 8 + □ = 11 answered 19.
    result = run(example_chain(), 19, lookup=no_step_back)

    assert result.correct is False
    assert result.matched_rules == [MistakeRule.ADD_VISIBLE]
    assert result.error_pattern_id == "mt_3JgrHY221M#0"
    # From the error pattern itself: step back to what the equals sign means.
    assert result.reteach_topic_id == EQUALS_SIGN
    assert result.unrecognized is False


def test_reading_the_answer_left_form_backwards():
    # 5 = □ − 3 answered 2.
    result = run(make_puzzle([make_step("c=?-b", 5, 3)]), 2, lookup=no_step_back)

    assert result.matched_rules == [MistakeRule.ANSWER_LEFT_BACKWARDS]
    assert result.error_pattern_id == "mt_3JgrHY221M#1"
    assert result.reteach_topic_id == EQUALS_SIGN


def test_position_confusion_at_level_3():
    # □ − 120 = 250 answered 130.
    puzzle = make_puzzle([make_step("?-b=c", 120, 250, level=3)], level=3)
    result = run(puzzle, 130, lookup=no_step_back)

    assert result.matched_rules == [MistakeRule.POSITION_CONFUSION]
    assert result.error_pattern_id == "mt_XuHmIn2xje#2"
    assert result.reteach_topic_id == TOPIC_WITHIN_1000


def test_a_pattern_without_a_reteach_topic_falls_back_to_the_prerequisite_graph():
    # 245 + □ = 380 answered 625: the level-3 pattern names no topic to reteach.
    puzzle = make_puzzle([make_step("a+?=c", 245, 380, level=3)], level=3)
    asked = []

    def lookup(topic_id):
        asked.append(topic_id)
        return "mt_from_the_graph"

    result = run(puzzle, 625, lookup=lookup)

    assert result.matched_rules == [MistakeRule.ADD_VISIBLE]
    assert result.error_pattern_id == "mt_XuHmIn2xje#0"
    assert result.reteach_topic_id == "mt_from_the_graph"
    assert asked == ["mt_XuHmIn2xje"]  # the puzzle's primary topic


def test_a_pattern_from_another_level_is_named_but_its_reteach_topic_is_not_used():
    # □ − 3 = 5 answered 2 at level 1. The only "position confusion" pattern is
    # written for the level-3 topic, and reteaches three-digit work.
    result = run(example_chain(), 2, step_index=1)

    assert result.matched_rules == [MistakeRule.POSITION_CONFUSION]
    assert result.error_pattern_id == "mt_XuHmIn2xje#2"
    assert result.reteach_topic_id == EQUALS_SIGN  # step back from the level-1 topic
    assert result.reteach_topic_id != TOPIC_WITHIN_1000


def test_a_slip_with_no_taxonomy_pattern():
    over = run(example_chain(), 4)
    under = run(example_chain(), 2)

    assert over.matched_rules == [MistakeRule.OFF_BY_ONE_OVER]
    assert under.matched_rules == [MistakeRule.OFF_BY_ONE_UNDER]
    for result in (over, under):
        assert result.error_pattern_id is None
        assert result.unrecognized is False
        assert result.reteach_topic_id == EQUALS_SIGN


def test_place_value_slip_at_level_3():
    puzzle = make_puzzle([make_step("a+?=c", 245, 380, level=3)], level=3)
    result = run(puzzle, 145)

    assert result.matched_rules == [MistakeRule.PLACE_VALUE_SLIP]
    assert result.error_pattern_id is None
    assert result.reteach_topic_id == TOPIC_WITHIN_1000


def test_an_answer_that_several_rules_explain_returns_them_all_linked_first():
    # □ − 50 = 60 (right answer 110) answered 10:
    #   position confusion: 60 − 50 = 10
    #   column slip:        50 + 60 with the carry dropped = 10
    puzzle = make_puzzle([make_step("?-b=c", 50, 60, level=3)], level=3)
    result = run(puzzle, 10, lookup=no_step_back)

    assert result.matched_rules == [MistakeRule.POSITION_CONFUSION, MistakeRule.PLACE_VALUE_SLIP]
    assert result.error_pattern_id == "mt_XuHmIn2xje#2"
    assert result.reteach_topic_id == TOPIC_WITHIN_1000


def test_each_unlinked_rule_is_told_apart():
    # 101 − □ = 99, right answer 2.
    puzzle = make_puzzle([make_step("a-?=c", 101, 99, level=3)], level=3)

    # Column by column with no exchange: |1−0| |0−9| |1−9| = 198.
    assert run(puzzle, 198).matched_rules == [MistakeRule.PLACE_VALUE_SLIP]
    assert run(puzzle, 3).matched_rules == [MistakeRule.OFF_BY_ONE_OVER]
    assert run(puzzle, 1).matched_rules == [MistakeRule.OFF_BY_ONE_UNDER]


@pytest.mark.parametrize("answer", [7, 0, 11, 8, 100, -4])
def test_unrecognized_answers_are_not_forced_into_a_rule(answer):
    # 8 + □ = 11: none of these comes from a known mistake.
    result = run(example_chain(), answer, lookup=no_step_back)

    assert result == Diagnosis(correct=False, unrecognized=True)
    assert result.matched_rules == []
    assert result.error_pattern_id is None
    assert result.reteach_topic_id is None


def test_a_filler_distractor_is_not_a_diagnosis():
    puzzle = example_chain()
    # 14 − □ = 8 has no "add the visible numbers" option, so it carries a filler.
    fillers = [d for d in puzzle.steps[2].distractors if d.rule is MistakeRule.NEAR_MISS]
    assert fillers

    result = run(puzzle, fillers[0].value, step_index=2)
    assert result.unrecognized is True
    assert result.matched_rules == []


def test_an_answer_above_the_level_range_is_offered_and_diagnosed():
    # 15 + □ = 18 answered 33: past level 1's 20, but it is what a child who
    # adds the visible numbers writes, so it is an option and it is diagnosed.
    puzzle = make_puzzle([make_step("a+?=c", 15, 18)])
    assert 33 in [d.value for d in puzzle.steps[0].distractors]

    result = run(puzzle, 33)
    assert result.matched_rules == [MistakeRule.ADD_VISIBLE]
    assert result.error_pattern_id == "mt_3JgrHY221M#0"


def test_an_answer_past_the_distractor_cap_is_still_diagnosed():
    # A value too large to offer as an option can still be typed, so the
    # diagnoser has no upper limit. (25 and 30 are not level-1 numbers; the
    # step is only here to push the sum past the cap of 40.)
    puzzle = make_puzzle([make_step("a+?=c", 25, 30)])
    assert 55 not in [d.value for d in puzzle.steps[0].distractors]

    result = run(puzzle, 55)
    assert result.matched_rules == [MistakeRule.ADD_VISIBLE]


def test_every_real_rule_distractor_is_diagnosed_as_its_rule():
    puzzle = example_chain()
    for index, step in enumerate(puzzle.steps):
        for distractor in step.distractors:
            if distractor.rule is MistakeRule.NEAR_MISS:
                continue
            result = run(puzzle, distractor.value, step_index=index)
            assert distractor.rule in result.matched_rules
            if distractor.error_pattern_id:
                assert result.error_pattern_id == distractor.error_pattern_id


def test_no_step_back_candidate_leaves_reteach_empty():
    result = run(example_chain(), 4, lookup=lambda _topic_id: None)

    assert result.matched_rules == [MistakeRule.OFF_BY_ONE_OVER]
    assert result.reteach_topic_id is None
    assert result.unrecognized is False
