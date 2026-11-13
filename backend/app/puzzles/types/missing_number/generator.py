"""Builds a missing-number chain from a seed. Reproducible, and nothing else.

    generate(seed, level, length, catalog, focus=None) -> Puzzle

The same inputs and GENERATOR_VERSION always give the same puzzle: all
randomness comes from one local random.Random(seed). Bump GENERATOR_VERSION in
levels.py whenever a change here (or in rules, hints or levels) can alter the
output for an existing seed.

This module does not check its own work. verifier.py does that, separately,
and generate_verified (app/puzzles/core/verified.py) is the entry point that puts
the two together. A seed that cannot be completed raises GenerationError.

How a step is built: every equation is part + part = whole with one number
hidden. From the second step on, the previous answer must be one of the two
visible numbers (the linking rule), so each step picks a form and a position
for that linked number, then chooses the one remaining free number so that
everything stays inside the level's range.

Focus: with a mistake rule as `focus`, the forms where that mistake happens
are picked more often, its wrong answer takes the first option slot wherever
it exists, and the first hint is worded around it (levels.py lists what each
focus changes). Without a focus nothing extra is drawn from the random
generator, so the puzzle for a seed is exactly what it was before focus existed.
"""

import random
from dataclasses import dataclass

from app.puzzles.core import GenerationError
from app.puzzles.types.missing_number.equations import ALL_FORMS, FORMS, build_equation
from app.puzzles.types.missing_number.hints import build_hints
from app.puzzles.types.missing_number.ids import MAX_SEED, make_puzzle_id
from app.puzzles.types.missing_number.levels import (
    ANSWER_LEFT_FORMS,
    DISTRACTORS_PER_STEP,
    FOCUS_CODES,
    FOCUS_NUMBER_DRAWS,
    FOCUS_TARGET_FORMS,
    FOCUS_UNTARGETED_FROM_LENGTH,
    FOCUS_WEIGHT_FACTOR,
    FORM_WEIGHTS,
    GENERATOR_VERSION,
    LEVELS,
    MAX_STEPS,
    MIN_STEPS,
    LevelSpec,
    answer_left_limit,
    supported_focus,
    topic_ids_for,
)
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog
from app.puzzles.types.missing_number.models import (
    Distractor,
    Form,
    HintSource,
    MistakeRule,
    Puzzle,
    PuzzleStep,
)
from app.puzzles.types.missing_number.rules import distractor_value

# The order mistake rules are tried in within a tier. _distractors puts the
# rules that have a taxonomy error pattern ahead of the ones that do not.
DISTRACTOR_RULE_ORDER: tuple[MistakeRule, ...] = (
    MistakeRule.ADD_VISIBLE,
    MistakeRule.ANSWER_LEFT_BACKWARDS,
    MistakeRule.POSITION_CONFUSION,
    MistakeRule.PLACE_VALUE_SLIP,
    MistakeRule.OFF_BY_ONE_OVER,
    MistakeRule.OFF_BY_ONE_UNDER,
)


@dataclass(frozen=True)
class _Numbers:
    first: int
    second: int
    answer: int


def _pick(rng: random.Random, low: int, high: int, preferred_low: int) -> int | None:
    """A whole number from low..high, from preferred_low up when that leaves any."""
    if low > high:
        return None
    return rng.randint(max(low, preferred_low) if preferred_low <= high else low, high)


def _weighted_order(
    rng: random.Random, options: list[tuple[Form, int | None]], targets: frozenset[Form]
) -> list[tuple[Form, int | None]]:
    """The options in a random order where heavier forms tend to come first.

    Each option draws a key u ** (1 / weight), u uniform in [0, 1), and the
    options are tried from the largest key down. The first one is then picked
    with probability proportional to its form's weight (FORM_WEIGHTS), and
    every option keeps some chance of coming first. The forms a focus targets
    (`targets`) weigh FOCUS_WEIGHT_FACTOR times as much.
    """

    def weight(form: Form) -> float:
        return FORM_WEIGHTS[form] * (FOCUS_WEIGHT_FACTOR if form in targets else 1.0)

    keyed = [(rng.random() ** (1.0 / weight(form)), form, position) for form, position in options]
    keyed.sort(key=lambda item: item[0], reverse=True)
    return [(form, position) for _key, form, position in keyed]


