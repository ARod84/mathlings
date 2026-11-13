"""Quality report for the "Next in Line" generator.

    uv run python -m app.puzzles.report --game sequences --all --count 5000
    uv run python -m app.puzzles.report --game sequences --level 3
    uv run python -m app.puzzles.report --game sequences --samples 2     # example puzzles
    uv run python -m app.puzzles.report --game sequences --catalog       # rule -> error pattern

Uses the real database for the error-pattern links and topic ids, so run the
migration and the importer first. Seeds 0..count-1 are used, so the numbers
are the same on every run.

Two things are counted about ambiguity:

- Rejections: how often a candidate the generator made was turned down by the
  verifier because two rule families fit and disagree, or because it showed
  too few terms in a row. Each one costs a retry with a derived seed.
- What the evidence rule is for: every other place the blanks could have gone
  in the same sequences, if the level's rule about visible terms in a row
  (levels.EVIDENCE) did not exist. The verifier's own `fitting_rules` says how
  many of those would have had two answers.
"""

import argparse
import contextlib
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from sqlmodel import Session

from app.db import make_engine
from app.puzzles.core import GenerationError
from app.puzzles.core.ids import derive_seed
from app.puzzles.core.taxonomy_link import topic_exists
from app.puzzles.core.verified import MAX_ATTEMPTS
from app.puzzles.types.sequences.generator import generate
from app.puzzles.types.sequences.hints import show
from app.puzzles.types.sequences.levels import EVIDENCE, LEVELS, longest_visible_run
from app.puzzles.types.sequences.misconceptions import SequenceCatalog, resolve_catalog
from app.puzzles.types.sequences.models import MistakeRule, SequencePuzzle
from app.puzzles.types.sequences.verifier import FailureName, fitting_rules, verify
from app.taxonomy.service import TaxonomyService, reload_graph

# Generation is timed once per seed. The slowest few seeds are then timed again
# this many times each and the best time kept: a puzzle is built the same way
# every time, so the best time is the code's own, without the machine's hiccups.
RETIME_SLOWEST = 10
RETIME_REPEATS = 3


