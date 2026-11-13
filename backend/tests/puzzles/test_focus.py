"""Focused puzzles: generation that targets one mistake rule."""

import functools
import itertools
import json
import logging
from collections import Counter

import pytest

from app.puzzles.equations import ALL_FORMS, visible_numbers
from app.puzzles.hints import FOCUS_ADD_VISIBLE, MEANING, MEANING_ANSWER_LEFT, build_hints
from app.puzzles.ids import InvalidPuzzleId, make_puzzle_id, parse_puzzle_id
from app.puzzles.levels import (
    ANSWER_LEFT_FORMS,
    FOCUS_BY_CODE,
    FOCUS_CODES,
    FOCUS_TARGET_FORMS,
    FOCUS_WEIGHT_FACTOR,
    GENERATOR_VERSION,
    LEVELS,
    answer_left_limit,
    supported_focus,
)
from app.puzzles.models import MistakeRule, Puzzle
from app.puzzles.rules import RULES, distractor_value
from app.puzzles.verified import generate_verified, regenerate
from app.puzzles.verifier import verify
from tests.puzzles.baseline import BASELINE_FILE, SEEDS, current_fingerprints
from tests.puzzles.support import make_catalog, make_step, topic_exists

CATALOG = make_catalog()
FOCUSES = list(FOCUS_TARGET_FORMS)
AV, ALB, PC = (
    MistakeRule.ADD_VISIBLE,
    MistakeRule.ANSWER_LEFT_BACKWARDS,
    MistakeRule.POSITION_CONFUSION,
)


@functools.cache
def make(seed: int, level: int, length: int, focus: MistakeRule | None = None) -> Puzzle:
    return generate_verified(seed, level, length, focus, catalog=CATALOG, topic_exists=topic_exists)


def sample(focus: MistakeRule | None, level: int, lengths=(3, 4), seeds: int = 150) -> list[Puzzle]:
    return [make(seed, level, length, focus) for seed in range(seeds) for length in lengths]


# ---- no focus: nothing changes ----


def test_without_a_focus_the_output_is_identical_to_version_2_for_2000_seeds():
    """The fingerprints were written by generator version 2, before focus existed.

    They cover everything in a puzzle except its id and version stamp, which
    the bump to version 3 changes by definition. This was also run before the
    bump, with the version still at 2: 2000 of 2000 identical.
    """
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    assert baseline["written_by_generator_version"] == "2"
    assert baseline["seeds"] == SEEDS == 2000

    now = current_fingerprints()

    different = [
        seed
        for seed, (old, new) in enumerate(zip(baseline["fingerprints"], now, strict=True))
        if old != new
    ]
    assert different == []


def test_a_puzzle_without_a_focus_has_none_and_a_plain_id():
    puzzle = make(5, 1, 3)

    assert puzzle.focus is None
    assert puzzle.puzzle_id == make_puzzle_id(GENERATOR_VERSION, 1, 3, puzzle.seed)
    assert len(puzzle.puzzle_id.split("-")) == 6
    assert make(5, 1, 3, None) == puzzle


def test_a_rule_that_cannot_be_targeted_is_logged_and_treated_as_no_focus(caplog):
    plain = make(9, 2, 3)

    for rule in MistakeRule:
        if rule in FOCUS_TARGET_FORMS:
            continue
        assert supported_focus(rule) is None
        with caplog.at_level(logging.INFO, logger="app.puzzles.verified"):
            assert make(9, 2, 3, rule) == plain
        assert f"Focus {rule.value} has no effect" in caplog.text
        caplog.clear()
    assert supported_focus(None) is None
    assert [supported_focus(rule) for rule in FOCUSES] == FOCUSES


# ---- what a focus is ----


def test_the_target_forms_are_the_forms_each_rule_gives_a_value_on():
    assert set(FOCUS_TARGET_FORMS) == {AV, ALB, PC}
    assert FOCUS_TARGET_FORMS[AV] == {"a+?=c", "?+b=c", "c=a+?"}
    assert FOCUS_TARGET_FORMS[ALB] == {"c=?-b"}
    assert FOCUS_TARGET_FORMS[PC] == {"?-b=c"}
    assert FOCUS_WEIGHT_FACTOR == 3.0

    # Checked against rules.py itself: a rule applies to a form if it gives a
    # value for some pair of visible numbers.
    pairs = {
        "a+?=c": [(4, 9)],
        "?+b=c": [(4, 9)],
        "a-?=c": [(9, 4)],
        "?-b=c": [(4, 9), (9, 4)],
        "c=a+?": [(9, 4)],
        "c=?-b": [(4, 9), (9, 4)],
    }
    for rule, targets in FOCUS_TARGET_FORMS.items():
        applies = {
            form
            for form in ALL_FORMS
            if any(RULES[rule](make_step(form, x, y)) is not None for x, y in pairs[form])
        }
        assert applies == targets, rule


def test_focus_codes():
    assert FOCUS_CODES == {AV: "av", ALB: "ab", PC: "pc"}
    assert FOCUS_BY_CODE == {"av": AV, "ab": ALB, "pc": PC}