def _choose_numbers(
    rng: random.Random, spec: LevelSpec, form: Form, linked: int | None, position: int | None
) -> _Numbers | None:
    """Numbers for one step, or None if this form and link position cannot work.

    `linked` is the previous answer and `position` (0 or 1) is where it must
    appear among the visible numbers. Both are None for the first step.
    """
    roles = FORMS[form].roles
    min_whole = 100 if spec.requires_three_digit else 2

    if FORMS[form].unknown_role == "whole":
        # Two visible parts; the hidden whole is their sum.
        if linked is None:
            whole = _pick(rng, min_whole, spec.max_value, spec.preferred_min_whole)
            if whole is None:
                return None
            part = rng.randint(1, whole - 1)
            visible = [part, whole - part]
        else:
            other = _pick(
                rng, max(1, min_whole - linked), spec.max_value - linked, spec.preferred_min_part
            )
            if other is None:
                return None
            visible = [other, other]
            visible[position or 0] = linked
        return _Numbers(visible[0], visible[1], visible[0] + visible[1])

    # One visible part and the visible whole; the hidden number is the other part.
    whole_index = roles.index("whole")
    if linked is None:
        whole = _pick(rng, min_whole, spec.max_value, spec.preferred_min_whole)
        part = None if whole is None else _pick(rng, 1, whole - 1, spec.preferred_min_part)
    elif position == whole_index:
        whole = linked if linked >= min_whole else None
        part = None if whole is None else _pick(rng, 1, whole - 1, spec.preferred_min_part)
    else:
        part = linked
        whole = _pick(
            rng, max(linked + 1, min_whole), spec.max_value, max(spec.preferred_min_whole, linked)
        )
    if whole is None or part is None:
        return None
    visible = [part, part]
    visible[whole_index] = whole
    return _Numbers(visible[0], visible[1], whole - part)


def _acceptable(numbers: _Numbers, spec: LevelSpec) -> bool:
    values = (numbers.first, numbers.second, numbers.answer)
    if any(value < 1 or value > spec.max_value for value in values):
        return False
    # The answer may not already be on show: tier-2 hints quote the visible numbers.
    if numbers.answer in (numbers.first, numbers.second):
        return False
    return not spec.requires_three_digit or any(100 <= value <= 999 for value in values)


def _distractors(
    rng: random.Random,
    step: PuzzleStep,
    spec: LevelSpec,
    catalog: MisconceptionCatalog,
    focus: MistakeRule | None = None,
) -> list[Distractor] | None:
    """Three wrong answers for a step, the most diagnosable first.

    0. the focus rule, when the puzzle has a focus
    1. mistake rules with a taxonomy error pattern
    2. the other mistake rules
    3. NEAR_MISS fillers, only if the first two leave a slot empty

    Within tiers 1 and 2 the order is fixed (DISTRACTOR_RULE_ORDER); the
    fillers are picked by the seed.
    """
    chosen: list[Distractor] = []
    used = {step.answer}
    # sorted() is stable, so each tier keeps DISTRACTOR_RULE_ORDER.
    by_tier = sorted(
        DISTRACTOR_RULE_ORDER, key=lambda rule: (rule is not focus, not catalog.is_linked(rule))
    )
    for rule in by_tier:
        if len(chosen) == DISTRACTORS_PER_STEP:
            break
        value = distractor_value(rule, step, spec)
        if value is None or value in used:
            continue
        link = catalog.link_for(rule, spec.primary_topic_id)
        chosen.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)

    if len(chosen) < DISTRACTORS_PER_STEP:
        near = [
            step.answer + sign * offset for offset in spec.near_miss_offsets for sign in (-1, 1)
        ]
        near = [value for value in near if 0 <= value <= spec.max_value and value not in used]
        rng.shuffle(near)
        for value in near[: DISTRACTORS_PER_STEP - len(chosen)]:
            chosen.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
    return chosen if len(chosen) == DISTRACTORS_PER_STEP else None


