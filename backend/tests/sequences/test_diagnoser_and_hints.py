"""The diagnoser, the rule catalog and the hint templates, on hand-built puzzles."""

import pytest

from app.puzzles.core.catalog import MisconceptionResolutionError
from app.puzzles.types.sequences.diagnoser import Diagnosis, diagnose
from app.puzzles.types.sequences.hints import LOOK, build_hints, quoted_numbers, written_numbers
from app.puzzles.types.sequences.levels import (
    TOPIC_GENERALISING,
    TOPIC_LINEAR_SEQUENCES,
    TOPIC_NEGATIVE_NUMBERS,
    TOPIC_SKIP_COUNTING,
)
from app.puzzles.types.sequences.misconceptions import RULE_PATTERNS, resolve_catalog
from app.puzzles.types.sequences.models import MistakeRule as R
from app.puzzles.types.sequences.models import SequencePuzzle
from app.puzzles.types.sequences.report import format_catalog, format_puzzle
from tests.sequences.support import (
    ERROR_PATTERN_ROWS,
    TOPIC_COUNTING_IN_2S,
    TOPIC_TEMPERATURE,
    TOPIC_WITHIN_20,
    make_catalog,
    make_puzzle,
    step_back,
)

CATALOG = make_catalog()


def answer(puzzle: SequencePuzzle, value: int, step: int = 0) -> Diagnosis:
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
        ("STOPS_AT_ZERO", f"{TOPIC_LINEAR_SEQUENCES}#0", TOPIC_TEMPERATURE),
        ("STOPS_AT_ZERO", f"{TOPIC_NEGATIVE_NUMBERS}#1", "mt_M2v1A9OEuM"),
        ("SIGN_DROPPED", f"{TOPIC_LINEAR_SEQUENCES}#1", None),
        ("WRONG_DIRECTION", f"{TOPIC_LINEAR_SEQUENCES}#4", None),
        ("BOUNDARY_SLIP", f"{TOPIC_SKIP_COUNTING}#2", None),
        ("CONSTANT_GAP", f"{TOPIC_GENERALISING}#2", None),
        ("COUNT_BY_ONE", None, None),
        ("SKIPPED_TERM", None, None),
        ("OFF_BY_ONE_OVER", None, None),
        ("OFF_BY_ONE_UNDER", None, None),
        ("NEAR_MISS", None, None),
    ]
    assert "STOPS_AT_ZERO" in format_catalog(CATALOG)
    assert "COUNT_BY_ONE       (none)" in format_catalog(CATALOG)


def test_count_by_one_is_deliberately_not_linked_to_sub_counting():
    # The nearest pattern describes a slow route to the right answer, not this wrong one.
    assert R.COUNT_BY_ONE not in RULE_PATTERNS
    assert not CATALOG.is_linked(R.COUNT_BY_ONE)
    assert CATALOG.get(f"{TOPIC_SKIP_COUNTING}#0") is None


def test_a_missing_or_doubled_pattern_fails_loudly():
    def without_stops(topic_id):
        return [row for row in ERROR_PATTERN_ROWS[topic_id] if "stop" not in row.pattern.lower()]

    with pytest.raises(MisconceptionResolutionError, match=r"STOPS_AT_ZERO.*found 0"):
        resolve_catalog(without_stops)

    def doubled(topic_id):
        rows = ERROR_PATTERN_ROWS[topic_id]
        return [*rows, *(row for row in rows if row.pattern.startswith("50s/100s"))]

    with pytest.raises(MisconceptionResolutionError, match=r"BOUNDARY_SLIP.*found 2"):
        resolve_catalog(doubled)


# ---- the diagnoser ----


def test_a_right_answer_and_an_unexplained_wrong_one():
    puzzle = make_puzzle([9, 6, 3, 0, -3], [4], level=3)

    assert answer(puzzle, -3) == Diagnosis(correct=True)
    assert answer(puzzle, 40) == Diagnosis(correct=False, unrecognized=True)