# ---- what a focus changes ----


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_focused_puzzles_pass_verification_and_carry_the_focus(focus, level):
    for puzzle in sample(focus, level, lengths=(1, 2, 3, 4), seeds=40):
        assert verify(puzzle, catalog=CATALOG, topic_exists=topic_exists).ok
        assert puzzle.focus is focus
        assert parse_puzzle_id(puzzle.puzzle_id).focus == FOCUS_CODES[focus]
        assert puzzle.level == level


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_target_forms_appear_more_often_with_the_focus(focus, level):
    targets = FOCUS_TARGET_FORMS[focus]

    def share(puzzles: list[Puzzle]) -> float:
        forms = [step.form for puzzle in puzzles for step in puzzle.steps]
        return sum(form in targets for form in forms) / len(forms)

    plain, focused = share(sample(None, level)), share(sample(focus, level))

    # A loose bound: clearly more, not a particular number.
    assert focused > plain + 0.08, (plain, focused)
    assert focused < 1.0


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_the_focus_distractor_comes_first_on_every_step_where_the_rule_gives_a_value(focus, level):
    spec = LEVELS[level]
    applicable = with_option = 0
    for puzzle in sample(focus, level):
        for step in puzzle.steps:
            value = distractor_value(focus, step, spec)
            if step.form in FOCUS_TARGET_FORMS[focus]:
                applicable += 1
            if value is None:
                assert all(d.rule is not focus for d in step.distractors)
                continue
            with_option += 1
            assert step.form in FOCUS_TARGET_FORMS[focus]
            assert step.distractors[0].rule is focus
            assert step.distractors[0].value == value
            assert step.distractors[0].error_pattern_id is not None
            assert value <= spec.distractor_max

    assert applicable > 100
    # ADD_VISIBLE always has a value. The two subtraction slips need c >= b, and
    # drawing the numbers again finds that most of the time.
    if focus is AV:
        assert with_option == applicable
    else:
        assert with_option / applicable > 0.75, (with_option, applicable)


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_a_chain_of_three_or_more_keeps_a_step_the_focus_does_not_target(focus, level):
    targets = FOCUS_TARGET_FORMS[focus]
    all_targeted_short = 0
    for length in (1, 2, 3, 4):
        for seed in range(150):
            forms = [step.form for step in make(seed, level, length, focus).steps]
            untargeted = sum(form not in targets for form in forms)
            if length >= 3:
                assert untargeted >= 1, (seed, length, forms)
            elif untargeted == 0:
                all_targeted_short += 1
    # Short chains may be all target forms (never for a one-form focus of length 2).
    if focus is AV:
        assert all_targeted_short > 0


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_other_constraint_still_holds(focus, level):
    spec = LEVELS[level]
    for puzzle in sample(focus, level):
        forms = [step.form for step in puzzle.steps]
        assert all(a != b for a, b in itertools.pairwise(forms)), forms
        for step in puzzle.steps:
            numbers = [*visible_numbers(step.equation), step.answer]
            assert all(1 <= number <= spec.max_value for number in numbers)
            assert len({d.value for d in step.distractors}) == 3
            assert all(0 <= d.value <= spec.distractor_max for d in step.distractors)
            assert step.answer not in [d.value for d in step.distractors]


def test_answer_left_backwards_allows_two_answer_left_steps_and_nothing_else_does():
    def most_answer_left(focus, level):
        counts = Counter()
        for puzzle in sample(focus, level, lengths=(3, 4), seeds=200):
            counts[sum(step.form in ANSWER_LEFT_FORMS for step in puzzle.steps)] += 1
        return max(counts), counts

    for level in (1, 2):
        assert answer_left_limit(LEVELS[level]) == 1
        assert answer_left_limit(LEVELS[level], ALB) == 2
        assert answer_left_limit(LEVELS[level], AV) == 1
        assert answer_left_limit(LEVELS[level], PC) == 1

        most, counts = most_answer_left(ALB, level)
        assert most == 2, counts
        assert counts[2] > 20
        for other in (None, AV, PC):
            assert most_answer_left(other, level)[0] == 1, other
    # Level 3 has no limit, with or without a focus.
    assert answer_left_limit(LEVELS[3]) is None
    assert answer_left_limit(LEVELS[3], ALB) is None


def test_a_focus_changes_the_puzzle_and_the_same_inputs_give_the_same_one():
    different = 0
    for seed in range(40):
        plain, focused = make(seed, 1, 3), make(seed, 1, 3, AV)
        assert focused == make(seed, 1, 3, AV)
        assert focused.puzzle_id != plain.puzzle_id
        different += [s.equation for s in focused.steps] != [s.equation for s in plain.steps]
    assert different > 20


# ---- ids ----


