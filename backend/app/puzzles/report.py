"""Quality report for the missing-number chain generator.

    uv run python -m app.puzzles.report --level 1 --count 5000
    uv run python -m app.puzzles.report --all --count 5000
    uv run python -m app.puzzles.report --samples 2          # print example puzzles
    uv run python -m app.puzzles.report --catalog            # rule -> error pattern table

Uses the real database for the error-pattern links and topic ids, so run the
migration and the importer first. Seeds 0..count-1 are used, with chain
lengths 1 to 4 in turn, so the numbers are the same on every run.
"""

import argparse
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session

from app.db import make_engine
from app.puzzles.equations import ALL_FORMS, render
from app.puzzles.levels import LEVELS, MAX_STEPS, MIN_STEPS
from app.puzzles.misconceptions import MisconceptionCatalog
from app.puzzles.models import MistakeRule, Puzzle
from app.puzzles.taxonomy_link import load_catalog, topic_exists
from app.puzzles.verified import PuzzleGenerationFailed, generate_verified_outcome
from app.taxonomy.service import TaxonomyService, reload_graph


@dataclass
class LevelReport:
    level: int
    requested: int
    produced: int = 0
    failed: int = 0
    first_try: int = 0
    retries: int = 0
    steps: int = 0
    forms: Counter[str] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    linked_distractors: int = 0
    distractors: int = 0
    slowest_ms: float = 0.0
    slowest_seed: int = 0
    total_ms: float = 0.0

    def format(self) -> str:
        def share(part: int, whole: int) -> str:
            return f"{100 * part / whole:5.1f}%" if whole else "    -"

        n = self.requested
        lines = [
            f"Level {self.level}: {n} puzzles requested (seeds 0..{n - 1})",
            f"  verified puzzles produced    {self.produced}  ({share(self.produced, n)})",
            f"  passed on the first try      {self.first_try}  ({share(self.first_try, n)})",
            f"  average retries per puzzle   {self.retries / n:.4f}",
            f"  gave up after all retries    {self.failed}",
            f"  slowest generation           {self.slowest_ms:.2f} ms (seed {self.slowest_seed})",
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
        return "\n".join(lines)


def build_report(level: int, count: int, catalog: MisconceptionCatalog, exists) -> LevelReport:
    report = LevelReport(level=level, requested=count)
    lengths = range(MIN_STEPS, MAX_STEPS + 1)
    for seed in range(count):
        length = lengths[seed % len(lengths)]
        started = time.perf_counter()
        try:
            outcome = generate_verified_outcome(
                seed, level, length, catalog=catalog, topic_exists=exists
            )
        except PuzzleGenerationFailed:
            outcome = None
        elapsed_ms = (time.perf_counter() - started) * 1000
        report.total_ms += elapsed_ms
        if elapsed_ms > report.slowest_ms:
            report.slowest_ms, report.slowest_seed = elapsed_ms, seed
        if outcome is None:
            report.failed += 1
            continue
        report.produced += 1
        report.retries += outcome.retries
        report.first_try += outcome.retries == 0
        for step in outcome.puzzle.steps:
            report.steps += 1
            report.forms[step.form] += 1
            for distractor in step.distractors:
                report.distractors += 1
                report.rules[distractor.rule.value] += 1
                report.linked_distractors += distractor.error_pattern_id is not None
    return report


def format_puzzle(puzzle: Puzzle) -> str:
    lines = [
        f"{puzzle.puzzle_id}   level {puzzle.level}, {len(puzzle.steps)} steps, seed {puzzle.seed}",
        f"  topics: {', '.join(puzzle.topic_ids)}",
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
    args = parser.parse_args(argv)
    levels = sorted(LEVELS) if args.all or args.level is None else [args.level]

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
                    seed + 1, level, 3, catalog=catalog, topic_exists=exists
                )
                print(format_puzzle(outcome.puzzle), end="\n\n")
    if not args.catalog and not args.samples:
        for level in levels:
            print(build_report(level, args.count, catalog, exists).format(), end="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
