"""The verifier on puzzles written by hand: what fits, what is ambiguous, what breaks a rule."""

from pathlib import Path

import pytest

from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import GENERATOR_VERSION, TOPIC_SKIP_COUNTING
from app.puzzles.types.sequences.models import Distractor, MistakeRule, SequencePuzzle
from app.puzzles.types.sequences.verifier import (
    FailureName as F,
)
from app.puzzles.types.sequences.verifier import (
    VerificationResult,
    fitting_rules,
    verify,
)
from tests.sequences.support import make_catalog, make_puzzle, topic_exists

CATALOG = make_catalog()


def check(puzzle: SequencePuzzle) -> VerificationResult:
    return verify(puzzle, catalog=CATALOG, topic_exists=topic_exists)


def names(puzzle: SequencePuzzle) -> set[F]:
    return check(puzzle).names


def fits(visible: dict[int, int], length: int) -> dict[str, tuple[int, ...]]:
    return {rule.name: rule.terms for rule in fitting_rules(visible, length).rules}


# ---- the examples from the spec are valid puzzles ----


@pytest.mark.parametrize(
    ("terms", "blanks", "level", "kind"),
    [
        ([4, 8, 12, 16, 20], [4], 1, "constant"),
        ([4, 8, 12, 16, 20], [3], 2, "constant"),  # 4, 8, 12, □, 20
        ([50, 100, 150, 200, 250], [1], 2, "constant"),  # 50, □, 150, 200, 250
        ([9, 6, 3, 0, -3], [4], 3, "constant"),  # 9, 6, 3, 0, □
        ([1, 2, 4, 7, 11], [4], 3, "growing"),  # 1, 2, 4, 7, □
        ([45, 35, 25, 15, 5], [3, 4], 2, "constant"),
        ([12, 8, 4, 0, -4, -8], [4, 5], 3, "constant"),
        ([3, 5, 8, 12, 17, 23], [1], 3, "growing"),
        ([3, 5, 8, 12, 17, 23], [4, 5], 3, "growing"),
    ],
)
def test_hand_built_valid_puzzles_pass(terms, blanks, level, kind):
    result = check(make_puzzle(terms, blanks, level=level, kind=kind))
    assert result.ok, result.failures


# ---- which rules fit ----


def test_two_visible_terms_fit_a_step_and_a_ratio_and_leave_growing_open():
    fit = fitting_rules({0: 2, 1: 4}, 3)

    assert {rule.name: rule.terms for rule in fit.rules} == {"+2": (2, 4, 6), "×2": (2, 4, 8)}
    # Any growth at all passes through two points.
    assert fit.open_families == ["growing"]


def test_three_terms_in_a_row_leave_one_rule_whichever_family_it_is():
    assert fits({0: 2, 1: 4, 2: 6}, 5) == {"+2": (2, 4, 6, 8, 10)}
    assert fits({0: 2, 1: 4, 2: 8}, 4) == {"×2": (2, 4, 8, 16), "step grows by 2": (2, 4, 8, 14)}
    assert fits({0: 1, 1: 3, 2: 9}, 4) == {"×3": (1, 3, 9, 27), "step grows by 4": (1, 3, 9, 19)}
    assert fits({0: 20, 1: 17, 2: 14}, 5) == {"−3": (20, 17, 14, 11, 8)}
    assert fitting_rules({0: 2, 1: 4, 2: 6}, 5).open_families == []


def test_the_growing_rule_is_found_from_terms_that_are_not_next_to_each_other():
    # 1, 2, □, 7, □: only one rule of the declared set passes through these three.
    assert fits({0: 1, 1: 2, 3: 7}, 5) == {"step grows by 1": (1, 2, 4, 7, 11)}
    # 50, □, 150, 200, 250
    assert fits({0: 50, 2: 150, 3: 200, 4: 250}, 5) == {"+50": (50, 100, 150, 200, 250)}


