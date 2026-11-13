"""Offline check of the adaptive engine on made-up learners.

    uv run python -m app.adaptive.simulate --learners 500 --steps 120 --seed 1

Each synthetic learner plays through the real loop, in memory and without
HTTP: recommend -> generate a verified puzzle -> answer its steps -> the
answers go through the same evidence rules as stored attempts -> recommend
again. The same seed always gives the same report.

WHAT THIS CAN AND CANNOT SHOW. The learners are a model written by hand, not
children. The run shows that the policy behaves sensibly on learners who
behave the way the model says: strong ones move up, weak ones are not pushed,
nobody bounces around. It says nothing about whether real children behave
that way, and it does not validate the BKT parameters.

The learner model
    - A hidden true skill per level, between 0 and 1: the chance that the
      learner really knows how to do a step at that level.
    - Knows it: answers right unless they slip. Does not know it: sometimes
      asks for the strategy hint first, then guesses among the four options.
    - Every step practised raises the skill at that level by learn_rate of
      what is missing, the levels below it by the same, and the levels above
      it by TRANSFER of that.
    - The "add_visible" kind, when wrong, picks the option that comes from
      adding the two visible numbers whenever the step offers it.
"""

import argparse
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlmodel import Session

from app.adaptive.bkt import Observation, to_observation
from app.adaptive.constants import DEFAULT_BKT, MAX_LEVEL
from app.adaptive.policy import recommend_from
from app.db import make_engine
from app.puzzles.diagnoser import diagnose
from app.puzzles.ids import MAX_SEED
from app.puzzles.levels import GENERATOR_VERSION, step_topic_ids
from app.puzzles.misconceptions import MisconceptionCatalog
from app.puzzles.models import MistakeRule, Puzzle
from app.puzzles.taxonomy_link import load_catalog, topic_exists
from app.puzzles.verified import generate_verified
from app.taxonomy.service import TaxonomyService, reload_graph

# Practising a level also helps the levels above it, at this share of the rate.
TRANSFER = 0.5
# A learner who does not know a step asks for the strategy hint (tier 2) first this often.
HINT_WHEN_STUCK = 0.15
# Anyone may glance at the tier 1 reminder; it must not change the evidence.
TIER_ONE_HINT = 0.05

# Targets from the task that asked for this simulator.
TRUE_SKILL_FOR_PROMOTION = 0.6
FALSE_PROMOTION_TARGET = 5.0
STUCK_AFTER_STEPS = 40
STUCK_TARGET = 5.0
FOCUS_WITHIN_STEPS = 30


@dataclass(frozen=True)
class LearnerKind:
    name: str
    # (low, high) of the starting true skill, per level 1, 2, 3.
    start: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    learn_rate: tuple[float, float]
    slip: float = 0.08
    guess: float = 0.25
    picks_add_visible: bool = False


KINDS: tuple[LearnerKind, ...] = (
    LearnerKind("fast", ((0.30, 0.55), (0.15, 0.35), (0.05, 0.20)), (0.06, 0.10)),
    LearnerKind("slow", ((0.15, 0.40), (0.05, 0.20), (0.00, 0.10)), (0.010, 0.025)),
    LearnerKind("strong", ((0.90, 0.98), (0.85, 0.95), (0.75, 0.92)), (0.03, 0.06)),
    LearnerKind(
        "add_visible",
        ((0.20, 0.40), (0.10, 0.25), (0.00, 0.10)),
        (0.010, 0.020),
        picks_add_visible=True,
    ),
)


@dataclass
class Learner:
    kind: LearnerKind
    skill: dict[int, float]
    learn_rate: float

    def practise(self, level: int) -> None:
        for other in self.skill:
            rate = self.learn_rate if other <= level else self.learn_rate * TRANSFER
            self.skill[other] += rate * (1 - self.skill[other])


@dataclass
class LearnerResult:
    kind: str
    steps_to_level_3: int | None = None
    level_changes: int = 0
    promotions: int = 0
    false_promotions: int = 0
    level_after_stuck_window: int = 1
    focus_flagged_at: int | None = None
    final_level: int = 1
    levels_played: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class KindReport:
    kind: str
    learners: int
    reached_level_3_percent: float
    average_steps_to_level_3: float | None
    false_promotion_percent: float
    promotions: int
    false_promotions: int
    stuck_at_level_1_percent: float
    average_level_changes: float
    max_level_changes: int
    focus_flagged_percent: float


