from pathlib import Path

import pytest

from app.puzzles.types.missing_number.equations import build_equation
from app.puzzles.types.missing_number.ids import make_puzzle_id
from app.puzzles.types.missing_number.models import (
    Distractor,
    Equation,
    MistakeRule,
    NumberToken,
    OperatorToken,
    Puzzle,
    UnknownToken,
)
from app.puzzles.types.missing_number.verifier import FailureName, VerificationResult, verify
from tests.puzzles.support import (
    example_chain,
    make_catalog,
    make_puzzle,
    make_step,
    replace_step,
    topic_exists,
)

F = FailureName


def check(puzzle: Puzzle) -> VerificationResult:
    return verify(puzzle, catalog=make_catalog(), topic_exists=topic_exists)


def test_the_hand_built_example_passes():
    result = check(example_chain())
    assert result.ok, result.failures
    assert result.failures == []


def test_hand_built_puzzles_pass_at_every_level():
    level_2 = make_puzzle(
        [make_step("c=a+?", 73, 28, level=2), make_step("?+b=c", 45, 97, level=2, link_position=0)],
        level=2,
    )
    level_3 = make_puzzle(
        [
            make_step("a+?=c", 245, 380, level=3),
            make_step("c=?-b", 135, 148, level=3, link_position=0),
            make_step("c=a+?", 283, 120, level=3, link_position=0),
        ],
        level=3,
    )
    assert check(level_2).ok, check(level_2).failures
    assert check(level_3).ok, check(level_3).failures


# ---- one test per failure name ----


def test_wrong_stored_answer():
    broken = replace_step(example_chain(), 0, answer=4)  # 8 + □ = 11 is 3

    result = check(broken)
    assert F.WRONG_ANSWER in result.names
    failure = next(f for f in result.failures if f.name is F.WRONG_ANSWER)
    assert failure.step == 0
    assert "solved 3" in failure.detail


def test_value_out_of_range():
    # 8 + □ = 25 at level 1: 25 is past 20, and so is nothing wrong with the sum itself.
    step = make_step("a+?=c", 8, 11).model_copy(update={"equation": build_equation("a+?=c", 8, 25)})
    result = check(make_puzzle([step]))

    assert F.VALUE_OUT_OF_RANGE in result.names


def test_negative_value():
    step = make_step("a+?=c", 8, 11).model_copy(update={"equation": build_equation("a+?=c", -3, 0)})
    result = check(make_puzzle([step]))

    assert F.NEGATIVE_VALUE in result.names


def test_no_unique_solution_when_the_answer_lies_outside_the_range():
    # □ − 15 = 9 needs 24, which level 1 does not have.
    result = check(make_puzzle([make_step("?-b=c", 15, 9)]))

    assert F.NO_UNIQUE_SOLUTION in result.names
    assert F.VALUE_OUT_OF_RANGE in result.names


def test_duplicate_distractor():
    puzzle = example_chain()
    first, second, _third = puzzle.steps[0].distractors
    broken = replace_step(puzzle, 0, distractors=[first, second, second])

    assert F.DUPLICATE_DISTRACTOR in check(broken).names


def test_distractor_equal_to_the_answer():
    puzzle = example_chain()
    kept = puzzle.steps[0].distractors[:2]
    same_as_answer = Distractor(value=3, rule=MistakeRule.NEAR_MISS)
    broken = replace_step(puzzle, 0, distractors=[*kept, same_as_answer])

    assert F.DISTRACTOR_EQUALS_ANSWER in check(broken).names


def test_distractor_that_does_not_match_its_rule():
    puzzle = example_chain()
    kept = puzzle.steps[0].distractors[:2]
    # ADD_VISIBLE on 8 + □ = 11 is 19, not 12.
    mislabeled = Distractor(
        value=12, rule=MistakeRule.ADD_VISIBLE, error_pattern_id="mt_3JgrHY221M#0"
    )
    broken = replace_step(puzzle, 0, distractors=[kept[1], mislabeled, kept[0]])

    result = check(broken)
    assert result.names == {F.DISTRACTOR_RULE_MISMATCH}
    assert "the rule gives 19" in result.failures[0].detail


def test_near_miss_distractor_too_far_from_the_answer():
    puzzle = example_chain()
    kept = puzzle.steps[0].distractors[:2]
    broken = replace_step(
        puzzle, 0, distractors=[*kept, Distractor(value=12, rule=MistakeRule.NEAR_MISS)]
    )

    assert check(broken).names == {F.DISTRACTOR_RULE_MISMATCH}


