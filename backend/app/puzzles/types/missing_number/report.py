"""Quality report for the missing-number chain generator.

    uv run python -m app.puzzles.types.missing_number.report --level 1 --count 5000
    uv run python -m app.puzzles.types.missing_number.report --all --count 5000
    uv run python -m app.puzzles.types.missing_number.report --samples 2    # example puzzles
    uv run python -m app.puzzles.types.missing_number.report --catalog      # rule -> error pattern

Uses the real database for the error-pattern links and topic ids, so run the
migration and the importer first. Seeds 0..count-1 are used, with chain
lengths 1 to 4 in turn, so the numbers are the same on every run.
"""

import argparse
import contextlib
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session

from app.db import make_engine
from app.puzzles.types.missing_number.equations import ALL_FORMS, render
from app.puzzles.types.missing_number.levels import (
    ANSWER_LEFT_FORMS,
    FOCUS_TARGET_FORMS,
    LEVELS,
    MAX_STEPS,
    MIN_STEPS,
)
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog
from app.puzzles.types.missing_number.models import MistakeRule, Puzzle
from app.puzzles.types.missing_number.rules import distractor_value, rule_output
from app.puzzles.types.missing_number.taxonomy_link import load_catalog, topic_exists
from app.puzzles.types.missing_number.verified import (
    PuzzleGenerationFailed,
    generate_verified_outcome,
)
from app.taxonomy.service import TaxonomyService, reload_graph

# Generation is timed once per seed. The slowest few seeds are then timed again
# this many times each and the best time kept: a puzzle is built the same way
# every time, so the best time is the code's own, without the machine's hiccups.
RETIME_SLOWEST = 10
RETIME_REPEATS = 3


@dataclass
class LevelReport:
    level: int
    requested: int
    # The mistake rule every puzzle was generated to target, or None.
    focus: MistakeRule | None = None
    # With a focus: steps of a form it targets, and those that offer its wrong answer.
    targeted_steps: int = 0
    focus_option_steps: int = 0
    # Chains with two or more answer-left steps, and the most in any one chain.
    chains_with_two_answer_left: int = 0
    most_answer_left: int = 0
    # Chains of three or more steps where every step is one the focus targets (must be 0).
    chains_without_untargeted_step: int = 0
    produced: int = 0
    failed: int = 0
    first_try: int = 0
    retries: int = 0
    steps: int = 0
    forms: Counter[str] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    linked_distractors: int = 0
    distractors: int = 0
    # Steps with at least one distractor that has a taxonomy error pattern. A
    # wrong answer can only be diagnosed if such an option was there to pick.
    steps_with_linked: int = 0
    # Per linked rule: steps where the mistake gives a value, and steps where
    # that value could not be offered because it is outside the allowed range.
    linked_applied: Counter[str] = field(default_factory=Counter)
    linked_dropped: Counter[str] = field(default_factory=Counter)
    steps_with_dropped: int = 0
    # The slowest puzzle to make, re-timed (best of RETIME_REPEATS) so that one
    # interruption by the operating system does not pass for slow code.
    slowest_ms: float = 0.0
    slowest_seed: int = 0
    # The largest single timing seen in the main loop, interruptions included.
    largest_single_ms: float = 0.0
    total_ms: float = 0.0

    def format(self) -> str:
        def share(part: int, whole: int) -> str:
            return f"{100 * part / whole:5.1f}%" if whole else "    -"

        n = self.requested
        focus = f", focus {self.focus.value}" if self.focus else ", no focus"
        lines = [
            f"Level {self.level}: {n} puzzles requested (seeds 0..{n - 1}){focus}",
            f"  verified puzzles produced    {self.produced}  ({share(self.produced, n)})",
            f"  passed on the first try      {self.first_try}  ({share(self.first_try, n)})",
            f"  average retries per puzzle   {self.retries / n:.4f}",
            f"  gave up after all retries    {self.failed}",
            f"  slowest generation           {self.slowest_ms:.2f} ms (seed {self.slowest_seed}, "
            f"best of {RETIME_REPEATS})",
            f"  largest single timing seen   {self.largest_single_ms:.2f} ms",
            f"  average generation           {self.total_ms / n:.3f} ms",
            f"  steps generated              {self.steps}",
            "  forms",
        ]
        lines += [
            f"    {form:<7}{self.forms[form]:>7}  {share(self.forms[form], self.steps)}"
            for form in ALL_FORMS
        ]
        lines.append("  distractor rules")
        lines += [
            f"    {rule.value:<22}{self.rules[rule.value]:>7}  "
            f"{share(self.rules[rule.value], self.distractors)}"
            for rule in MistakeRule
        ]
        lines.append(
            f"  distractors linked to a taxonomy error pattern  "
            f"{self.linked_distractors} of {self.distractors}  "
            f"({share(self.linked_distractors, self.distractors).strip()})"
        )
        lines.append(
            f"  steps with at least one linked distractor       "
            f"{self.steps_with_linked} of {self.steps}  "
            f"({share(self.steps_with_linked, self.steps).strip()})"
        )
        lines.append(
            f"  steps where a linked rule applied but its value was out of range  "
            f"{self.steps_with_dropped} of {self.steps}  "
            f"({share(self.steps_with_dropped, self.steps).strip()})"
        )
        lines += [
            f"    {rule:<22}{self.linked_dropped[rule]:>7} of {self.linked_applied[rule]:>6} "
            f"steps where it applied  ({share(self.linked_dropped[rule], self.steps).strip()} "
            f"of all steps)"
            for rule in sorted(self.linked_applied)
        ]
        lines.append(
            f"  chains with two or more answer-left steps        "
            f"{self.chains_with_two_answer_left}  (most in one chain: {self.most_answer_left})"
        )
        if self.focus is not None:
            lines += [
                f"  steps of a form the focus targets                "
                f"{self.targeted_steps} of {self.steps}  "
                f"({share(self.targeted_steps, self.steps).strip()})",
                f"  targeted steps that offer the focus wrong answer  "
                f"{self.focus_option_steps} of {self.targeted_steps}  "
                f"({share(self.focus_option_steps, self.targeted_steps).strip()})",
                f"  chains of 3+ with no untargeted step (must be 0)  "
                f"{self.chains_without_untargeted_step}",
            ]
        return "\n".join(lines)