@dataclass(frozen=True)
class SimulationReport:
    learners: int
    steps: int
    seed: int
    kinds: tuple[KindReport, ...]
    # Over every learner: promoted at least once while the true skill at the
    # level they were leaving was below TRUE_SKILL_FOR_PROMOTION.
    false_promotion_percent: float
    # Every promote decision, and how many of them were false by the same test.
    promotions: int
    false_promotions: int
    # Strong learners still recommended level 1 after STUCK_AFTER_STEPS steps.
    strong_stuck_percent: float
    # add_visible learners whose focus_rule was ADD_VISIBLE within FOCUS_WITHIN_STEPS steps.
    focus_flagged_percent: float
    average_level_changes: float

    @property
    def false_promotion_decision_percent(self) -> float:
        return _percent(self.false_promotions, self.promotions)

    @property
    def targets_met(self) -> bool:
        return (
            self.false_promotion_percent <= FALSE_PROMOTION_TARGET
            and self.strong_stuck_percent <= STUCK_TARGET
        )

    def format(self) -> str:
        bkt = DEFAULT_BKT
        lines = [
            f"Adaptive simulation: {self.learners} learners, {self.steps} steps each, "
            f"seed {self.seed}, generator version {GENERATOR_VERSION}",
            f"BKT priors: p_init {bkt.p_init}, p_learn {bkt.p_learn}, "
            f"p_slip {bkt.p_slip}, p_guess {bkt.p_guess}",
            "",
            f"{'kind':<12}{'n':>5}{'reached L3':>12}{'avg steps to L3':>17}"
            f"{'false promo':>13}{'false/all promotions':>22}{'stuck at L1':>13}"
            f"{'level changes':>15}{'max':>5}{'focus flagged':>15}",
        ]
        for kind in self.kinds:
            steps = (
                "-"
                if kind.average_steps_to_level_3 is None
                else f"{kind.average_steps_to_level_3:.1f}"
            )
            lines.append(
                f"{kind.kind:<12}{kind.learners:>5}{kind.reached_level_3_percent:>11.1f}%"
                f"{steps:>17}{kind.false_promotion_percent:>12.1f}%"
                f"{f'{kind.false_promotions}/{kind.promotions}':>22}"
                f"{kind.stuck_at_level_1_percent:>12.1f}%{kind.average_level_changes:>15.2f}"
                f"{kind.max_level_changes:>5}{kind.focus_flagged_percent:>14.1f}%"
            )

        def verdict(value: float, target: float) -> str:
            return "ok" if value <= target else "TARGET MISSED"

        lines += [
            "",
            f"False promotions (ever promoted with true skill below {TRUE_SKILL_FOR_PROMOTION}): "
            f"{self.false_promotion_percent:.1f}% of all learners "
            f"(target <= {FALSE_PROMOTION_TARGET:.0f}%: "
            f"{verdict(self.false_promotion_percent, FALSE_PROMOTION_TARGET)})",
            f"Promotion decisions that were false: {self.false_promotions} of "
            f"{self.promotions} ({self.false_promotion_decision_percent:.1f}%)",
            f"Strong learners still at level 1 after {STUCK_AFTER_STEPS} steps: "
            f"{self.strong_stuck_percent:.1f}% (target <= {STUCK_TARGET:.0f}%: "
            f"{verdict(self.strong_stuck_percent, STUCK_TARGET)})",
            f"Level changes per learner, all kinds: {self.average_level_changes:.2f}",
            f"add_visible learners with focus_rule ADD_VISIBLE within {FOCUS_WITHIN_STEPS} steps: "
            f"{self.focus_flagged_percent:.1f}%",
        ]
        return "\n".join(lines)


def make_learner(kind: LearnerKind, rng: random.Random) -> Learner:
    return Learner(
        kind=kind,
        skill={level: rng.uniform(*kind.start[level - 1]) for level in (1, 2, 3)},
        learn_rate=rng.uniform(*kind.learn_rate),
    )


def answer_step(
    learner: Learner,
    puzzle: Puzzle,
    step_index: int,
    rng: random.Random,
    catalog: MisconceptionCatalog,
) -> list[Observation]:
    """Play one step the way the learner would; return what counts as evidence.

    Builds the same facts an attempt row holds (which try, hint tier before,
    right or wrong, matched rules) and passes them through to_observation,
    the function the API uses. A wrong first try is followed by a retry,
    which to_observation must drop.
    """
    step = puzzle.steps[step_index]
    kind = learner.kind
    knows = rng.random() < learner.skill[puzzle.level]

    hint_tier = 0
    if not knows and rng.random() < HINT_WHEN_STUCK:
        hint_tier = 2
    elif rng.random() < TIER_ONE_HINT:
        hint_tier = 1

    correct = rng.random() >= kind.slip if knows else rng.random() < kind.guess
    if correct:
        answer = step.answer
    else:
        from_adding = [d for d in step.distractors if d.rule is MistakeRule.ADD_VISIBLE]
        chosen = (
            from_adding[0]
            if kind.picks_add_visible and from_adding and not knows
            else rng.choice(step.distractors)
        )
        answer = chosen.value

    diagnosis = diagnose(puzzle, step_index, answer, catalog=catalog, step_back=lambda _topic: None)
    tries = [(1, hint_tier, diagnosis.correct, [rule.value for rule in diagnosis.matched_rules])]
    if not diagnosis.correct:
        tries.append((2, hint_tier, True, []))

    observations = []
    for attempt_on_step, tier, was_correct, rules in tries:
        observation = to_observation(
            attempt_on_step=attempt_on_step,
            hint_tier_before=tier,
            correct=was_correct,
            level=puzzle.level,
            topic_ids=step_topic_ids(puzzle.level, step.form),
            matched_rules=rules,
        )
        if observation is not None:
            observations.append(observation)
    learner.practise(puzzle.level)
    return observations