def test_distractor_out_of_range():
    puzzle = example_chain()
    kept = puzzle.steps[0].distractors[:2]
    broken = replace_step(
        puzzle, 0, distractors=[*kept, Distractor(value=45, rule=MistakeRule.NEAR_MISS)]
    )

    assert F.DISTRACTOR_OUT_OF_RANGE in check(broken).names


def test_a_mistake_value_past_the_level_range_is_accepted_up_to_the_cap():
    # 8 + □ = 15 at level 1, with 23 (8 + 15) as an option: above 20, within 40.
    puzzle = make_puzzle([make_step("a+?=c", 8, 15)])
    assert 23 in [d.value for d in puzzle.steps[0].distractors]
    assert check(puzzle).ok, check(puzzle).failures

    # 19 + □ = 20 gives 39, the largest a level-1 sum can be.
    assert check(make_puzzle([make_step("a+?=c", 19, 20)])).ok


def test_a_mistake_value_past_the_cap_is_rejected():
    puzzle = make_puzzle([make_step("a+?=c", 8, 15)])
    kept = puzzle.steps[0].distractors[:2]
    over_cap = Distractor(
        value=41, rule=MistakeRule.ADD_VISIBLE, error_pattern_id="mt_3JgrHY221M#0"
    )
    result = check(replace_step(puzzle, 0, distractors=[over_cap, kept[1], kept[0]]))

    assert F.DISTRACTOR_OUT_OF_RANGE in result.names
    detail = next(f.detail for f in result.failures if f.name is F.DISTRACTOR_OUT_OF_RANGE)
    assert "0..40" in detail


def test_a_filler_past_the_level_range_is_rejected_even_under_the_cap():
    # 1 + □ = 20 is 19. A filler at 21 is "near", and under 40, but fillers stay in range.
    puzzle = make_puzzle([make_step("a+?=c", 1, 20)])
    kept = puzzle.steps[0].distractors[:2]
    filler = Distractor(value=21, rule=MistakeRule.NEAR_MISS)
    result = check(replace_step(puzzle, 0, distractors=[*kept, filler]))

    assert F.DISTRACTOR_OUT_OF_RANGE in result.names
    detail = next(f.detail for f in result.failures if f.name is F.DISTRACTOR_OUT_OF_RANGE)
    assert "0..20" in detail


def test_the_answer_and_visible_numbers_do_not_get_the_higher_cap():
    # 8 + □ = 30 would need 22: the cap is for mistakes, not for the puzzle itself.
    result = check(make_puzzle([make_step("a+?=c", 8, 30)]))

    assert F.VALUE_OUT_OF_RANGE in result.names
    assert F.NO_UNIQUE_SOLUTION in result.names


def test_wrong_number_of_distractors():
    puzzle = example_chain()
    broken = replace_step(puzzle, 0, distractors=puzzle.steps[0].distractors[:2])

    assert check(broken).names == {F.DISTRACTOR_COUNT}


def test_distractor_tagged_with_the_wrong_error_pattern():
    puzzle = example_chain()
    retagged = [
        d.model_copy(update={"error_pattern_id": "mt_3JgrHY221M#1"})
        if d.rule is MistakeRule.ADD_VISIBLE
        else d
        for d in puzzle.steps[0].distractors
    ]
    untagged = [d.model_copy(update={"error_pattern_id": None}) for d in retagged]

    assert check(replace_step(puzzle, 0, distractors=retagged)).names == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }
    assert check(replace_step(puzzle, 0, distractors=untagged)).names == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }


def test_broken_chain_link():
    # Step 2 is □ − 3 = 5 with the linked 3 at position 0; claim it is at position 1.
    wrong_position = replace_step(example_chain(), 1, link_position=1)
    assert check(wrong_position).names == {F.BROKEN_CHAIN_LINK}

    missing = replace_step(example_chain(), 1, link_position=None)
    assert check(missing).names == {F.BROKEN_CHAIN_LINK}

    # A second step that does not show the first answer at all.
    unrelated = make_puzzle([make_step("a+?=c", 8, 11), make_step("a-?=c", 14, 6, link_position=0)])
    assert check(unrelated).names == {F.BROKEN_CHAIN_LINK}


def test_first_step_must_not_claim_a_link():
    assert check(replace_step(example_chain(), 0, link_position=0)).names == {F.BROKEN_CHAIN_LINK}


def test_repeated_form():
    puzzle = make_puzzle([make_step("a+?=c", 8, 11), make_step("a+?=c", 3, 10, link_position=0)])

    assert check(puzzle).names == {F.REPEATED_FORM}


