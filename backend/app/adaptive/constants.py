"""Every number the adaptive engine uses, in one place.

THE BKT PARAMETERS ARE PRIORS, NOT FITTED VALUES. They are reasonable
starting guesses for a four-option multiple-choice task, chosen by hand.
Fitting them (for example with expectation-maximisation) needs real attempt
data from real children, which does not exist yet. Until then, treat p_known
as a rough, explainable estimate and not as a measurement. This is an open
item in backend/README.md.

The policy thresholds below are in the same position: sensible defaults,
checked only against the offline simulator (app/adaptive/simulate.py).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BktParams:
    # Prior that the topic is already known before any practice.
    p_init: float = 0.30
    # Chance of learning the topic at each practice opportunity.
    p_learn: float = 0.15
    # Knows it, answers wrong anyway.
    p_slip: float = 0.10
    # Does not know it, answers right anyway: one in four options.
    p_guess: float = 0.25


DEFAULT_BKT = BktParams()
# Per-topic overrides would go here. There are none: nothing has been fitted.
BKT_BY_TOPIC: dict[str, BktParams] = {}


def bkt_params(topic_id: str) -> BktParams:
    return BKT_BY_TOPIC.get(topic_id, DEFAULT_BKT)


# ---- evidence ----

# Only this try at a step is an observation. Retries are not independent evidence.
EVIDENCE_ATTEMPT_ON_STEP = 1
# A first try made after a hint of this tier or higher counts as incorrect:
# tier 2 gives the strategy and tier 3 the worked step. Tier 1 only recalls
# what the equals sign means, and leaves the observation as it is.
HINT_TIER_COUNTS_AS_INCORRECT = 2
# Mastery is replayed from at most this many of the latest observations per
# topic and level.
MAX_OBSERVATIONS_PER_TOPIC = 200

# ---- recommendation policy (missing-number) ----

MIN_LEVEL = 1
MAX_LEVEL = 3

COLD_START_LEVEL = 1
COLD_START_LENGTH = 2

# Move up when the level's primary topic is at least this likely to be known
# at this level (0.95 is the usual BKT mastery threshold)...
PROMOTE_P_KNOWN = 0.95
# ...and at least this many of the latest first tries at this level were right.
# P(known) alone follows the last two or three answers too closely.
PROMOTE_RECENT_WINDOW = 6
PROMOTE_RECENT_CORRECT = 5
# Move down when it is at most this likely.
STEP_DOWN_P_KNOWN = 0.35
# Both need this many observations at the current level.
MIN_OBSERVATIONS_FOR_LEVEL_CHANGE = 6
# After any change of level, this many observations at the new level must come
# in before the level may change again. Stops a learner bouncing between two.
MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE = 4
# The chain length right after a level change, and at a cold start.
LENGTH_AFTER_LEVEL_CHANGE = 2

# Staying at a level: the chain grows with confidence.
# p_known below the first number: 2 steps; below the second: 3; otherwise 4.
CONSOLIDATE_LENGTHS: tuple[tuple[float, int], ...] = ((0.5, 2), (0.7, 3))
CONSOLIDATE_LENGTH_MAX = 4

# A mistake rule matched this many times in the last so-many first tries is
# reported as focus_rule. Information only: nothing acts on it yet.
FOCUS_WINDOW = 8
FOCUS_MIN_MATCHES = 2
