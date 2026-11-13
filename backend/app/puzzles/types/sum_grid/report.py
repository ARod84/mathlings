"""Quality report for the Sum Grid generator.

    uv run python -m app.puzzles.report --game sum-grid --all --count 5000
    uv run python -m app.puzzles.report --game sum-grid --level 3
    uv run python -m app.puzzles.report --game sum-grid --samples 2     # example grids
    uv run python -m app.puzzles.report --game sum-grid --catalog       # rule -> error pattern

Uses the real database for the error-pattern links and topic ids, so run the
migration and the importer first. Seeds 0..count-1 are used, so the numbers
are the same on every run.

Besides the usual counts it reports how much work the verifier's solution
search does (the numbers it tries in a blank, per puzzle), and at level 3 how
often the TENS_AS_ONES mistake has a multiple of ten to act on.
"""

import argparse
import contextlib
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session

from app.db import make_engine
from app.puzzles.core import GenerationError
from app.puzzles.core.ids import derive_seed
from app.puzzles.core.taxonomy_link import topic_exists
from app.puzzles.core.verified import MAX_ATTEMPTS
from app.puzzles.types.sum_grid.generator import generate
from app.puzzles.types.sum_grid.hints import line_name
from app.puzzles.types.sum_grid.levels import LEVELS
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog, resolve_catalog
from app.puzzles.types.sum_grid.models import MistakeRule, SumGridPuzzle
from app.puzzles.types.sum_grid.rules import rule_output, step_view
from app.puzzles.types.sum_grid.verifier import verify
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
    produced: int = 0
    failed: int = 0
    first_try: int = 0
    retries: int = 0
    # Why a candidate was not used. One candidate can have several reasons.
    generation_errors: int = 0
    rejections: Counter[str] = field(default_factory=Counter)
    # Numbers the verifier's solution search tried in a blank, per verified puzzle.
    nodes_total: int = 0
    nodes_max: int = 0
    nodes_max_seed: int = 0
    steps: int = 0
    blanks: Counter[int] = field(default_factory=Counter)
    lines: Counter[str] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    linked_distractors: int = 0
    distractors: int = 0
    # Steps with at least one distractor that has a taxonomy error pattern. A
    # wrong answer can only be diagnosed if such an option was there to pick.
    steps_with_linked: int = 0
    # TENS_AS_ONES: steps where the mistake gives a wrong value at all (there
    # is a multiple of ten among the known cells), and steps that offer it.
    tens_applies: int = 0
    tens_offered: int = 0
    puzzles_with_tens: int = 0
    # The slowest puzzle to make, re-timed (best of RETIME_REPEATS) so that one
    # interruption by the operating system does not pass for slow code.
    slowest_ms: float = 0.0
    slowest_seed: int = 0
    largest_single_ms: float = 0.0
    total_ms: float = 0.0

    def format(self) -> str:
        def share(part: int, whole: int) -> str:
            return f"{100 * part / whole:5.1f}%" if whole else "    -"

        n = self.requested
        spec = LEVELS[self.level]
        lines = [
            f"Level {self.level} ({spec.size} by {spec.size}): {n} puzzles requested "
            f"(seeds 0..{n - 1})",
            f"  verified puzzles produced    {self.produced}  ({share(self.produced, n)})",
            f"  passed on the first try      {self.first_try}  ({share(self.first_try, n)})",
            f"  average retries per puzzle   {self.retries / n:.4f}",
            f"  gave up after all retries    {self.failed}",
            f"  the generator gave up on a seed   {self.generation_errors}",
        ]
        lines += [
            f"  rejected: {name:<28}{count}" for name, count in sorted(self.rejections.items())
        ]
        lines += [
            "  verifier's solution search, numbers tried per puzzle",
            f"    average                    {self.nodes_total / max(1, self.produced):.2f}",
            f"    most                       {self.nodes_max} (seed {self.nodes_max_seed})",
            f"  slowest generation           {self.slowest_ms:.2f} ms (seed {self.slowest_seed}, "
            f"best of {RETIME_REPEATS})",
            f"  largest single timing seen   {self.largest_single_ms:.2f} ms",
            f"  average generation           {self.total_ms / n:.3f} ms",
            f"  steps (blanks) generated     {self.steps}",
            "  puzzles by number of blanks",
        ]
        lines += [
            f"    {count} blanks  {self.blanks[count]:>7}  "
            f"{share(self.blanks[count], self.produced)}"
            for count in sorted(self.blanks)
        ]
        lines.append("  steps by the line they are solved from")
        lines += [
            f"    {kind:<8}{self.lines[kind]:>7}  {share(self.lines[kind], self.steps)}"
            for kind in ("row", "col")
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
        if spec.tens_as_ones_rule:
            lines += [
                f"  steps where TENS_AS_ONES could apply            "
                f"{self.tens_applies} of {self.steps}  "
                f"({share(self.tens_applies, self.steps).strip()})",
                f"  steps that offer the TENS_AS_ONES wrong answer   "
                f"{self.tens_offered} of {self.steps}  "
                f"({share(self.tens_offered, self.steps).strip()})",
                f"  puzzles with at least one such step             "
                f"{self.puzzles_with_tens} of {self.produced}  "
                f"({share(self.puzzles_with_tens, self.produced).strip()})",
            ]
        return "\n".join(lines)


def _attempt(seed: int, level: int, catalog: SumGridCatalog, exists, report: LevelReport | None):
    """What generate_verified does, one candidate at a time, with the reasons kept.

    Returns the puzzle, the number of retries and the verifier's search size,
    or None if every attempt failed.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            puzzle = generate(derive_seed(seed, attempt), level, catalog)
        except GenerationError:
            if report is not None:
                report.generation_errors += 1
            continue
        result = verify(puzzle, catalog=catalog, topic_exists=exists)
        if result.ok:
            return puzzle, attempt, result.nodes
        if report is not None:
            report.rejections.update(name.value for name in result.names)
    return None


def build_report(level: int, count: int, catalog: SumGridCatalog, exists) -> LevelReport:
    report = LevelReport(level=level, requested=count)
    spec = LEVELS[level]
    timings: list[tuple[float, int]] = []
    for seed in range(count):
        started = time.perf_counter()
        outcome = _attempt(seed, level, catalog, exists, report)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings.append((elapsed_ms, seed))
        report.total_ms += elapsed_ms
        report.largest_single_ms = max(report.largest_single_ms, elapsed_ms)
        if outcome is None:
            report.failed += 1
            continue
        puzzle, retries, nodes = outcome
        report.produced += 1
        report.retries += retries
        report.first_try += retries == 0
        report.nodes_total += nodes
        if nodes > report.nodes_max:
            report.nodes_max, report.nodes_max_seed = nodes, seed
        report.blanks[len(puzzle.steps)] += 1
        has_tens = False
        for index, step in enumerate(puzzle.steps):
            report.steps += 1
            report.lines[step.line.kind] += 1
            linked = [d for d in step.distractors if d.error_pattern_id is not None]
            report.linked_distractors += len(linked)
            report.steps_with_linked += bool(linked)
            for distractor in step.distractors:
                report.distractors += 1
                report.rules[distractor.rule.value] += 1
            view = step_view(puzzle, index)
            if rule_output(MistakeRule.TENS_AS_ONES, view, spec) is not None:
                report.tens_applies += 1
                has_tens = True
            report.tens_offered += any(d.rule is MistakeRule.TENS_AS_ONES for d in step.distractors)
        report.puzzles_with_tens += has_tens

    for _elapsed, seed in sorted(timings, reverse=True)[:RETIME_SLOWEST]:
        best = float("inf")
        for _ in range(RETIME_REPEATS):
            started = time.perf_counter()
            _attempt(seed, level, catalog, exists, None)
            best = min(best, (time.perf_counter() - started) * 1000)
        if best > report.slowest_ms:
            report.slowest_ms, report.slowest_seed = best, seed
    return report


def format_puzzle(puzzle: SumGridPuzzle) -> str:
    width = max(len(str(value)) for value in (*puzzle.row_targets, *puzzle.col_targets))
    lines = [
        f"{puzzle.puzzle_id}   level {puzzle.level}, {puzzle.size} by {puzzle.size}, "
        f"seed {puzzle.seed}",
        f"  topics: {', '.join(puzzle.topic_ids)}",
    ]
    for row, target in zip(puzzle.cells, puzzle.row_targets, strict=True):
        cells = " | ".join(f"{'□' if value is None else value:>{width}}" for value in row)
        lines.append(f"    {cells} | {target:>{width}}")
    lines.append("    " + " | ".join(f"{target:>{width}}" for target in puzzle.col_targets))
    for number, step in enumerate(puzzle.steps, start=1):
        lines.append(
            f"  step {number}: row {step.cell.row + 1}, column {step.cell.col + 1}, from "
            f"{line_name(step.line, puzzle.size)} -> {step.answer}"
        )
        for distractor in step.distractors:
            pattern = f"  -> {distractor.error_pattern_id}" if distractor.error_pattern_id else ""
            lines.append(f"       {distractor.value:<5} {distractor.rule.value}{pattern}")
        lines += [f"       hint {tier}: {hint}" for tier, hint in enumerate(step.hints, start=1)]
    return "\n".join(lines)


def format_catalog(catalog: SumGridCatalog) -> str:
    lines = ["Rule -> taxonomy error pattern"]
    for rule, pattern in catalog.table():
        if pattern is None:
            lines.append(f"  {rule.value:<18} (none)")
            continue
        text = pattern.pattern if len(pattern.pattern) <= 70 else pattern.pattern[:67] + "..."
        lines.append(f"  {rule.value:<18} {pattern.error_pattern_id}")
        lines.append(f"  {'':<18}   pattern: {text}")
        lines.append(f"  {'':<18}   reteach: {pattern.reteach_topic_id}")
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
        with contextlib.suppress(ValueError):
            sys.stdout.reconfigure(encoding="utf-8")

    with Session(make_engine()) as session:
        graph = reload_graph(session)
        service = TaxonomyService(session, graph)
        catalog = resolve_catalog(service.get_error_patterns)
        exists = topic_exists(service)

    if args.catalog:
        print(format_catalog(catalog))
    if args.samples:
        for level in levels:
            for seed in range(args.samples):
                outcome = _attempt(seed + 1, level, catalog, exists, None)
                if outcome is not None:
                    print(format_puzzle(outcome[0]), end="\n\n")
    if not args.catalog and not args.samples:
        for level in levels:
            print(build_report(level, args.count, catalog, exists).format(), end="\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