def test_too_many_answer_left_steps_at_levels_1_and_2():
    steps = [
        make_step("c=a+?", 11, 8),
        make_step("?+b=c", 3, 10, link_position=0),
        make_step("c=?-b", 7, 4, link_position=0),
    ]
    assert check(make_puzzle(steps)).names == {F.TOO_MANY_ANSWER_LEFT}

    # Level 3 has no such limit.
    level_3 = make_puzzle(
        [
            make_step("c=a+?", 380, 245, level=3),
            make_step("?+b=c", 135, 400, level=3, link_position=0),
            make_step("c=?-b", 265, 148, level=3, link_position=0),
        ],
        level=3,
    )
    assert check(level_3).ok, check(level_3).failures


def test_trivial_step():
    # 8 + □ = 8: the box is 0.
    zero_answer = check(make_puzzle([make_step("a+?=c", 8, 8)]))
    assert F.TRIVIAL_STEP in zero_answer.names

    # □ − 0 = 7: nothing to work out.
    zero_visible = check(make_puzzle([make_step("?-b=c", 0, 7)]))
    assert F.TRIVIAL_STEP in zero_visible.names


def test_unknown_topic_id():
    made_up = example_chain().model_copy(update={"topic_ids": ["mt_3JgrHY221M", "mt_nope"]})
    assert F.UNKNOWN_TOPIC in check(made_up).names

    # The right ids, in a database that does not have one of them.
    result = verify(
        example_chain(),
        catalog=make_catalog(),
        topic_exists=lambda topic_id: topic_id != "mt_3JgrHY221M",
    )
    assert result.names == {F.UNKNOWN_TOPIC}
    assert "mt_3JgrHY221M" in result.failures[0].detail


def test_wrong_topics_for_the_level_and_forms():
    puzzle = make_puzzle([make_step("c=a+?", 11, 8)])
    # An answer-left step must carry the equals-sign topic.
    assert puzzle.topic_ids == ["mt_3JgrHY221M", "mt_oIzycTBeE4"]
    dropped = puzzle.model_copy(update={"topic_ids": ["mt_3JgrHY221M"]})
    reordered = puzzle.model_copy(update={"topic_ids": ["mt_oIzycTBeE4", "mt_3JgrHY221M"]})

    assert check(dropped).names == {F.WRONG_TOPICS}
    assert check(reordered).names == {F.WRONG_TOPICS}


def test_level_3_step_without_a_three_digit_number():
    result = check(make_puzzle([make_step("a+?=c", 12, 60, level=3)], level=3))

    assert result.names == {F.MISSING_THREE_DIGIT_NUMBER}


def test_form_label_that_does_not_match_the_tokens():
    broken = replace_step(example_chain(), 0, form="?+b=c")  # tokens are still 8 + □ = 11

    assert F.FORM_MISMATCH in check(broken).names


def test_malformed_equation():
    two_boxes = Equation(
        left=[UnknownToken(), OperatorToken(symbol="+"), UnknownToken()],
        right=[NumberToken(value=11)],
    )
    dangling_operator = Equation(
        left=[NumberToken(value=8), OperatorToken(symbol="+")], right=[NumberToken(value=11)]
    )
    for equation in (two_boxes, dangling_operator):
        result = check(replace_step(example_chain(), 0, equation=equation))
        assert F.MALFORMED_EQUATION in result.names
        assert F.NO_UNIQUE_SOLUTION in result.names


def test_hint_that_gives_the_answer_away_early():
    puzzle = example_chain()
    hints = list(puzzle.steps[0].hints)
    hints[1] = "Try 11 − 8. It is 3."
    result = check(replace_step(puzzle, 0, hints=hints))

    assert result.names == {F.HINT_REVEALS_ANSWER}
    assert "tier 2" in result.failures[0].detail


def test_hint_numbers_are_compared_whole():
    # The answer is 3; "13" and "30" in a hint do not give it away.
    puzzle = example_chain()
    hints = list(puzzle.steps[0].hints)
    hints[0] = "Think of 13 and 30."
    assert check(replace_step(puzzle, 0, hints=hints)).ok


def test_hint_count_and_last_hint_must_show_the_answer():
    puzzle = example_chain()
    hints = list(puzzle.steps[0].hints)

    assert check(replace_step(puzzle, 0, hints=hints[:2])).names == {F.HINT_COUNT}
    vague = [*hints[:2], "Now work it out."]
    assert check(replace_step(puzzle, 0, hints=vague)).names == {F.HINT_MISSING_ANSWER}