def simulate_learner(
    learner: Learner,
    steps: int,
    rng: random.Random,
    catalog: MisconceptionCatalog,
    exists: Callable[[str], bool],
) -> LearnerResult:
    result = LearnerResult(kind=learner.kind.name)
    observations: list[Observation] = []
    previous_level: int | None = None

    while len(observations) < steps:
        recommendation = recommend_from(observations)
        done = len(observations)
        if (
            recommendation.focus_rule == MistakeRule.ADD_VISIBLE.value
            and result.focus_flagged_at is None
        ):
            result.focus_flagged_at = done
        if done <= STUCK_AFTER_STEPS:
            result.level_after_stuck_window = recommendation.level
        if recommendation.reason_code == "promote":
            leaving = recommendation.level - 1
            result.promotions += 1
            if learner.skill[leaving] < TRUE_SKILL_FOR_PROMOTION:
                result.false_promotions += 1

        level = recommendation.level
        if previous_level is not None and level != previous_level:
            result.level_changes += 1
        previous_level = level
        result.levels_played.append(level)
        if level == MAX_LEVEL and result.steps_to_level_3 is None:
            result.steps_to_level_3 = done

        puzzle = generate_verified(
            rng.randrange(MAX_SEED + 1),
            level,
            recommendation.length,
            catalog=catalog,
            topic_exists=exists,
        )
        for step_index in range(len(puzzle.steps)):
            observations.extend(answer_step(learner, puzzle, step_index, rng, catalog))
            if len(observations) >= steps:
                break

    result.final_level = previous_level or 1
    return result


def _percent(part: int, whole: int) -> float:
    return 100 * part / whole if whole else 0.0


def run_simulation(
    learners: int,
    steps: int,
    seed: int,
    *,
    catalog: MisconceptionCatalog,
    topic_exists: Callable[[str], bool],
) -> SimulationReport:
    """Simulate `learners` learners, the kinds in turn, for `steps` first tries each."""
    results: list[LearnerResult] = []
    for index in range(learners):
        # One generator per learner, so adding learners never changes earlier ones.
        rng = random.Random(f"{seed}:{index}")
        learner = make_learner(KINDS[index % len(KINDS)], rng)
        results.append(simulate_learner(learner, steps, rng, catalog, topic_exists))

    kinds = []
    for kind in KINDS:
        mine = [r for r in results if r.kind == kind.name]
        reached = [r.steps_to_level_3 for r in mine if r.steps_to_level_3 is not None]
        kinds.append(
            KindReport(
                kind=kind.name,
                learners=len(mine),
                reached_level_3_percent=_percent(len(reached), len(mine)),
                average_steps_to_level_3=sum(reached) / len(reached) if reached else None,
                false_promotion_percent=_percent(
                    sum(r.false_promotions > 0 for r in mine), len(mine)
                ),
                promotions=sum(r.promotions for r in mine),
                false_promotions=sum(r.false_promotions for r in mine),
                stuck_at_level_1_percent=_percent(
                    sum(r.level_after_stuck_window == 1 for r in mine), len(mine)
                ),
                average_level_changes=(
                    sum(r.level_changes for r in mine) / len(mine) if mine else 0.0
                ),
                max_level_changes=max((r.level_changes for r in mine), default=0),
                focus_flagged_percent=_percent(
                    sum(
                        r.focus_flagged_at is not None and r.focus_flagged_at <= FOCUS_WITHIN_STEPS
                        for r in mine
                    ),
                    len(mine),
                ),
            )
        )

    by_kind = {kind.kind: kind for kind in kinds}
    return SimulationReport(
        learners=learners,
        steps=steps,
        seed=seed,
        kinds=tuple(kinds),
        false_promotion_percent=_percent(
            sum(r.false_promotions > 0 for r in results), len(results)
        ),
        promotions=sum(r.promotions for r in results),
        false_promotions=sum(r.false_promotions for r in results),
        strong_stuck_percent=by_kind["strong"].stuck_at_level_1_percent,
        focus_flagged_percent=by_kind["add_visible"].focus_flagged_percent,
        average_level_changes=(
            sum(r.level_changes for r in results) / len(results) if results else 0.0
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--learners", type=int, default=500)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    # The puzzles need the mistake-rule catalog, which is resolved against the
    # imported taxonomy. That is the only thing read from the database.
    with Session(make_engine()) as session:
        graph = reload_graph(session)
        service = TaxonomyService(session, graph)
        catalog = load_catalog(service)
        exists = topic_exists(service)

    report = run_simulation(
        args.learners, args.steps, args.seed, catalog=catalog, topic_exists=exists
    )
    print(report.format())
    return 0 if report.targets_met else 1


if __name__ == "__main__":
    sys.exit(main())