def build_report(
    level: int,
    count: int,
    catalog: MisconceptionCatalog,
    exists,
    focus: MistakeRule | None = None,
) -> LevelReport:
    report = LevelReport(level=level, requested=count, focus=focus)
    targets = FOCUS_TARGET_FORMS.get(focus, frozenset()) if focus else frozenset()
    spec = LEVELS[level]
    linked_rules = [rule for rule in MistakeRule if catalog.is_linked(rule)]
    lengths = range(MIN_STEPS, MAX_STEPS + 1)
    timings: list[tuple[float, int]] = []
    for seed in range(count):
        length = lengths[seed % len(lengths)]
        started = time.perf_counter()
        try:
            outcome = generate_verified_outcome(
                seed, level, length, focus, catalog=catalog, topic_exists=exists
            )
        except PuzzleGenerationFailed:
            outcome = None
        elapsed_ms = (time.perf_counter() - started) * 1000
        report.total_ms += elapsed_ms
        timings.append((elapsed_ms, seed))
        if outcome is None:
            report.failed += 1
            continue
        report.produced += 1
        report.retries += outcome.retries
        report.first_try += outcome.retries == 0
        forms = [step.form for step in outcome.puzzle.steps]
        answer_left = sum(form in ANSWER_LEFT_FORMS for form in forms)
        report.chains_with_two_answer_left += answer_left >= 2
        report.most_answer_left = max(report.most_answer_left, answer_left)
        report.chains_without_untargeted_step += (
            bool(targets) and len(forms) >= 3 and all(form in targets for form in forms)
        )
        for step in outcome.puzzle.steps:
            if step.form in targets:
                report.targeted_steps += 1
                report.focus_option_steps += any(d.rule is focus for d in step.distractors)
            report.steps += 1
            report.forms[step.form] += 1
            for distractor in step.distractors:
                report.distractors += 1
                report.rules[distractor.rule.value] += 1
                report.linked_distractors += distractor.error_pattern_id is not None
            report.steps_with_linked += any(d.error_pattern_id for d in step.distractors)
            dropped_here = False
            for rule in linked_rules:
                if rule_output(rule, step, spec) is None:
                    continue
                report.linked_applied[rule.value] += 1
                # The mistake gives a value, but it cannot be shown as an option.
                if distractor_value(rule, step, spec) is None:
                    report.linked_dropped[rule.value] += 1
                    dropped_here = True
            report.steps_with_dropped += dropped_here

    timings.sort(reverse=True)
    report.largest_single_ms = timings[0][0] if timings else 0.0
    for _first_ms, seed in timings[:RETIME_SLOWEST]:
        best = float("inf")
        for _repeat in range(RETIME_REPEATS):
            started = time.perf_counter()
            with contextlib.suppress(PuzzleGenerationFailed):
                generate_verified_outcome(
                    seed,
                    level,
                    lengths[seed % len(lengths)],
                    focus,
                    catalog=catalog,
                    topic_exists=exists,
                )
            best = min(best, (time.perf_counter() - started) * 1000)
        if best > report.slowest_ms:
            report.slowest_ms, report.slowest_seed = best, seed
    return report