def test_puzzle_id_must_describe_the_puzzle():
    puzzle = example_chain()
    other_seed = puzzle.model_copy(update={"seed": puzzle.seed + 1})
    garbage = puzzle.model_copy(update={"puzzle_id": "not-an-id"})

    assert check(other_seed).names == {F.PUZZLE_ID_MISMATCH}
    assert check(garbage).names == {F.PUZZLE_ID_MISMATCH}


def test_bad_length():
    step = make_step("a+?=c", 8, 11)
    result = check(make_puzzle([]))
    assert F.BAD_LENGTH in result.names

    forms = ["a+?=c", "?+b=c", "a+?=c", "?+b=c", "a+?=c"]
    five = make_puzzle([step.model_copy(update={"form": form}) for form in forms])
    assert F.BAD_LENGTH in check(five).names


def test_unsupported_level_or_version():
    puzzle = example_chain()

    assert check(puzzle.model_copy(update={"level": 9})).names == {F.UNSUPPORTED_PUZZLE}
    assert check(puzzle.model_copy(update={"generator_version": "0"})).names == {
        F.UNSUPPORTED_PUZZLE
    }


def test_several_problems_are_all_reported():
    puzzle = example_chain()
    broken = replace_step(puzzle, 0, answer=4, distractors=puzzle.steps[0].distractors[:1])
    broken = replace_step(broken, 2, link_position=0)

    names = check(broken).names
    assert {F.WRONG_ANSWER, F.DISTRACTOR_COUNT, F.BROKEN_CHAIN_LINK} <= names


# ---- independence ----


def test_brute_force_solving_handles_every_form():
    for form, first, second, answer in [
        ("a+?=c", 8, 11, 3),
        ("?+b=c", 5, 12, 7),
        ("a-?=c", 14, 6, 8),
        ("?-b=c", 3, 5, 8),
        ("c=a+?", 11, 8, 3),
        ("c=?-b", 5, 3, 8),
    ]:
        right = make_puzzle([make_step(form, first, second)])
        assert check(right).ok, (form, check(right).failures)
        wrong = replace_step(right, 0, answer=answer + 2)
        assert F.WRONG_ANSWER in check(wrong).names, form


# ---- focused puzzles ----

AV = MistakeRule.ADD_VISIBLE
ALB = MistakeRule.ANSWER_LEFT_BACKWARDS
PC = MistakeRule.POSITION_CONFUSION


def focused_chain(focus: MistakeRule = AV) -> Puzzle:
    """8 + □ = 11,  □ − 3 = 5,  14 − □ = 8, built as a puzzle with a focus."""
    return make_puzzle(
        [
            make_step("a+?=c", 8, 11, focus=focus),
            make_step("?-b=c", 3, 5, link_position=0, focus=focus),
            make_step("a-?=c", 14, 8, link_position=1, focus=focus),
        ],
        focus=focus,
    )


def test_hand_built_focused_puzzles_pass():
    for focus in (AV, ALB, PC):
        result = check(focused_chain(focus))
        assert result.ok, (focus, result.failures)
    # The focus is in the id, and that is where the verifier reads it from.
    assert "-av-" in focused_chain(AV).puzzle_id
    assert "-pc-" in focused_chain(PC).puzzle_id


def test_the_focus_in_the_id_and_in_the_puzzle_must_agree():
    plain, focused = example_chain(), focused_chain(AV)

    says_focus_but_id_does_not = plain.model_copy(update={"focus": AV})
    id_says_focus_but_puzzle_does_not = focused.model_copy(update={"focus": None})
    another_focus = focused.model_copy(update={"focus": PC})

    for puzzle in (says_focus_but_id_does_not, id_says_focus_but_puzzle_does_not, another_focus):
        assert F.PUZZLE_ID_MISMATCH in check(puzzle).names


def test_a_rule_that_cannot_be_a_focus_is_rejected():
    for rule in (MistakeRule.OFF_BY_ONE_OVER, MistakeRule.PLACE_VALUE_SLIP, MistakeRule.NEAR_MISS):
        puzzle = example_chain().model_copy(update={"focus": rule})
        assert F.UNSUPPORTED_FOCUS in check(puzzle).names

    # An id with a focus code nobody defined.
    chain = example_chain()
    unknown = chain.model_copy(
        update={"puzzle_id": make_puzzle_id(chain.generator_version, 1, 3, chain.seed, "zz")}
    )
    assert F.UNSUPPORTED_FOCUS in check(unknown).names