def _build_step(
    rng: random.Random,
    spec: LevelSpec,
    catalog: MisconceptionCatalog,
    form: Form,
    numbers: _Numbers,
    position: int | None,
    focus: MistakeRule | None = None,
) -> PuzzleStep | None:
    bare = PuzzleStep(
        equation=build_equation(form, numbers.first, numbers.second),
        answer=numbers.answer,
        form=form,
        link_position=position,
        distractors=[],
        hints=build_hints(form, numbers.first, numbers.second, numbers.answer, focus),
    )
    distractors = _distractors(rng, bare, spec, catalog, focus)
    if distractors is None:
        return None
    sources: dict[str, HintSource] = {}
    for distractor in distractors:
        pattern = catalog.get(distractor.error_pattern_id or "")
        if pattern is not None:
            sources[pattern.error_pattern_id] = HintSource(
                error_pattern_id=pattern.error_pattern_id, next_move=pattern.next_move
            )
    return bare.model_copy(
        update={"distractors": distractors, "hint_source": list(sources.values())}
    )


def generate(
    seed: int,
    level: int,
    length: int,
    catalog: MisconceptionCatalog,
    focus: MistakeRule | None = None,
) -> Puzzle:
    """One puzzle for this exact seed. Raises GenerationError if the seed cannot work.

    A `focus` the generator does not act on (levels.supported_focus) is the
    same as no focus.
    """
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}; choose from {sorted(LEVELS)}")
    if not MIN_STEPS <= length <= MAX_STEPS:
        raise ValueError(f"length must be between {MIN_STEPS} and {MAX_STEPS}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")

    spec = LEVELS[level]
    focus = supported_focus(focus)
    targets = FOCUS_TARGET_FORMS.get(focus, frozenset()) if focus else frozenset()
    max_answer_left = answer_left_limit(spec, focus)
    rng = random.Random(seed)
    steps: list[PuzzleStep] = []

    for index in range(length):
        previous = steps[-1] if steps else None
        answer_left_used = sum(step.form in ANSWER_LEFT_FORMS for step in steps)
        answer_left_allowed = max_answer_left is None or answer_left_used < max_answer_left
        # The last step of a longer focused chain must be one the focus does
        # not target, if every step so far was targeted.
        needs_untargeted = (
            bool(targets)
            and length >= FOCUS_UNTARGETED_FROM_LENGTH
            and index == length - 1
            and all(step.form in targets for step in steps)
        )
        options: list[tuple[Form, int | None]] = [
            (form, position)
            for form in ALL_FORMS
            if (previous is None or form != previous.form)
            and (answer_left_allowed or form not in ANSWER_LEFT_FORMS)
            and not (needs_untargeted and form in targets)
            for position in ((None,) if previous is None else (0, 1))
        ]
        options = _weighted_order(rng, options, targets)

        step = None
        for form, position in options:
            # A targeted step is worth more when the mistake has a value to
            # offer. So for a targeted form the numbers are drawn a few times
            # looking for one, and if the linked number makes that impossible
            # where it is, the other place it can go is tried as well. Only if
            # all of that fails is a step without the option accepted.
            # Without a focus this is one draw at one position, as it always was.
            targeted = form in targets
            positions = [position]
            if targeted:
                positions += [p for f, p in options if f == form and p != position]
            without_option = None
            for link_position in positions:
                for _draw in range(FOCUS_NUMBER_DRAWS if targeted else 1):
                    numbers = _choose_numbers(
                        rng, spec, form, previous.answer if previous else None, link_position
                    )
                    if numbers is None or not _acceptable(numbers, spec):
                        continue
                    candidate = _build_step(rng, spec, catalog, form, numbers, link_position, focus)
                    if candidate is None:
                        continue
                    if not targeted or candidate.distractors[0].rule is focus:
                        step = candidate
                        break
                    without_option = without_option or candidate
                if step is not None:
                    break
            step = step or without_option
            if step is not None:
                break
        if step is None:
            raise GenerationError(
                f"seed {seed}, level {level}: no valid step {index + 1} of {length}"
            )
        steps.append(step)

    return Puzzle(
        puzzle_id=make_puzzle_id(
            GENERATOR_VERSION, level, length, seed, FOCUS_CODES[focus] if focus else None
        ),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        steps=steps,
        topic_ids=topic_ids_for(spec, [step.form for step in steps]),
        focus=focus,
    )