def test_rules_that_would_need_fractions_or_a_zero_step_do_not_fit():
    assert fits({0: 1, 2: 4, 4: 7}, 5) == {}  # a step of one and a half
    assert fits({0: 5, 1: 5, 2: 5}, 4) == {}  # no step at all
    assert fits({1: 3, 2: 6}, 3) == {"+3": (0, 3, 6)}  # ×2 would start at 1.5
    assert fits({0: 0, 1: 0, 2: 1}, 4) == {"step grows by 1": (0, 0, 1, 3)}


def test_one_visible_term_pins_nothing_down():
    fit = fitting_rules({0: 4}, 3)
    assert fit.rules == []
    assert set(fit.open_families) == {"constant", "ratio", "growing"}


# ---- ambiguity ----


def test_two_four_blank_is_rejected_because_plus_two_and_times_two_both_fit():
    result = check(make_puzzle([2, 4, 6], [2], level=1))

    assert F.AMBIGUOUS in result.names
    detail = next(f.detail for f in result.failures if f.name is F.AMBIGUOUS)
    assert "+2 gives [6]" in detail and "×2 gives [8]" in detail
    # It is also too short, and shows too little.
    assert {F.BAD_LENGTH, F.NOT_ENOUGH_EVIDENCE} <= result.names


def test_its_unambiguous_counterpart_passes():
    # The same rule with three terms in a row on show: ×2 no longer fits.
    assert check(make_puzzle([2, 4, 6, 8, 10], [4], level=1)).ok
    assert check(make_puzzle([2, 4, 6, 8, 10], [3, 4], level=2)).ok


def test_a_growing_puzzle_with_three_visible_terms_is_rejected():
    # 1, 2, 4, □, □ reads as "+1, +2, +3" (7, 11) and as doubling (8, 16).
    doubling = check(make_puzzle([1, 2, 4, 7, 11], [3, 4], level=3, kind="growing"))
    assert doubling.names == {F.AMBIGUOUS, F.NOT_ENOUGH_EVIDENCE}
    detail = next(f.detail for f in doubling.failures if f.name is F.AMBIGUOUS)
    assert "step grows by 1 gives [7, 11]" in detail and "×2 gives [8, 16]" in detail

    # 3, 5, 8, □, □ has one reading in the declared set, and still shows too
    # little: the growth is on show only once.
    thin = check(make_puzzle([3, 5, 8, 12, 17], [3, 4], level=3, kind="growing"))
    assert thin.names == {F.NOT_ENOUGH_EVIDENCE}


def test_its_counterparts_with_four_visible_terms_pass():
    assert check(make_puzzle([1, 2, 4, 7, 11], [4], level=3, kind="growing")).ok
    assert check(make_puzzle([3, 5, 8, 12, 17], [4], level=3, kind="growing")).ok
    assert check(make_puzzle([3, 5, 8, 12, 17, 23], [4, 5], level=3, kind="growing")).ok


def test_a_constant_puzzle_needs_three_visible_terms_in_a_row():
    # □ at 1 and 3 of five: 50, □, 150, □, 250. One rule fits, but no two
    # visible terms are neighbours, so the step is never on show.
    result = check(make_puzzle([50, 100, 150, 200, 250], [1, 3], level=2))
    assert result.names == {F.NOT_ENOUGH_EVIDENCE}

    assert check(make_puzzle([50, 100, 150, 200, 250, 300], [1, 5], level=2)).ok


def test_a_growing_puzzle_needs_four_in_a_row_even_with_four_visible():
    # 3, □, 8, 12, 17, □: four visible terms, three in a row.
    result = check(make_puzzle([3, 5, 8, 12, 17, 23], [1, 5], level=3, kind="growing"))
    assert result.names == {F.NOT_ENOUGH_EVIDENCE}


# ---- the stored answer ----


def test_a_wrong_stored_answer_is_caught_from_the_visible_terms_alone():
    good = make_puzzle([4, 8, 12, 16, 20], [4], level=1)
    step = good.steps[0].model_copy(update={"answer": 21})
    bad = good.model_copy(update={"steps": [step], "terms": [4, 8, 12, 16, 21]})

    result = check(bad)
    assert F.WRONG_ANSWER in result.names
    detail = next(f.detail for f in result.failures if f.name is F.WRONG_ANSWER)
    assert "the rule gives 20" in detail


