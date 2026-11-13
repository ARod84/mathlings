"""Offline check of the adaptive engine on made-up learners.

    uv run python -m app.adaptive.simulate --learners 500 --steps 120 --seed 1
    uv run python -m app.adaptive.simulate --focus off     # ignore the recommended focus

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

FOCUS. With --focus on (the default) each puzzle is generated with the focus
the policy recommends, as the game does. The report then has a "focus
mechanics" block for the add_visible learners: how often puzzles are focused,
whether the every-other-puzzle cap holds, and how soon the focus is released
once the mistake stops matching.

It deliberately reports NO learning effect of focus. A synthetic learner
unlearns a misconception only if this file says so, and at whatever rate this
file picks, so any "improvement" would be our own assumption shown back to
us. The learners here do not react to focus at all. Whether focused practice
helps is a question for real children's data.
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
from app.puzzles.levels import FOCUS_TARGET_FORMS, GENERATOR_VERSION, step_topic_ids
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
    # ---- focus mechanics ----
    puzzles: int = 0
    focused_puzzles: int = 0
    # Puzzles generated while the policy was reporting a focus_rule.
    puzzles_while_flagged: int = 0
    # A focused puzzle straight after a focused puzzle: the cap says never.
    back_to_back_focused: int = 0
    # Each time focus_rule went back to None: first tries since the rule last matched.
    releases: list[int] = field(default_factory=list)
    steps_played: int = 0
    # Steps of a form ADD_VISIBLE applies to, and steps that offered its wrong answer.
    add_visible_form_steps: int = 0
    add_visible_option_steps: int = 0


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
class FocusMechanics:
    """How focus behaved for one kind of learner. Mechanics only: no learning effect."""

    kind: str
    puzzles: int
    focused_puzzles: int
    puzzles_while_flagged: int
    back_to_back_focused: int
    releases: int
    average_first_tries_to_release: float | None
    most_first_tries_to_release: int | None
    steps: int
    add_visible_form_steps: int
    add_visible_option_steps: int

    @property
    def focused_percent(self) -> float:
        return _percent(self.focused_puzzles, self.puzzles)

    @property
    def focused_while_flagged_percent(self) -> float:
        return _percent(self.focused_puzzles, self.puzzles_while_flagged)

    @property
    def cap_holds(self) -> bool:
        return self.back_to_back_focused == 0

    def format(self) -> str:
        release = (
            "never released"
            if self.average_first_tries_to_release is None
            else f"{self.average_first_tries_to_release:.1f} first tries on average, "
            f"{self.most_first_tries_to_release} at most, over {self.releases} releases"
        )
        return "\n".join(
            [
                f"Focus mechanics, {self.kind} learners (no learning effect is measured)",
                f"  puzzles generated with a focus     {self.focused_puzzles} of {self.puzzles}  "
                f"({self.focused_percent:.1f}%)",
                f"  ...of the puzzles made while a mistake was flagged  "
                f"{self.focused_while_flagged_percent:.1f}%",
                f"  focused puzzles back to back       {self.back_to_back_focused}  "
                f"(cap {'holds' if self.cap_holds else 'BROKEN'})",
                f"  flag released after the rule last matched  {release}",
                f"  steps of a form ADD_VISIBLE applies to     "
                f"{_percent(self.add_visible_form_steps, self.steps):.1f}%",
                f"  steps offering the ADD_VISIBLE wrong answer  "
                f"{_percent(self.add_visible_option_steps, self.steps):.1f}%",
            ]
        )


@dataclass(frozen=True)
class SimulationReport:
    learners: int
    steps: int
    seed: int
    # True if puzzles were generated with the focus the policy recommended.
    focus: bool
    mechanics: FocusMechanics
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
            f"seed {self.seed}, generator version {GENERATOR_VERSION}, "
            f"focus {'on' if self.focus else 'off'}",
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
            "",
            self.mechanics.format(),
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
            focused=puzzle.focus is not None,
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
    use_focus: bool = True,
) -> LearnerResult:
    result = LearnerResult(kind=learner.kind.name)
    observations: list[Observation] = []
    previous_level: int | None = None
    was_flagged = False
    previous_focused = False
    add_visible = MistakeRule.ADD_VISIBLE

    while len(observations) < steps:
        recommendation = recommend_from(observations)
        done = len(observations)
        flagged = recommendation.focus_rule is not None
        if was_flagged and not flagged:
            # Released: how many first tries ago did any rule last match?
            since = next(
                (
                    back
                    for back, observation in enumerate(reversed(observations))
                    if observation.matched_rules
                ),
                done,
            )
            result.releases.append(since)
        was_flagged = flagged
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

        focus = MistakeRule(recommendation.focus) if use_focus and recommendation.focus else None
        puzzle = generate_verified(
            rng.randrange(MAX_SEED + 1),
            level,
            recommendation.length,
            focus,
            catalog=catalog,
            topic_exists=exists,
        )
        focused = puzzle.focus is not None
        result.puzzles += 1
        result.focused_puzzles += focused
        result.puzzles_while_flagged += flagged
        result.back_to_back_focused += focused and previous_focused
        previous_focused = focused
        for step_index, step in enumerate(puzzle.steps):
            result.steps_played += 1
            result.add_visible_form_steps += step.form in FOCUS_TARGET_FORMS[add_visible]
            result.add_visible_option_steps += any(d.rule is add_visible for d in step.distractors)
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
    focus: bool = True,
) -> SimulationReport:
    """Simulate `learners` learners, the kinds in turn, for `steps` first tries each.

    With `focus`, each puzzle is generated with the focus the policy
    recommends, as the game does. Without it the recommendation is ignored.
    """
    results: list[LearnerResult] = []
    for index in range(learners):
        # One generator per learner, so adding learners never changes earlier ones.
        rng = random.Random(f"{seed}:{index}")
        learner = make_learner(KINDS[index % len(KINDS)], rng)
        results.append(simulate_learner(learner, steps, rng, catalog, topic_exists, focus))

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
        focus=focus,
        mechanics=focus_mechanics("add_visible", results),
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


def focus_mechanics(kind: str, results: list[LearnerResult]) -> FocusMechanics:
    mine = [r for r in results if r.kind == kind]
    releases = [since for r in mine for since in r.releases]
    return FocusMechanics(
        kind=kind,
        puzzles=sum(r.puzzles for r in mine),
        focused_puzzles=sum(r.focused_puzzles for r in mine),
        puzzles_while_flagged=sum(r.puzzles_while_flagged for r in mine),
        back_to_back_focused=sum(r.back_to_back_focused for r in mine),
        releases=len(releases),
        average_first_tries_to_release=sum(releases) / len(releases) if releases else None,
        most_first_tries_to_release=max(releases) if releases else None,
        steps=sum(r.steps_played for r in mine),
        add_visible_form_steps=sum(r.add_visible_form_steps for r in mine),
        add_visible_option_steps=sum(r.add_visible_option_steps for r in mine),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--learners", type=int, default=500)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--focus",
        choices=("on", "off"),
        default="on",
        help="on: generate each puzzle with the focus the policy recommends (what the game "
        "does). off: ignore it.",
    )
    args = parser.parse_args(argv)

    # The puzzles need the mistake-rule catalog, which is resolved against the
    # imported taxonomy. That is the only thing read from the database.
    with Session(make_engine()) as session:
        graph = reload_graph(session)
        service = TaxonomyService(session, graph)
        catalog = load_catalog(service)
        exists = topic_exists(service)

    report = run_simulation(
        args.learners,
        args.steps,
        args.seed,
        catalog=catalog,
        topic_exists=exists,
        focus=args.focus == "on",
    )
    print(report.format())
    return 0 if report.targets_met else 1


if __name__ == "__main__":
    sys.exit(main())
