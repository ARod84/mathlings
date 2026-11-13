"""Builds a "Next in Line" puzzle from a seed. Reproducible, and nothing else.

    generate(seed, level, catalog) -> SequencePuzzle

The same inputs and GENERATOR_VERSION always give the same puzzle: all
randomness comes from one local random.Random(seed). Bump GENERATOR_VERSION in
levels.py whenever a change here (or in rules, hints or levels) can alter the
output for an existing seed.

This module does not check its own work, and it does not reason about which
rules fit a row of numbers: verifier.py does that, separately, and
generate_verified (app/puzzles/core/verified.py) puts the two together. A seed
that cannot be completed raises GenerationError.

How a puzzle is built: pick the kind of sequence the level allows, its length,
its step (and growth), and a first term that keeps every term inside the
level's range. Then pick where the blanks go, from the places the level
allows (levels.py: never the first term, enough visible terms in a row, and
at a through-zero level at least one blank below zero). A blank whose answer
the second hint would have to quote is not used. Each blank then gets its
three wrong options and its hints.
"""

import random
from itertools import combinations

from app.puzzles.core import GenerationError
from app.puzzles.core.ids import MAX_SEED
from app.puzzles.types.sequences.hints import build_hints, quoted_numbers
from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import (
    DISTRACTORS_PER_STEP,
    EVIDENCE,
    GENERATOR_VERSION,
    LEVELS,
    MAX_TERMS,
    MIN_TERMS,
    Kind,
    LevelSpec,
    longest_visible_run,
    step_topic_ids,
)
from app.puzzles.types.sequences.misconceptions import SequenceCatalog
from app.puzzles.types.sequences.models import (
    Distractor,
    HintSource,
    MistakeRule,
    SequencePuzzle,
    SequenceStep,
)
from app.puzzles.types.sequences.rules import distractor_value

# The order mistake rules are tried in within a tier. _distractors puts the
# rules that have a taxonomy error pattern ahead of the ones that do not.
DISTRACTOR_RULE_ORDER: tuple[MistakeRule, ...] = (
    MistakeRule.STOPS_AT_ZERO,
    MistakeRule.SIGN_DROPPED,
    MistakeRule.WRONG_DIRECTION,
    MistakeRule.BOUNDARY_SLIP,
    MistakeRule.CONSTANT_GAP,
    MistakeRule.COUNT_BY_ONE,
    MistakeRule.SKIPPED_TERM,
    MistakeRule.OFF_BY_ONE_OVER,
    MistakeRule.OFF_BY_ONE_UNDER,
)
# How often a counting sequence starts on a multiple of its step (0, 5, 10, …
# and not 3, 8, 13, …), and how often a through-zero sequence lands on zero
# on its way down. Preferences: both sorts are valid, and both are made.
START_ON_MULTIPLE = 0.6
LAND_ON_ZERO = 0.5