def test_the_kind_a_puzzle_claims_must_be_one_that_fits():
    # A growing row filed as "constant": no constant rule passes through it.
    growing = make_puzzle([1, 2, 4, 7, 11], [4], level=3, kind="growing")
    mislabelled = growing.model_copy(update={"kind": "constant"})
    assert F.NO_INTENDED_RULE in names(mislabelled)

    # Growing is not a kind level 2 has at all.
    assert names(growing.model_copy(update={"level": 2})) == {F.UNSUPPORTED_PUZZLE}


# ---- the level's own rules ----


@pytest.mark.parametrize(
    ("terms", "blanks", "level", "kind", "expected"),
    [
        # level 1 only goes up, in steps of 1 to 5 or 10, one blank, at the end
        ([20, 16, 12, 8, 4], [4], 1, "constant", {F.BAD_DIRECTION}),
        ([7, 14, 21, 28, 35], [4], 1, "constant", {F.BAD_STEP}),
        ([4, 8, 12, 16, 20], [2], 1, "constant", {F.BAD_BLANKS}),
        ([4, 8, 12, 16, 20], [3, 4], 1, "constant", {F.BAD_BLANKS}),
        ([80, 90, 100, 110, 120], [4], 1, "constant", {F.VALUE_OUT_OF_RANGE}),
        # level 2: the listed steps, nothing below zero
        ([7, 14, 21, 28, 35], [4], 2, "constant", {F.BAD_STEP}),
        ([6, 4, 2, 0, -2], [3], 2, "constant", {F.VALUE_OUT_OF_RANGE}),
        ([900, 950, 1000, 1050, 1100], [1], 2, "constant", {F.VALUE_OUT_OF_RANGE}),
        # level 3, constant: down, through zero, a blank below it, no lower than −50
        (
            [4, 8, 12, 16, 20],
            [4],
            3,
            "constant",
            {F.BAD_DIRECTION, F.NOT_THROUGH_ZERO, F.NO_BLANK_BELOW_ZERO},
        ),
        ([20, 17, 14, 11, 8], [4], 3, "constant", {F.NOT_THROUGH_ZERO, F.NO_BLANK_BELOW_ZERO}),
        ([9, 6, 3, 0, -3], [2], 3, "constant", {F.NO_BLANK_BELOW_ZERO}),
        ([0, -3, -6, -9, -12], [4], 3, "constant", {F.NOT_THROUGH_ZERO}),
        ([10, -10, -30, -50, -70], [4], 3, "constant", {F.BAD_STEP, F.VALUE_OUT_OF_RANGE}),
        # level 3, growing: the step grows by 1 or 2, from a first step of at least 1
        ([1, 3, 8, 16, 27], [4], 3, "growing", {F.BAD_GROWTH}),  # grows by 3
        ([30, 28, 27, 27, 28], [4], 3, "growing", {F.BAD_GROWTH}),  # starts by going down
    ],
)
def test_level_rules(terms, blanks, level, kind, expected):
    found = names(make_puzzle(terms, blanks, level=level, kind=kind))
    assert expected <= found, found
    # None of these is about the options or the hints.
    assert not {n for n in found if n.value.startswith(("distractor", "hint"))} - {
        F.DISTRACTOR_OUT_OF_RANGE,
        F.DISTRACTOR_RULE_MISMATCH,
        F.DISTRACTOR_COUNT,
        F.HINT_REVEALS_ANSWER,
    }


def test_a_blank_may_never_be_the_first_term_or_out_of_order():
    good = make_puzzle([50, 100, 150, 200, 250, 300], [1, 5], level=2)
    assert check(good).ok

    first = make_puzzle([50, 100, 150, 200, 250], [1], level=2)
    first = first.model_copy(
        update={"steps": [first.steps[0].model_copy(update={"position": 0, "answer": 50})]}
    )
    assert names(first) == {F.BAD_BLANKS}
    swapped = good.model_copy(update={"steps": good.steps[::-1]})
    assert names(swapped) == {F.BAD_BLANKS}
    none = good.model_copy(update={"steps": []})
    assert names(none) == {F.BAD_BLANKS}
    three = make_puzzle([50, 100, 150, 200, 250, 300], [3, 4, 5], level=2)
    assert F.BAD_BLANKS in names(three)