def describe(puzzle: SequencePuzzle) -> str:
    """Which sort of sequence a puzzle is, for the report's breakdown."""
    if puzzle.kind == "growing":
        return "growing step"
    if puzzle.terms[-1] < 0:
        return "constant, down through zero"
    return "constant, up" if puzzle.terms[1] > puzzle.terms[0] else "constant, down"


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
    # Blank placements the evidence rule forbids, tried on the produced sequences.
    other_placements: int = 0
    other_ambiguous: int = 0
    other_ambiguous_by_sort: Counter[str] = field(default_factory=Counter)
    other_by_sort: Counter[str] = field(default_factory=Counter)
    steps: int = 0
    sorts: Counter[str] = field(default_factory=Counter)
    blanks: Counter[int] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    linked_distractors: int = 0
    distractors: int = 0
    # Steps with at least one distractor that has a taxonomy error pattern. A
    # wrong answer can only be diagnosed if such an option was there to pick.
    steps_with_linked: int = 0
    steps_by_sort: Counter[str] = field(default_factory=Counter)
    linked_steps_by_sort: Counter[str] = field(default_factory=Counter)
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
        candidates = self.produced + self.failed + self.retries
        lines = [
            f'Level {self.level} "{spec.label}": {n} puzzles requested (seeds 0..{n - 1})',
            f"  verified puzzles produced    {self.produced}  ({share(self.produced, n)})",
            f"  passed on the first try      {self.first_try}  ({share(self.first_try, n)})",
            f"  average retries per puzzle   {self.retries / n:.4f}",
            f"  gave up after all retries    {self.failed}",
            f"  candidates made              {candidates}",
            f"    the generator gave up on the seed     {self.generation_errors}",
            f"    rejected: two families disagree       "
            f"{self.rejections[FailureName.AMBIGUOUS.value]}",
            f"    rejected: too few terms in a row      "
            f"{self.rejections[FailureName.NOT_ENOUGH_EVIDENCE.value]}",
        ]
        lines += [
            f"    rejected: {name:<28}{count}"
            for name, count in sorted(self.rejections.items())
            if name not in (FailureName.AMBIGUOUS.value, FailureName.NOT_ENOUGH_EVIDENCE.value)
        ]
        lines += [
            "  blank placements the evidence rule forbids, tried on the same sequences",
            f"    placements                 {self.other_placements}",
            f"    of those, two answers      {self.other_ambiguous}  "
            f"({share(self.other_ambiguous, self.other_placements).strip()})",
        ]
        lines += [
            f"      {sort:<28}{self.other_ambiguous_by_sort[sort]:>6} of "
            f"{self.other_by_sort[sort]:>6}  "
            f"({share(self.other_ambiguous_by_sort[sort], self.other_by_sort[sort]).strip()})"
            for sort in sorted(self.other_by_sort)
        ]
        lines += [
            f"  slowest generation           {self.slowest_ms:.2f} ms (seed {self.slowest_seed}, "
            f"best of {RETIME_REPEATS})",
            f"  largest single timing seen   {self.largest_single_ms:.2f} ms",
            f"  average generation           {self.total_ms / n:.3f} ms",
            f"  steps (blanks) generated     {self.steps}",
            "  puzzles by number of blanks",
        ]
        lines += [
            f"    {count} blank{'s' if count > 1 else ' '}   {self.blanks[count]:>7}  "
            f"{share(self.blanks[count], self.produced)}"
            for count in sorted(self.blanks)
        ]
        lines.append("  puzzles by sort of sequence")
        lines += [
            f"    {sort:<28}{self.sorts[sort]:>7}  {share(self.sorts[sort], self.produced)}"
            for sort in sorted(self.sorts)
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
        lines += [
            f"    {sort:<28}{self.linked_steps_by_sort[sort]:>6} of {self.steps_by_sort[sort]:>6}  "
            f"({share(self.linked_steps_by_sort[sort], self.steps_by_sort[sort]).strip()})"
            for sort in sorted(self.steps_by_sort)
        ]
        return "\n".join(lines)


def _forbidden_placements(puzzle: SequencePuzzle) -> list[tuple[int, ...]]:
    """Where the blanks could go by position alone, but may not for lack of visible terms."""
    spec = LEVELS[puzzle.level]
    length = len(puzzle.terms)
    if spec.blank_at_end_only:
        return []
    return [
        blanks
        for count in range(1, spec.max_blanks + 1)
        for blanks in combinations(range(1, length), count)
        if longest_visible_run(length, blanks) < EVIDENCE[puzzle.kind]
    ]


def _has_two_answers(puzzle: SequencePuzzle, blanks: tuple[int, ...]) -> bool:
    visible = {p: value for p, value in enumerate(puzzle.terms) if p not in blanks}
    fit = fitting_rules(visible, len(puzzle.terms))
    return bool(fit.open_families) or any(
        len({rule.terms[position] for rule in fit.rules}) > 1 for position in blanks
    )


def _attempt(seed: int, level: int, catalog: SequenceCatalog, exists, report: LevelReport | None):
    """What generate_verified does, one candidate at a time, with the reasons kept.

    Returns the puzzle and the number of retries, or None if every attempt failed.
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
            return puzzle, attempt
        if report is not None:
            report.rejections.update(name.value for name in result.names)
    return None


def build_report(level: int, count: int, catalog: SequenceCatalog, exists) -> LevelReport:
    report = LevelReport(level=level, requested=count)
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
        puzzle, retries = outcome
        report.produced += 1
        report.retries += retries
        report.first_try += retries == 0
        sort = describe(puzzle)
        report.sorts[sort] += 1
        report.blanks[len(puzzle.steps)] += 1
        for blanks in _forbidden_placements(puzzle):
            report.other_placements += 1
            report.other_by_sort[sort] += 1
            if _has_two_answers(puzzle, blanks):
                report.other_ambiguous += 1
                report.other_ambiguous_by_sort[sort] += 1
        for step in puzzle.steps:
            report.steps += 1
            report.steps_by_sort[sort] += 1
            linked = [d for d in step.distractors if d.error_pattern_id is not None]
            report.linked_distractors += len(linked)
            report.steps_with_linked += bool(linked)
            report.linked_steps_by_sort[sort] += bool(linked)
            for distractor in step.distractors:
                report.distractors += 1
                report.rules[distractor.rule.value] += 1

    for _elapsed, seed in sorted(timings, reverse=True)[:RETIME_SLOWEST]:
        best = float("inf")
        for _ in range(RETIME_REPEATS):
            started = time.perf_counter()
            _attempt(seed, level, catalog, exists, None)
            best = min(best, (time.perf_counter() - started) * 1000)
        if best > report.slowest_ms:
            report.slowest_ms, report.slowest_seed = best, seed
    return report


def format_puzzle(puzzle: SequencePuzzle) -> str:
    row = ", ".join(
        "□" if position in puzzle.blanks else show(term)
        for position, term in enumerate(puzzle.terms)
    )
    lines = [
        f"{puzzle.puzzle_id}   level {puzzle.level}, {describe(puzzle)}, seed {puzzle.seed}",
        f"  {row}",
        f"  topics: {', '.join(puzzle.topic_ids)}",
    ]
    for number, step in enumerate(puzzle.steps, start=1):
        lines.append(f"  blank {number} (term {step.position + 1}) -> {show(step.answer)}")
        for distractor in step.distractors:
            pattern = f"  -> {distractor.error_pattern_id}" if distractor.error_pattern_id else ""
            lines.append(f"       {show(distractor.value):<6} {distractor.rule.value}{pattern}")
        lines += [f"       hint {tier}: {hint}" for tier, hint in enumerate(step.hints, start=1)]
    return "\n".join(lines)


def format_catalog(catalog: SequenceCatalog) -> str:
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