def test_stops_at_zero_maps_to_the_linear_sequences_pattern_and_its_reteach_topic():
    puzzle = make_puzzle([10, 6, 2, -2, -6], [4], level=3)

    diagnosis = answer(puzzle, 0)

    assert diagnosis.matched_rules == [R.STOPS_AT_ZERO]
    # The pattern on the step's primary topic, not the one on Negative Numbers.
    assert diagnosis.error_pattern_id == f"{TOPIC_LINEAR_SEQUENCES}#0"
    # The pattern itself says where to step back to: measuring temperature.
    assert diagnosis.reteach_topic_id == TOPIC_TEMPERATURE


def test_sign_dropped_maps_to_its_pattern_and_steps_back_through_the_graph():
    puzzle = make_puzzle([10, 6, 2, -2, -6], [4], level=3)

    diagnosis = answer(puzzle, 6)

    assert diagnosis.matched_rules == [R.SIGN_DROPPED]
    assert diagnosis.error_pattern_id == f"{TOPIC_LINEAR_SEQUENCES}#1"
    # That pattern names no topic, so the prerequisite graph decides.
    assert diagnosis.reteach_topic_id == step_back(TOPIC_LINEAR_SEQUENCES) == TOPIC_NEGATIVE_NUMBERS


def test_wrong_direction_maps_to_its_pattern_at_level_three():
    puzzle = make_puzzle([10, 6, 2, -2, -6], [4], level=3)

    diagnosis = answer(puzzle, 2)  # −2 + 4

    assert diagnosis.matched_rules == [R.WRONG_DIRECTION]
    assert diagnosis.error_pattern_id == f"{TOPIC_LINEAR_SEQUENCES}#4"
    assert diagnosis.reteach_topic_id == TOPIC_NEGATIVE_NUMBERS


def test_wrong_direction_at_level_two_keeps_the_pattern_but_reteaches_for_its_own_topic():
    # 20, 17, 14, 11, □ is skip counting. The pattern is written for linear
    # sequences, an older child's topic, so its level's step-back is not used.
    puzzle = make_puzzle([20, 17, 14, 11, 8], [4], level=2)

    diagnosis = answer(puzzle, 14)

    assert diagnosis.matched_rules == [R.WRONG_DIRECTION]
    assert diagnosis.error_pattern_id == f"{TOPIC_LINEAR_SEQUENCES}#4"
    assert diagnosis.reteach_topic_id == step_back(TOPIC_SKIP_COUNTING) == TOPIC_COUNTING_IN_2S


def test_an_answer_two_mistakes_give_names_both_linked_ones():
    # After 9, 6, 3, 0 the answer 3 is "dropped the sign" and "went up" at once.
    puzzle = make_puzzle([9, 6, 3, 0, -3], [4], level=3)

    diagnosis = answer(puzzle, 3)

    assert diagnosis.matched_rules == [R.SIGN_DROPPED, R.WRONG_DIRECTION]
    assert diagnosis.error_pattern_id == f"{TOPIC_LINEAR_SEQUENCES}#1"


def test_linked_rules_are_named_before_unlinked_ones():
    # 1, 2, 4, 7, □: 10 is "the last jump again" (linked) and one under 11 (not linked).
    puzzle = make_puzzle([1, 2, 4, 7, 11], [4], level=3, kind="growing")

    diagnosis = answer(puzzle, 10)

    assert diagnosis.matched_rules == [R.CONSTANT_GAP, R.OFF_BY_ONE_UNDER]
    assert diagnosis.error_pattern_id == f"{TOPIC_GENERALISING}#2"
    assert diagnosis.reteach_topic_id == step_back(TOPIC_GENERALISING) == TOPIC_WITHIN_20