def _constant_terms(rng: random.Random, spec: LevelSpec, length: int) -> list[int] | None:
    step = rng.choice(spec.steps)
    span = step * (length - 1)
    if spec.through_zero:
        # Down from above zero to below it: the first term is at least 1, the
        # last at most −1 and no lower than the level's minimum.
        on_zero = [k * step for k in range(1, length - 1) if k * step - span >= spec.min_value]
        if on_zero and rng.random() < LAND_ON_ZERO:
            first = rng.choice(on_zero)
        else:
            low, high = max(1, span + spec.min_value), min(spec.max_value, span - 1)
            if low > high:
                return None
            first = rng.randint(low, high)
        return [first - step * index for index in range(length)]

    directions = [
        up for up, allowed in ((True, spec.may_go_up), (False, spec.may_go_down)) if allowed
    ]
    goes_up = rng.choice(directions)
    highest_start = spec.max_value - span
    if highest_start < spec.min_value:
        return None
    multiples = range(-(-spec.min_value // step), highest_start // step + 1)
    if multiples and rng.random() < START_ON_MULTIPLE:
        lowest = rng.choice(multiples) * step
    else:
        lowest = rng.randint(spec.min_value, highest_start)
    terms = [lowest + step * index for index in range(length)]
    return terms if goes_up else terms[::-1]


def _growing_terms(rng: random.Random, spec: LevelSpec, length: int) -> list[int] | None:
    growth = rng.choice(spec.growths)
    step = rng.randint(1, spec.preferred_first_step_max)
    terms = [rng.randint(max(0, spec.min_value), spec.preferred_start_max)]
    for _ in range(length - 1):
        terms.append(terms[-1] + step)
        step += growth
    return terms if terms[-1] <= spec.max_value else None


def _blank_choices(spec: LevelSpec, kind: Kind, terms: list[int]) -> list[tuple[int, ...]]:
    """Every set of blanks the level allows for this sequence, smallest sets first."""
    length = len(terms)
    if spec.blank_at_end_only:
        candidates: list[tuple[int, ...]] = [(length - 1,)]
    else:
        # Never the first term.
        candidates = [
            blanks
            for count in range(1, spec.max_blanks + 1)
            for blanks in combinations(range(1, length), count)
        ]
    return [
        blanks
        for blanks in candidates
        if longest_visible_run(length, blanks) >= EVIDENCE[kind]
        and (not spec.through_zero or kind != "constant" or any(terms[p] < 0 for p in blanks))
        # The second hint quotes these; the answer may not be one of them.
        and all(terms[p] not in quoted_numbers(terms, p, kind) for p in blanks)
    ]


def _distractors(
    rng: random.Random,
    spec: LevelSpec,
    catalog: SequenceCatalog,
    kind: Kind,
    terms: list[int],
    position: int,
) -> list[Distractor] | None:
    """Three wrong answers for a blank, the most diagnosable first.

    1. mistake rules with a taxonomy error pattern
    2. the other mistake rules
    3. NEAR_MISS fillers, only if the first two leave a slot empty

    Within tiers 1 and 2 the order is fixed (DISTRACTOR_RULE_ORDER); the
    fillers are picked by the seed.
    """
    answer = terms[position]
    primary_topic_id = spec.topic_ids[kind][0]
    chosen: list[Distractor] = []
    used = {answer}
    # sorted() is stable, so each tier keeps DISTRACTOR_RULE_ORDER.
    for rule in sorted(DISTRACTOR_RULE_ORDER, key=lambda rule: not catalog.is_linked(rule)):
        if len(chosen) == DISTRACTORS_PER_STEP:
            break
        value = distractor_value(rule, terms, position, kind, spec)
        if value is None or value in used:
            continue
        link = catalog.link_for(rule, primary_topic_id)
        chosen.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)

    if len(chosen) < DISTRACTORS_PER_STEP:
        near = [answer + sign * offset for offset in spec.near_miss_offsets for sign in (-1, 1)]
        near = [
            value
            for value in near
            if spec.min_value <= value <= spec.max_value and value not in used
        ]
        rng.shuffle(near)
        for value in near[: DISTRACTORS_PER_STEP - len(chosen)]:
            chosen.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
    return chosen if len(chosen) == DISTRACTORS_PER_STEP else None


def _build_step(
    rng: random.Random,
    spec: LevelSpec,
    catalog: SequenceCatalog,
    kind: Kind,
    terms: list[int],
    position: int,
) -> SequenceStep | None:
    distractors = _distractors(rng, spec, catalog, kind, terms, position)
    if distractors is None:
        return None
    sources: dict[str, HintSource] = {}
    for distractor in distractors:
        pattern = catalog.get(distractor.error_pattern_id or "")
        if pattern is not None:
            sources[pattern.error_pattern_id] = HintSource(
                error_pattern_id=pattern.error_pattern_id, next_move=pattern.next_move
            )
    return SequenceStep(
        position=position,
        answer=terms[position],
        distractors=distractors,
        hints=build_hints(terms, position, kind),
        hint_source=list(sources.values()),
    )


def generate(seed: int, level: int, catalog: SequenceCatalog) -> SequencePuzzle:
    """One puzzle for this exact seed. Raises GenerationError if the seed cannot work."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}; choose from {sorted(LEVELS)}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")

    spec = LEVELS[level]
    rng = random.Random(seed)
    kind: Kind = rng.choice(spec.kinds)
    length = rng.randint(MIN_TERMS, MAX_TERMS)
    terms = (
        _constant_terms(rng, spec, length)
        if kind == "constant"
        else _growing_terms(rng, spec, length)
    )
    if terms is None:
        raise GenerationError(f"seed {seed}, level {level}: the sequence does not fit the range")

    choices = _blank_choices(spec, kind, terms)
    if not choices:
        raise GenerationError(f"seed {seed}, level {level}: no place for a blank in {terms}")
    # One blank or two with the same chance, where the sequence allows both.
    count = rng.choice(sorted({len(blanks) for blanks in choices}))
    blanks = rng.choice([blanks for blanks in choices if len(blanks) == count])

    steps: list[SequenceStep] = []
    for position in blanks:
        step = _build_step(rng, spec, catalog, kind, terms, position)
        if step is None:
            raise GenerationError(
                f"seed {seed}, level {level}: not enough wrong options for {terms[position]}"
            )
        steps.append(step)

    return SequencePuzzle(
        puzzle_id=make_sequence_id(GENERATOR_VERSION, level, seed),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        kind=kind,
        terms=terms,
        steps=steps,
        topic_ids=step_topic_ids(level, kind),
    )