def test_the_focus_distractor_must_be_there_and_come_first():
    puzzle = focused_chain(AV)
    first = puzzle.steps[0]
    assert first.distractors[0].rule is AV  # 8 + 11 = 19

    # Present, but not in the first slot.
    moved = replace_step(puzzle, 0, distractors=list(reversed(first.distractors)))
    assert check(moved).names == {F.FOCUS_DISTRACTOR_MISSING}

    # Not there at all: a filler in its place (3 − 2 = 1 is already an option, so 5).
    filler = Distractor(value=5, rule=MistakeRule.NEAR_MISS)
    assert filler.value not in [d.value for d in first.distractors]
    dropped = replace_step(puzzle, 0, distractors=[filler, *first.distractors[1:]])
    assert check(dropped).names == {F.FOCUS_DISTRACTOR_MISSING}

    # The same options without a focus are fine: the rule only binds focused puzzles.
    plain = example_chain()
    unfocused = replace_step(plain, 0, distractors=list(reversed(plain.steps[0].distractors)))
    assert check(unfocused).ok


def test_the_focus_distractor_is_not_demanded_where_the_rule_gives_nothing():
    # 5 = □ − 9: answer-left-backwards would be 5 − 9, below zero, so there is no value.
    puzzle = make_puzzle([make_step("c=?-b", 5, 9, focus=ALB)], focus=ALB)

    assert all(d.rule is not ALB for d in puzzle.steps[0].distractors)
    assert check(puzzle).ok
    # □ − 3 = 5 with a position-confusion focus: 5 − 3 = 2 has to be first.
    with_value = make_puzzle([make_step("?-b=c", 3, 5, focus=PC)], focus=PC)
    assert with_value.steps[0].distractors[0].rule is PC
    assert check(with_value).ok


def answer_left_chain(count: int, focus: MistakeRule | None) -> Puzzle:
    """5 = □ − 3,  12 = 8 + □,  9 = □ − 4: one, two or three answer-left steps."""
    steps = [
        make_step("c=?-b", 5, 3, focus=focus),
        make_step("c=a+?", 12, 8, link_position=1, focus=focus),
        make_step("c=?-b", 9, 4, link_position=1, focus=focus),
    ]
    return make_puzzle(steps[:count], focus=focus)


def test_answer_left_limit_with_and_without_the_focus_that_raises_it():
    assert check(answer_left_chain(1, None)).ok
    assert check(answer_left_chain(2, None)).names == {F.TOO_MANY_ANSWER_LEFT}

    # ANSWER_LEFT_BACKWARDS allows two at levels 1 and 2, and no more.
    assert check(answer_left_chain(2, ALB)).ok
    assert check(answer_left_chain(3, ALB)).names == {F.FOCUS_TOO_MANY_ANSWER_LEFT}

    # Another focus does not raise the limit.
    assert F.TOO_MANY_ANSWER_LEFT in check(answer_left_chain(2, AV)).names


def test_a_longer_focused_chain_needs_a_step_the_focus_does_not_target():
    # 8 + □ = 11,  □ + 3 = 10,  7 + □ = 12: every form is one ADD_VISIBLE targets.
    steps = [
        make_step("a+?=c", 8, 11, focus=AV),
        make_step("?+b=c", 3, 10, link_position=0, focus=AV),
        make_step("a+?=c", 7, 12, link_position=0, focus=AV),
    ]

    assert check(make_puzzle(steps, focus=AV)).names == {F.FOCUS_NO_UNTARGETED_STEP}
    # Two steps may both be targeted, and without a focus there is no such rule.
    assert check(make_puzzle(steps[:2], focus=AV)).ok
    plain = [
        make_step("a+?=c", 8, 11),
        make_step("?+b=c", 3, 10, link_position=0),
        make_step("a+?=c", 7, 12, link_position=0),
    ]
    assert check(make_puzzle(plain)).ok


def test_the_verifier_does_not_import_the_generator():
    package = Path(__file__).parents[2] / "app" / "puzzles" / "types" / "missing_number"
    source = (package / "verifier.py").read_text("utf-8")

    assert "missing_number.generator" not in source
    assert "missing_number.verified" not in source and "core.verified" not in source
    assert "missing_number.puzzle_type" not in source
    # It solves by trying numbers, not with the generator's closed-form arithmetic.
    assert "missing_number.equations" not in source
    # The check above would pass by accident if the imports were written another way.
    assert "from app.puzzles.types.missing_number.rules import" in source
    assert "import_module" not in source and "from . import" not in source


@pytest.mark.parametrize("name", list(FailureName))
def test_every_failure_name_is_exercised_by_a_test(name):
    source = Path(__file__).read_text("utf-8")
    assert f"F.{name.name}" in source, f"no test mentions {name.name}"
