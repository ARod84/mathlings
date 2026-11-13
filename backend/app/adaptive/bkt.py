"""Bayesian Knowledge Tracing, and the rules for what counts as an observation.

Pure Python: no database, no web framework. Everything here works on plain
values, so the API and the offline simulator run exactly the same code.

BKT keeps one number, P(known), per topic AND level. Each observation moves
it in two steps: first Bayes' rule on the answer (a right answer may be a
guess, a wrong one may be a slip), then the chance that the child learned the
topic from that practice.

Why per level: levels 1 and 2 practise the same topic with bigger numbers.
With one shared estimate, confidence earned at level 1 made the first wrong
answers at level 2 look like slips, and it took seven in a row to step back
down. So a step at level 1 updates only the level 1 estimate.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.adaptive.constants import (
    EVIDENCE_ATTEMPT_ON_STEP,
    HINT_TIER_COUNTS_AS_INCORRECT,
    MAX_OBSERVATIONS_PER_TOPIC,
    BktParams,
    bkt_params,
)

# (topic id, level): what one estimate is about.
MasteryKey = tuple[str, int]


@dataclass(frozen=True)
class Observation:
    """One first try at one step, after the evidence rules."""

    level: int
    topic_ids: tuple[str, ...]
    correct: bool
    # Mistake rules the answer matched; empty when right or unrecognized.
    matched_rules: tuple[str, ...] = ()
    at: datetime | None = None


@dataclass(frozen=True)
class TopicMastery:
    topic_id: str
    level: int
    p_known: float
    observations: int
    last_practised: datetime | None


def to_observation(
    *,
    attempt_on_step: int,
    hint_tier_before: int,
    correct: bool,
    level: int,
    topic_ids: Iterable[str],
    matched_rules: Iterable[str] = (),
    at: datetime | None = None,
) -> Observation | None:
    """Turn one stored attempt into an observation, or None if it is not evidence.

    - Only the first try at a step counts. A retry after a wrong answer is not
      independent evidence: the child has just been told the first one was wrong.
    - A first try made after a strategy hint or the worked step (tier 2 or 3)
      counts as incorrect, whatever the answer. A tier 1 hint changes nothing.
    """
    if attempt_on_step != EVIDENCE_ATTEMPT_ON_STEP:
        return None
    unaided = hint_tier_before < HINT_TIER_COUNTS_AS_INCORRECT
    return Observation(
        level=level,
        topic_ids=tuple(topic_ids),
        correct=correct and unaided,
        matched_rules=tuple(matched_rules),
        at=at,
    )


def posterior(p_known: float, correct: bool, params: BktParams) -> float:
    """P(known) given the answer alone, before any learning."""
    if correct:
        knew = p_known * (1 - params.p_slip)
        did_not = (1 - p_known) * params.p_guess
    else:
        knew = p_known * params.p_slip
        did_not = (1 - p_known) * (1 - params.p_guess)
    return knew / (knew + did_not)


def update(p_known: float, correct: bool, params: BktParams) -> float:
    """P(known) after one observation: Bayes on the answer, then the chance of learning."""
    after_answer = posterior(p_known, correct, params)
    return after_answer + (1 - after_answer) * params.p_learn


def mastery_from(observations: Sequence[Observation]) -> dict[MasteryKey, TopicMastery]:
    """Replay observations (oldest first) into P(known) per topic and level.

    An observation counts for every topic of its step, at its own level only.
    Per topic and level, only the latest MAX_OBSERVATIONS_PER_TOPIC are
    replayed, starting from the prior.
    """
    by_key: dict[MasteryKey, list[Observation]] = {}
    for observation in observations:
        for topic_id in observation.topic_ids:
            by_key.setdefault((topic_id, observation.level), []).append(observation)

    result: dict[MasteryKey, TopicMastery] = {}
    for (topic_id, level), seen in by_key.items():
        params = bkt_params(topic_id)
        recent = seen[-MAX_OBSERVATIONS_PER_TOPIC:]
        p_known = params.p_init
        for observation in recent:
            p_known = update(p_known, observation.correct, params)
        result[(topic_id, level)] = TopicMastery(
            topic_id=topic_id,
            level=level,
            p_known=p_known,
            observations=len(recent),
            last_practised=recent[-1].at,
        )
    return result


def prior_mastery(topic_id: str, level: int) -> TopicMastery:
    """What is assumed about a topic nobody has practised at this level yet."""
    return TopicMastery(
        topic_id=topic_id,
        level=level,
        p_known=bkt_params(topic_id).p_init,
        observations=0,
        last_practised=None,
    )
