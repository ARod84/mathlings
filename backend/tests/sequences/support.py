"""Helpers for the sequence tests: a catalog that needs no database, and hand-built puzzles."""

from app.puzzles.types.sequences.hints import build_hints
from app.puzzles.types.sequences.ids import make_sequence_id
from app.puzzles.types.sequences.levels import (
    GENERATOR_VERSION,
    LEVELS,
    TOPIC_GENERALISING,
    TOPIC_GROWING_PATTERNS,
    TOPIC_LINEAR_SEQUENCES,
    TOPIC_NEGATIVE_NUMBERS,
    TOPIC_SKIP_COUNTING,
    Kind,
    step_topic_ids,
)
from app.puzzles.types.sequences.misconceptions import SequenceCatalog, resolve_catalog
from app.puzzles.types.sequences.models import (
    Distractor,
    MistakeRule,
    SequencePuzzle,
    SequenceStep,
)
from app.puzzles.types.sequences.rules import distractor_value
from app.taxonomy.schemas import ErrorPatternOut
from tests.puzzles.support import _row

TOPIC_TEMPERATURE = "mt_RVK655t391"
TOPIC_COUNTING_1000 = "mt_M2v1A9OEuM"
TOPIC_COUNTING_IN_2S = "mt_nvdpxAJTBG"
TOPIC_SHAPE_PATTERNS = "mt_A-FyLLLLzy"
TOPIC_WITHIN_20 = "mt_m1W6nTQJ2b"

KNOWN_TOPICS = {
    TOPIC_GROWING_PATTERNS,
    TOPIC_SKIP_COUNTING,
    TOPIC_LINEAR_SEQUENCES,
    TOPIC_NEGATIVE_NUMBERS,
    TOPIC_GENERALISING,
    TOPIC_TEMPERATURE,
    TOPIC_COUNTING_1000,
    TOPIC_COUNTING_IN_2S,
    TOPIC_SHAPE_PATTERNS,
    TOPIC_WITHIN_20,
}

# The opening words and the positions are copied from the real taxonomy rows
# (pinned commit). Every pattern of each topic is here, in order.
ERROR_PATTERN_ROWS: dict[str, list[ErrorPatternOut]] = {
    TOPIC_SKIP_COUNTING: [
        _row(
            0,
            "sub-counts by smaller steps — builds the 8s by counting on in 4s (or ones)",
            TOPIC_COUNTING_IN_2S,
            "use number-line jumps of 8",
        ),
        _row(1, "no link between 4s and 8s", None, "ring every other one"),
        _row(
            2,
            "50s/100s digit slip — loses place in the 50s (…, 450, 500, 550)",
            None,
            "rehearse the …950, 1000 bridge",
        ),
    ],
    TOPIC_LINEAR_SEQUENCES: [
        _row(
            0,
            "Thinks the sequence 'stops' at zero — that you cannot go below zero",
            TOPIC_TEMPERATURE,
            "Confront with a temperature scale and keep the equal hop going.",
        ),
        _row(
            1,
            "Reads or writes the negative sign wrongly — records the term as 1 instead of −1",
            None,
            "Show the raised minus for a negative number.",
        ),
        _row(2, "States the rule vaguely — 'it goes down'", None, "Require the form."),
        _row(3, "Fixates on the last term", TOPIC_SHAPE_PATTERNS, "Check EVERY pair."),
        _row(
            4,
            "Treats a decreasing sequence as a different kind, continuing it upward",
            None,
            "Frame decreasing as 'adding a negative each time'.",
        ),
    ],
    TOPIC_NEGATIVE_NUMBERS: [
        _row(0, "Orders negatives by magnitude", None, "Walk both on a number line."),
        _row(
            1,
            "Numbers stop at (or bounce off) zero — after 0 the child says 1 again",
            TOPIC_COUNTING_1000,
            "Extend the number line below zero.",
        ),
        _row(2, "Zero-as-smallest", None, "Use a context that goes below zero."),
    ],
    TOPIC_GENERALISING: [
        _row(0, "Recomputes 6+7 from one", TOPIC_WITHIN_20, "Put 6+6 and 6+7 side by side."),
        _row(1, "Applies the near-double adjustment wrongly", None, "Scaffold."),
        _row(
            2,
            "States a sequence rule from one or two cases and assumes it holds",
            None,
            "Ask 'how could we be sure? test the next one'.",
        ),
    ],
}

# Where the prerequisite graph steps back to, for a topic whose pattern names nowhere.
STEP_BACK = {
    TOPIC_GROWING_PATTERNS: TOPIC_COUNTING_IN_2S,
    TOPIC_SKIP_COUNTING: TOPIC_COUNTING_IN_2S,
    TOPIC_LINEAR_SEQUENCES: TOPIC_NEGATIVE_NUMBERS,
    TOPIC_GENERALISING: TOPIC_WITHIN_20,
}


def make_catalog() -> SequenceCatalog:
    return resolve_catalog(lambda topic_id: ERROR_PATTERN_ROWS[topic_id])


def topic_exists(topic_id: str) -> bool:
    return topic_id in KNOWN_TOPICS


def step_back(topic_id: str) -> str | None:
    return STEP_BACK.get(topic_id)


# Linked rules first, then the rest: the order options are filled in.
_RULE_ORDER = (
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


def make_step(terms: list[int], position: int, *, level: int, kind: Kind) -> SequenceStep:
    """A blank with valid hints and distractors, built by hand from the whole sequence."""
    spec = LEVELS[level]
    catalog = make_catalog()
    answer = terms[position]
    distractors: list[Distractor] = []
    used = {answer}
    for rule in _RULE_ORDER:
        value = distractor_value(rule, terms, position, kind, spec)
        if value is None or value in used or len(distractors) == 3:
            continue
        link = catalog.link_for(rule, spec.topic_ids[kind][0])
        distractors.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)
    for offset in spec.near_miss_offsets:
        for value in (answer + offset, answer - offset):
            if (
                len(distractors) < 3
                and spec.min_value <= value <= spec.max_value
                and value not in used
            ):
                distractors.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
                used.add(value)
    return SequenceStep(
        position=position,
        answer=answer,
        distractors=distractors,
        hints=build_hints(terms, position, kind),
    )


def make_puzzle(
    terms: list[int],
    blanks: list[int],
    *,
    level: int,
    kind: Kind = "constant",
    seed: int = 7,
) -> SequencePuzzle:
    """A puzzle written by hand: the whole row, and which terms are blank."""
    return SequencePuzzle(
        puzzle_id=make_sequence_id(GENERATOR_VERSION, level, seed),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        kind=kind,
        terms=terms,
        steps=[make_step(terms, position, level=level, kind=kind) for position in blanks],
        topic_ids=step_topic_ids(level, kind),
    )