def format_puzzle(puzzle: Puzzle) -> str:
    lines = [
        f"{puzzle.puzzle_id}   level {puzzle.level}, {len(puzzle.steps)} steps, seed {puzzle.seed}",
        f"  topics: {', '.join(puzzle.topic_ids)}",
        f"  focus: {puzzle.focus.value if puzzle.focus else 'none'}",
    ]
    for number, step in enumerate(puzzle.steps, start=1):
        link = "" if step.link_position is None else f"   (link at position {step.link_position})"
        lines.append(
            f"  {number}. {render(step.equation):<18} -> {step.answer:<5} [{step.form}]{link}"
        )
        for distractor in step.distractors:
            pattern = f"  -> {distractor.error_pattern_id}" if distractor.error_pattern_id else ""
            lines.append(f"       {distractor.value:<5} {distractor.rule.value}{pattern}")
    return "\n".join(lines)


def format_catalog(catalog: MisconceptionCatalog) -> str:
    lines = ["Rule -> taxonomy error pattern"]
    for rule, pattern in catalog.table():
        if pattern is None:
            lines.append(f"  {rule.value:<22} (none)")
            continue
        text = pattern.pattern if len(pattern.pattern) <= 70 else pattern.pattern[:67] + "..."
        lines.append(f"  {rule.value:<22} {pattern.error_pattern_id}")
        lines.append(f"  {'':<22}   pattern: {text}")
        lines.append(f"  {'':<22}   reteach: {pattern.reteach_topic_id}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--level", type=int, choices=sorted(LEVELS))
    parser.add_argument("--all", action="store_true", help="report every level")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--samples", type=int, default=0, help="print this many puzzles per level")
    parser.add_argument("--catalog", action="store_true", help="print the rule mapping")
    parser.add_argument(
        "--focus",
        choices=[rule.value for rule in FOCUS_TARGET_FORMS],
        help="generate every puzzle with this focus (default: no focus)",
    )
    args = parser.parse_args(argv)
    levels = sorted(LEVELS) if args.all or args.level is None else [args.level]
    focus = MistakeRule(args.focus) if args.focus else None

    # The report contains "□" and "−"; a Windows console may not default to UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    with Session(make_engine()) as session:
        graph = reload_graph(session)
        service = TaxonomyService(session, graph)
        catalog = load_catalog(service)
        exists = topic_exists(service)

    if args.catalog:
        print(format_catalog(catalog))
    if args.samples:
        for level in levels:
            for seed in range(args.samples):
                outcome = generate_verified_outcome(
                    seed + 1, level, 3, focus, catalog=catalog, topic_exists=exists
                )
                print(format_puzzle(outcome.puzzle), end="\n\n")
    if not args.catalog and not args.samples:
        for level in levels:
            print(build_report(level, args.count, catalog, exists, focus).format(), end="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