@pytest.mark.parametrize("focus", [None, *FOCUSES])
def test_a_puzzle_is_rebuilt_from_its_id_with_or_without_a_focus(focus):
    for seed in range(30):
        puzzle = make(seed, 2, 4, focus)

        again = regenerate(puzzle.puzzle_id, catalog=CATALOG, topic_exists=topic_exists)

        assert again == puzzle
        key = parse_puzzle_id(puzzle.puzzle_id)
        assert (key.generator_version, key.level, key.length, key.seed) == (
            GENERATOR_VERSION,
            2,
            4,
            puzzle.seed,
        )
        assert key.focus == (FOCUS_CODES[focus] if focus else None)


def test_id_round_trip_with_a_focus_code():
    with_focus = make_puzzle_id("3", 2, 3, 12345, "av")
    without = make_puzzle_id("3", 2, 3, 12345)

    assert with_focus.startswith("mnc-3-2-3-9ix-av-")
    assert without.startswith("mnc-3-2-3-9ix-")
    assert (len(with_focus.split("-")), len(without.split("-"))) == (7, 6)
    assert parse_puzzle_id(with_focus).focus == "av"
    assert parse_puzzle_id(without).focus is None
    # The checksum covers the focus: the two ids differ in more than the code.
    assert with_focus.rsplit("-", 1)[1] != without.rsplit("-", 1)[1]
    for bad_code in ("AV", "a1", "", "toolong", "a-b"):
        with pytest.raises(ValueError):
            make_puzzle_id("3", 2, 3, 1, bad_code)


def test_a_tampered_focus_code_is_not_a_valid_id():
    focused = make(3, 1, 3, AV).puzzle_id
    plain = make(3, 1, 3).puzzle_id
    body, checksum = focused.rsplit("-", 1)
    plain_body, plain_checksum = plain.rsplit("-", 1)

    tampered = [
        focused.replace("-av-", "-pc-"),  # another focus under the old checksum
        f"{plain_body}-av-{plain_checksum}",  # a focus added to a plain id
        f"{body.removesuffix('-av')}-{checksum}",  # the focus removed
        f"{body}-{checksum}-x",
        focused.replace("-av-", "-AV-"),
    ]
    for bad in tampered:
        with pytest.raises(InvalidPuzzleId):
            regenerate(bad, catalog=CATALOG, topic_exists=topic_exists)


def test_a_well_formed_id_with_an_unknown_focus_code_cannot_be_rebuilt():
    unknown = make_puzzle_id(GENERATOR_VERSION, 1, 3, 5, "zz")
    assert parse_puzzle_id(unknown).focus == "zz"

    with pytest.raises(InvalidPuzzleId, match="focus"):
        regenerate(unknown, catalog=CATALOG, topic_exists=topic_exists)


# ---- hints ----


def test_the_focus_lines_are_the_agreed_wording():
    assert FOCUS_ADD_VISIBLE == (
        "The box isn't always the answer to a sum. What number makes both sides worth the same?"
    )
    # 5 = □ − 3
    assert build_hints("c=?-b", 5, 3, 8, ALB)[0] == (
        "The answer can be on the left! Read it as: what number, take away 3, leaves 5?"
    )
    # □ − 3 = 5
    assert build_hints("?-b=c", 3, 5, 8, PC)[0] == (
        "The box comes first here. What number do you start with, so that taking away 3 leaves 5?"
    )
    for form in FOCUS_TARGET_FORMS[AV]:
        assert build_hints(form, 9, 4, 5, AV)[0] == FOCUS_ADD_VISIBLE


@pytest.mark.parametrize("focus", FOCUSES)
def test_only_tier_1_changes_and_only_on_the_steps_the_focus_targets(focus):
    for form in ALL_FORMS:
        plain = build_hints(form, 9, 4, 5)
        focused = build_hints(form, 9, 4, 5, focus)

        assert focused[1:] == plain[1:]
        if form in FOCUS_TARGET_FORMS[focus]:
            assert focused[0] != plain[0]
            assert focused[0] not in (MEANING, MEANING_ANSWER_LEFT)
        else:
            assert focused == plain
    assert build_hints("a+?=c", 4, 9, 5, None) == build_hints("a+?=c", 4, 9, 5)


@pytest.mark.parametrize("focus", FOCUSES)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_focus_hints_in_generated_puzzles_never_give_the_answer(focus, level):
    import re

    targeted = 0
    for puzzle in sample(focus, level):
        for step in puzzle.steps:
            numbers = [[int(n) for n in re.findall(r"\d+", hint)] for hint in step.hints]
            assert step.answer not in numbers[0]
            assert step.answer not in numbers[1]
            assert step.answer in numbers[2]
            if step.form in FOCUS_TARGET_FORMS[focus]:
                targeted += 1
                assert step.hints[0] not in (MEANING, MEANING_ANSWER_LEFT)
                # Any numbers in the focus line are the ones already on show.
                assert set(numbers[0]) <= set(visible_numbers(step.equation))
                assert "practis" not in step.hints[0].lower()
            else:
                assert step.hints[0] in (MEANING, MEANING_ANSWER_LEFT)
    assert targeted > 100
