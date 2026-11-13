"""What to play next in Missing Number Chains, and why.

    recommend_from(observations) -> Recommendation

Pure Python, like bkt.py. Every recommendation names the rule that produced
it (reason_code) and says so in a sentence for an adult (reason). Neither is
ever shown to a child.

The rules, in the order they are tried:

    cold_start    no observations yet: level 1, chains of 2
    promote       the current level's primary topic is very likely known at
                  this level, with enough observations here and nearly all
                  of the latest ones right: one level up
    step_down     it is very likely not known, with enough observations at
                  this level: one level down
    consolidate   otherwise stay; the chain grows with confidence

The current level is the level of the latest observation, and every estimate
used is the one for that level (see bkt.py). After any change of level, a few
observations at the new level are required before promote or step_down may
fire again, so a learner does not bounce between two levels. At level 3 there
is nowhere to promote to, and at level 1 nowhere to step down to, so those
rules do not apply there and consolidate decides.

Focus. `focus_rule` names a mistake that keeps coming up. `focus` is the rule
the next puzzle should be generated with, or None:

    - only a rule the generator can target (levels.FOCUS_TARGET_FORMS)
    - at most every other puzzle: if the puzzle played last was focused, the
      next one is not, so a round of five has at most three (the 1st, 3rd, 5th)
    - it switches off by itself: focus_rule goes back to None once the rule
      has not matched often enough in the latest first tries

All of it is worked out from the attempts already stored. A focused puzzle is
recognised by the focus code in its id.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.adaptive.bkt import MasteryKey, Observation, TopicMastery, mastery_from, prior_mastery
from app.adaptive.constants import (
    COLD_START_LENGTH,
    COLD_START_LEVEL,
    CONSOLIDATE_LENGTH_MAX,
    CONSOLIDATE_LENGTHS,
    FOCUS_MIN_MATCHES,
    FOCUS_WINDOW,
    LENGTH_AFTER_LEVEL_CHANGE,
    MAX_LEVEL,
    MIN_LEVEL,
    MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE,
    MIN_OBSERVATIONS_FOR_LEVEL_CHANGE,
    PROMOTE_P_KNOWN,
    PROMOTE_RECENT_CORRECT,
    PROMOTE_RECENT_WINDOW,
    STEP_DOWN_P_KNOWN,
)
from app.puzzles.equations import ALL_FORMS
from app.puzzles.levels import FOCUS_TARGET_FORMS, LEVELS, topic_ids_for

ReasonCode = Literal["cold_start", "promote", "step_down", "consolidate"]


@dataclass(frozen=True)
class Recommendation:
    level: int
    length: int
    reason_code: ReasonCode
    # For an adult reading logs or a future dashboard. Never shown to the child.
    reason: str
    # A mistake rule that keeps coming up, if any.
    focus_rule: str | None = None
    # The rule to generate the next puzzle with, or None. See the module docstring.
    focus: str | None = None
    # Every mastery value behind the decision: all practised (topic, level)
    # pairs, plus the topics of the recommended level (at their prior if the
    # player has never practised them there).
    mastery: dict[MasteryKey, TopicMastery] = field(default_factory=dict)


def primary_topic_id(level: int) -> str:
    return LEVELS[level].primary_topic_id


def level_topic_ids(level: int) -> list[str]:
    """Every topic a puzzle at this level can practise, primary first."""
    return topic_ids_for(LEVELS[level], list(ALL_FORMS))


def consolidate_length(p_known: float) -> int:
    for below, length in CONSOLIDATE_LENGTHS:
        if p_known < below:
            return length
    return CONSOLIDATE_LENGTH_MAX


def find_focus_rule(observations: Sequence[Observation]) -> tuple[str, int] | None:
    """The mistake rule matched most often in the latest first tries, with its count.

    None unless a rule matched at least FOCUS_MIN_MATCHES times. On a tie the
    rule seen most recently wins, so the answer does not depend on dict order.
    """
    recent = observations[-FOCUS_WINDOW:]
    counts: Counter[str] = Counter()
    last_seen: dict[str, int] = {}
    for position, observation in enumerate(recent):
        for rule in observation.matched_rules:
            counts[rule] += 1
            last_seen[rule] = position
    if not counts:
        return None
    rule = max(counts, key=lambda name: (counts[name], last_seen[name], name))
    return (rule, counts[rule]) if counts[rule] >= FOCUS_MIN_MATCHES else None


def focus_for_next_puzzle(
    observations: Sequence[Observation], focus_rule: str | None
) -> str | None:
    """The rule to generate the next puzzle with, or None.

    None when there is no repeated mistake, when the generator cannot target
    it, or when the puzzle the player worked on last was itself focused.
    """
    if focus_rule is None or not observations:
        return None
    targetable = {rule.value for rule in FOCUS_TARGET_FORMS}
    if focus_rule not in targetable or observations[-1].focused:
        return None
    return focus_rule


def _with_level_topics(
    mastery: dict[MasteryKey, TopicMastery], level: int
) -> dict[MasteryKey, TopicMastery]:
    shown = dict(mastery)
    for topic_id in level_topic_ids(level):
        shown.setdefault((topic_id, level), prior_mastery(topic_id, level))
    return shown


def recommend_from(observations: Sequence[Observation]) -> Recommendation:
    """The next level and chain length for a player with these observations (oldest first)."""
    if not observations:
        return Recommendation(
            level=COLD_START_LEVEL,
            length=COLD_START_LENGTH,
            reason_code="cold_start",
            reason=(
                f"No practice recorded yet, so start at level {COLD_START_LEVEL} "
                f"with chains of {COLD_START_LENGTH} steps."
            ),
            mastery=_with_level_topics({}, COLD_START_LEVEL),
        )

    mastery = mastery_from(observations)
    level = observations[-1].level
    primary = primary_topic_id(level)
    known = mastery.get((primary, level), prior_mastery(primary, level))
    here = [o for o in observations if o.level == level]
    at_level = sum(1 for o in here if primary in o.topic_ids)
    recent = here[-PROMOTE_RECENT_WINDOW:]
    recent_right = sum(o.correct for o in recent)

    # How many of the latest observations are at this level in a row. If the
    # level was different before that, the player arrived here by a change.
    run = 0
    for observation in reversed(observations):
        if observation.level != level:
            break
        run += 1
    arrived_by_change = run < len(observations)
    settled = not arrived_by_change or run >= MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE
    enough = at_level >= MIN_OBSERVATIONS_FOR_LEVEL_CHANGE
    on_a_run = len(recent) == PROMOTE_RECENT_WINDOW and recent_right >= PROMOTE_RECENT_CORRECT

    # An estimate is never certain, so it is never printed as 100%.
    likely = "over 99%" if known.p_known > 0.99 else f"{known.p_known:.0%}"
    estimate = f"estimated {likely} likely to know the level {level} topic"
    evidence = f"after {at_level} first tries at this level"

    if settled and enough and on_a_run and known.p_known >= PROMOTE_P_KNOWN and level < MAX_LEVEL:
        new_level, length, code = level + 1, LENGTH_AFTER_LEVEL_CHANGE, "promote"
        reason = (
            f"Doing well: {estimate} {evidence}, with {recent_right} of the last "
            f"{len(recent)} right. Move up to level {new_level}, starting with chains of "
            f"{length} steps."
        )
    elif settled and enough and known.p_known <= STEP_DOWN_P_KNOWN and level > MIN_LEVEL:
        new_level, length, code = level - 1, LENGTH_AFTER_LEVEL_CHANGE, "step_down"
        reason = (
            f"Finding this hard: {estimate} {evidence}. "
            f"Step back to level {new_level}, with chains of {length} steps."
        )
    else:
        new_level, length, code = level, consolidate_length(known.p_known), "consolidate"
        reason = f"Keep practising level {level}: {estimate} {evidence}. Chains of {length} steps."
        if not settled:
            reason += (
                f" The level changed {run} first tries ago; it stays put until there are "
                f"{MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE} at the new level."
            )

    focus = find_focus_rule(observations)
    next_focus = focus_for_next_puzzle(observations, focus[0] if focus else None)
    if focus is not None:
        rule, count = focus
        window = min(FOCUS_WINDOW, len(observations))
        reason += (
            f" The same mistake keeps coming up: {rule} ({count} of the last {window} first tries)."
        )
        if next_focus is not None:
            reason += " The next puzzle targets it."
        elif observations[-1].focused:
            reason += " The last puzzle targeted it, so the next one is an ordinary one."

    return Recommendation(
        level=new_level,
        length=length,
        reason_code=code,
        reason=reason,
        focus_rule=focus[0] if focus else None,
        focus=next_focus,
        mastery=_with_level_topics(mastery, new_level),
    )