def test_the_number_of_terms():
    assert F.BAD_LENGTH in names(make_puzzle([4, 8, 12, 16], [3], level=1))
    assert F.BAD_LENGTH in names(make_puzzle([4, 8, 12, 16, 20, 24, 28], [6], level=1))
    assert check(make_puzzle([4, 8, 12, 16, 20, 24], [5], level=1)).ok


# ---- identity, topics ----


def test_the_id_must_describe_the_puzzle():
    good = make_puzzle([4, 8, 12, 16, 20], [4], level=1, seed=7)

    other_seed = good.model_copy(update={"seed": 8})
    assert names(other_seed) == {F.PUZZLE_ID_MISMATCH}
    other_level = good.model_copy(update={"puzzle_id": make_sequence_id(GENERATOR_VERSION, 2, 7)})
    assert names(other_level) == {F.PUZZLE_ID_MISMATCH}
    assert names(good.model_copy(update={"generator_version": "0"})) == {F.UNSUPPORTED_PUZZLE}
    assert names(good.model_copy(update={"level": 9})) == {F.UNSUPPORTED_PUZZLE}


def test_topics_follow_the_kind_and_must_exist():
    through_zero = make_puzzle([9, 6, 3, 0, -3], [4], level=3)
    growing = make_puzzle([1, 2, 4, 7, 11], [4], level=3, kind="growing")
    assert through_zero.topic_ids != growing.topic_ids

    swapped = through_zero.model_copy(update={"topic_ids": growing.topic_ids})
    assert names(swapped) == {F.WRONG_TOPICS}
    result = verify(through_zero, catalog=CATALOG, topic_exists=lambda _topic_id: False)
    assert result.names == {F.UNKNOWN_TOPIC}


# ---- options ----


def with_distractors(puzzle: SequencePuzzle, distractors: list[Distractor]) -> SequencePuzzle:
    step = puzzle.steps[0].model_copy(update={"distractors": distractors})
    return puzzle.model_copy(update={"steps": [step, *puzzle.steps[1:]]})


def test_distractors_must_be_three_different_wrong_values_that_their_rules_give():
    good = make_puzzle([20, 17, 14, 11, 8], [4], level=2)
    wrong_direction, count_by_one, skipped = good.steps[0].distractors
    assert (wrong_direction.value, count_by_one.value, skipped.value) == (14, 10, 5)
    assert wrong_direction.error_pattern_id == "mt_hBZwbst0ow#4"

    assert names(with_distractors(good, [wrong_direction, count_by_one])) == {F.DISTRACTOR_COUNT}
    twice = [wrong_direction, count_by_one, count_by_one]
    assert F.DUPLICATE_DISTRACTOR in names(with_distractors(good, twice))
    is_answer = [wrong_direction, count_by_one, Distractor(value=8, rule=MistakeRule.SKIPPED_TERM)]
    assert names(with_distractors(good, is_answer)) == {F.DISTRACTOR_EQUALS_ANSWER}
    invented = [wrong_direction, count_by_one, Distractor(value=6, rule=MistakeRule.SKIPPED_TERM)]
    assert names(with_distractors(good, invented)) == {F.DISTRACTOR_RULE_MISMATCH}
    not_applicable = [
        wrong_direction,
        count_by_one,
        Distractor(value=0, rule=MistakeRule.STOPS_AT_ZERO, error_pattern_id="mt_hBZwbst0ow#0"),
    ]
    assert names(with_distractors(good, not_applicable)) == {F.DISTRACTOR_RULE_MISMATCH}