def test_a_boundary_slip_and_an_unlinked_mistake():
    puzzle = make_puzzle([350, 400, 450, 500, 550], [3], level=2)

    slip = answer(puzzle, 400)
    assert slip.matched_rules == [R.BOUNDARY_SLIP]
    assert slip.error_pattern_id == f"{TOPIC_SKIP_COUNTING}#2"
    assert slip.reteach_topic_id == TOPIC_COUNTING_IN_2S

    # No pattern, but the mistake is known, so there is still somewhere to step back to.
    one_more = answer(puzzle, 451)
    assert one_more.matched_rules == [R.COUNT_BY_ONE]
    assert one_more.error_pattern_id is None
    assert one_more.reteach_topic_id == TOPIC_COUNTING_IN_2S
    assert one_more.unrecognized is False


def test_each_blank_is_diagnosed_against_its_own_place_in_the_row():
    puzzle = make_puzzle([12, 8, 4, 0, -4, -8], [4, 5], level=3)

    assert answer(puzzle, 4, step=0).matched_rules == [R.SIGN_DROPPED, R.WRONG_DIRECTION]
    assert answer(puzzle, 8, step=1).matched_rules == [R.SIGN_DROPPED]
    assert answer(puzzle, 0, step=1).matched_rules == [R.STOPS_AT_ZERO, R.WRONG_DIRECTION]
    assert answer(puzzle, -8, step=1).correct is True
    assert answer(puzzle, -8, step=0).matched_rules == [R.SKIPPED_TERM]


# ---- hints ----


def test_hints_for_a_step_going_up():
    assert build_hints([4, 8, 12, 16, 20], 4, "constant") == [
        LOOK,
        "Each time it goes up by 4. What is 16 + 4?",
        "16 + 4 = 20, so the missing number is 20.",
    ]


def test_hints_for_a_step_going_down_above_zero():
    assert build_hints([20, 17, 14, 11, 8], 4, "constant") == [
        LOOK,
        "Each time it goes down by 3. What is 11 − 3?",
        "11 − 3 = 8, so the missing number is 8.",
    ]


def test_hints_for_a_blank_below_zero():
    assert build_hints([9, 6, 3, 0, -3], 4, "constant") == [
        LOOK,
        "Keep going down by 3, past zero. The numbers below zero have a minus sign.",
        "0 − 3 = −3, so the missing number is −3.",
    ]
    assert build_hints([10, 6, 2, -2, -6], 4, "constant")[2] == (
        "−2 − 4 = −6, so the missing number is −6."
    )


def test_hints_for_a_growing_step():
    assert build_hints([1, 2, 4, 7, 11], 4, "growing") == [
        LOOK,
        "The jumps get bigger by 1 each time: +1, +2, +3… How big is the jump into the box?",
        "The jump into the box is +4. 7 + 4 = 11, so the missing number is 11.",
    ]
    assert build_hints([10, 13, 18, 25, 34, 45], 1, "growing")[1].startswith(
        "The jumps get bigger by 2 each time: +3, +5, +7…"
    )


def test_a_number_is_read_with_its_sign_only_when_the_sign_is_attached():
    assert written_numbers("0 − 3 = −3, so the missing number is −3.") == {0, 3, -3}
    assert written_numbers("−2 − 4 = −6") == {-2, 4, -6}
    assert written_numbers("+1, +2, +3…") == {1, 2, 3}
    assert written_numbers(LOOK) == set()
    assert written_numbers("down by 3, past zero") == {3}


def test_quoted_numbers_are_what_the_second_hint_shows():
    assert quoted_numbers([4, 8, 12, 16, 20], 4, "constant") == {4, 16}
    assert quoted_numbers([9, 6, 3, 0, -3], 4, "constant") == {3}
    assert quoted_numbers([1, 2, 4, 7, 11], 4, "growing") == {1, 2, 3}


# ---- the report's printing ----


def test_format_puzzle_shows_the_row_with_boxes_and_real_minus_signs():
    text = format_puzzle(make_puzzle([9, 6, 3, 0, -3], [4], level=3))

    assert "9, 6, 3, 0, □" in text
    assert "-> −3" in text
    assert "STOPS_AT_ZERO  -> mt_hBZwbst0ow#0" in text
    assert "hint 3: 0 − 3 = −3" in text
    assert "constant, down through zero" in text