def test_a_distractor_carries_exactly_the_pattern_the_catalog_gives_its_rule():
    good = make_puzzle([20, 17, 14, 11, 8], [4], level=2)
    wrong_direction, count_by_one, skipped = good.steps[0].distractors

    unlinked = wrong_direction.model_copy(update={"error_pattern_id": None})
    assert names(with_distractors(good, [unlinked, count_by_one, skipped])) == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }
    invented = count_by_one.model_copy(update={"error_pattern_id": f"{TOPIC_SKIP_COUNTING}#0"})
    assert names(with_distractors(good, [wrong_direction, invented, skipped])) == {
        F.DISTRACTOR_PATTERN_MISMATCH
    }


def test_options_outside_the_range_and_bad_fillers():
    # 8, 6, 4, 2, □ at level 2: −2 would be the skipped term, and is below the range.
    good = make_puzzle([8, 6, 4, 2, 0], [4], level=2)
    first, second, third = good.steps[0].distractors
    below = Distractor(value=-2, rule=MistakeRule.SKIPPED_TERM)
    assert F.DISTRACTOR_OUT_OF_RANGE in names(with_distractors(good, [first, second, below]))

    filler = Distractor(value=7, rule=MistakeRule.NEAR_MISS)  # 7 away from 0 is no offset
    assert names(with_distractors(good, [first, second, filler])) == {F.DISTRACTOR_RULE_MISMATCH}
    far_filler = Distractor(value=-2, rule=MistakeRule.NEAR_MISS)
    assert names(with_distractors(good, [first, second, far_filler])) == {F.DISTRACTOR_OUT_OF_RANGE}
    ok_filler = Distractor(value=5, rule=MistakeRule.NEAR_MISS)
    replaced = [d for d in (first, second, third) if d.value != 5][:2]
    assert check(with_distractors(good, [*replaced, ok_filler])).ok


# ---- hints ----


def with_hints(puzzle: SequencePuzzle, hints: list[str]) -> SequencePuzzle:
    step = puzzle.steps[0].model_copy(update={"hints": hints})
    return puzzle.model_copy(update={"steps": [step, *puzzle.steps[1:]]})


def test_hints_must_be_three_and_only_the_last_shows_the_answer():
    good = make_puzzle([9, 6, 3, 0, -3], [4], level=3)
    look, rule, worked = good.steps[0].hints

    assert names(with_hints(good, [look, rule])) == {F.HINT_COUNT}
    assert names(with_hints(good, [look, worked, worked])) == {F.HINT_REVEALS_ANSWER}
    assert names(with_hints(good, [look, "It is −3.", worked])) == {F.HINT_REVEALS_ANSWER}
    assert names(with_hints(good, [look, rule, rule])) == {F.HINT_MISSING_ANSWER}
    # "3" is not "−3": saying how big the step is does not give a negative answer away.
    assert "3" in rule and check(good).ok
    # ...and writing 3 where −3 is meant is not showing the answer either.
    assert names(with_hints(good, [look, rule, "0 − 3 = 3"])) == {F.HINT_MISSING_ANSWER}


def test_a_positive_answer_may_not_be_quoted_by_the_second_hint():
    # 16, 12, 8, □, 0, □ with a step of 4: "goes down by 4" would say the first answer.
    # The second answer is −4, which "down by 4" does not say.
    result = check(make_puzzle([16, 12, 8, 4, 0, -4], [3, 5], level=3))
    assert result.names == {F.HINT_REVEALS_ANSWER}
    assert [f.step for f in result.failures] == [0]


# ---- independence ----


def test_the_verifier_does_not_import_the_generator():
    package = Path(__file__).parents[2] / "app" / "puzzles" / "types" / "sequences"
    source = (package / "verifier.py").read_text("utf-8")

    assert "sequences.generator" not in source
    assert "sequences.verified" not in source and "core.verified" not in source
    assert "sequences.puzzle_type" not in source
    assert "from app.puzzles.types.sequences.rules import" in source
    assert "import_module" not in source and "from . import" not in source


@pytest.mark.parametrize("name", list(F))
def test_every_failure_name_is_exercised_by_a_test(name):
    source = Path(__file__).read_text("utf-8")
    assert f"F.{name.name}" in source, f"no test mentions {name.name}"
