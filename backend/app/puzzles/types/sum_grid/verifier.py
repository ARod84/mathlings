"""Checks a Sum Grid without trusting how it was made.

    verify(puzzle, catalog=..., topic_exists=...) -> VerificationResult

A puzzle does not reach a child unless `result.ok`. This module never imports
the generator, and uses neither its arithmetic nor its deduction code. It
works from the visible cells and the targets, so a grid written by hand, by
another program or by a model can be checked the same way.

Two questions are answered separately, because neither implies the other:

EXACTLY ONE SOLUTION. `count_solutions` tries numbers in the blanks, a blank
at a time, within the level's range, and counts the ways that meet every row
and column target. It stops at the second. Exactly one must exist, and it
must be the stored answers. (A grid can have one solution and still need a
guess to start, and a grid whose stored order never guesses can only have
one solution; both checks are made anyway, each on its own evidence.)

NO GUESSING. The stored order is replayed on the visible grid. At each step
the recorded line must have exactly one cell still unknown, and that cell
must be the step's own. This is the "can every block be worked out" idea of
Number Pyramid, here on the server.

It does share the declared rules of the puzzle type (levels.py), the mistake
rules (rules.py) and the way a number in a hint is read back: a distractor
has to equal what its rule gives, and there is one definition of each rule.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.puzzles.core.hint_text import written_numbers
from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import (
    DISTRACTORS_PER_STEP,
    GENERATOR_VERSION,
    HINT_TIERS,
    LEVELS,
    PUZZLE_TYPE,
    LevelSpec,
    step_topic_ids,
)
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog
from app.puzzles.types.sum_grid.models import MistakeRule, SumGridPuzzle, SumGridStep
from app.puzzles.types.sum_grid.rules import StepView, distractor_value, is_near_miss

Grid = list[list[int | None]]


class FailureName(StrEnum):
    UNSUPPORTED_PUZZLE = "unsupported_puzzle"
    PUZZLE_ID_MISMATCH = "puzzle_id_mismatch"
    BAD_GRID = "bad_grid"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    TARGET_OUT_OF_RANGE = "target_out_of_range"
    BAD_BLANK_COUNT = "bad_blank_count"
    LINE_WITHOUT_A_NUMBER = "line_without_a_number"
    BAD_STEPS = "bad_steps"
    NO_SOLUTION = "no_solution"
    MULTIPLE_SOLUTIONS = "multiple_solutions"
    WRONG_ANSWER = "wrong_answer"
    TARGET_MISMATCH = "target_mismatch"
    NEEDS_A_GUESS = "needs_a_guess"
    DISTRACTOR_COUNT = "distractor_count"
    DUPLICATE_DISTRACTOR = "duplicate_distractor"
    DISTRACTOR_EQUALS_ANSWER = "distractor_equals_answer"
    DISTRACTOR_OUT_OF_RANGE = "distractor_out_of_range"
    DISTRACTOR_RULE_MISMATCH = "distractor_rule_mismatch"
    DISTRACTOR_PATTERN_MISMATCH = "distractor_pattern_mismatch"
    HINT_COUNT = "hint_count"
    HINT_REVEALS_ANSWER = "hint_reveals_answer"
    HINT_MISSING_ANSWER = "hint_missing_answer"
    WRONG_TOPICS = "wrong_topics"
    UNKNOWN_TOPIC = "unknown_topic"


@dataclass(frozen=True)
class Failure:
    name: FailureName
    detail: str
    # 0-based step the failure is in; None when it is about the whole puzzle.
    step: int | None = None


@dataclass(frozen=True)
class VerificationResult:
    failures: list[Failure] = field(default_factory=list)
    # How many numbers the solution search tried in a blank. For the quality report.
    nodes: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def names(self) -> set[FailureName]:
        return {failure.name for failure in self.failures}


# ---- how many solutions ----


@dataclass(frozen=True)
class SolutionCount:
    # 0, 1 or 2. The search stops at the second, so 2 means "more than one".
    count: int
    # The first solution found: the whole grid, blanks filled in. None if there is none.
    first: list[list[int]] | None
    # How many numbers were tried in a blank.
    nodes: int


def count_solutions(
    cells: Grid,
    row_targets: list[int],
    col_targets: list[int],
    min_value: int,
    max_value: int,
) -> SolutionCount:
    """Count the ways to fill the blanks that meet every target, stopping at two.

    A small backtracking search: the blanks are taken in reading order, each
    tried with every number of the range that its row and its column can
    still take, given how much of their targets is left and how many other
    blanks still have to share it.
    """
    size = len(cells)
    grid: Grid = [list(row) for row in cells]
    blanks = [(r, c) for r in range(size) for c in range(size) if grid[r][c] is None]
    found: list[list[list[int]]] = []
    nodes = 0

    def room(values: list[int | None], target: int) -> tuple[int, int]:
        """The least and the most one more blank of this line can be."""
        left = target - sum(value for value in values if value is not None)
        others = sum(value is None for value in values) - 1
        return left - others * max_value, left - others * min_value

    def fill(index: int) -> None:
        nonlocal nodes
        if len(found) == 2:
            return
        if index == len(blanks):
            rows_ok = all(sum(v or 0 for v in grid[r]) == row_targets[r] for r in range(size))
            cols_ok = all(
                sum(grid[r][c] or 0 for r in range(size)) == col_targets[c] for c in range(size)
            )
            if rows_ok and cols_ok:
                found.append([[value or 0 for value in row] for row in grid])
            return
        row, col = blanks[index]
        row_low, row_high = room(grid[row], row_targets[row])
        col_low, col_high = room([grid[r][col] for r in range(size)], col_targets[col])
        for value in range(
            max(min_value, row_low, col_low), min(max_value, row_high, col_high) + 1
        ):
            nodes += 1
            grid[row][col] = value
            fill(index + 1)
            if len(found) == 2:
                break
        grid[row][col] = None

    fill(0)
    return SolutionCount(len(found), found[0] if found else None, nodes)


# ---- the puzzle ----


def _line_cells(kind: str, index: int, size: int) -> list[tuple[int, int]]:
    return [(index, i) if kind == "row" else (i, index) for i in range(size)]


def _check_options_and_hints(
    index: int,
    step: SumGridStep,
    view: StepView,
    spec: LevelSpec,
    catalog: SumGridCatalog,
) -> list[Failure]:
    failures: list[Failure] = []

    def fail(name: FailureName, detail: str) -> None:
        failures.append(Failure(name, detail, index))

    answer = view.answer
    primary_topic_id = spec.topic_ids[0]

    # ---- distractors ----
    if len(step.distractors) != DISTRACTORS_PER_STEP:
        fail(FailureName.DISTRACTOR_COUNT, f"{len(step.distractors)} distractors, need 3")
    values = [distractor.value for distractor in step.distractors]
    if len(set(values)) != len(values):
        fail(FailureName.DUPLICATE_DISTRACTOR, f"{values}")
    for distractor in step.distractors:
        if distractor.value == answer:
            fail(FailureName.DISTRACTOR_EQUALS_ANSWER, f"{distractor.value} is the answer")
            continue
        if distractor.rule is MistakeRule.NEAR_MISS:
            if not spec.min_value <= distractor.value <= spec.max_value:
                fail(FailureName.DISTRACTOR_OUT_OF_RANGE, f"{distractor.value}")
            elif not is_near_miss(distractor.value, answer, spec):
                fail(
                    FailureName.DISTRACTOR_RULE_MISMATCH,
                    f"{distractor.value} is not a near miss of {answer}",
                )
            expected_pattern = None
        else:
            if not 0 <= distractor.value <= spec.option_max:
                fail(FailureName.DISTRACTOR_OUT_OF_RANGE, f"{distractor.value}")
            expected = distractor_value(distractor.rule, view, spec)
            if expected != distractor.value:
                fail(
                    FailureName.DISTRACTOR_RULE_MISMATCH,
                    f"{distractor.rule.value} gives {expected}, not {distractor.value}",
                )
            link = catalog.link_for(distractor.rule, primary_topic_id)
            expected_pattern = link.error_pattern_id if link else None
        if distractor.error_pattern_id != expected_pattern:
            fail(
                FailureName.DISTRACTOR_PATTERN_MISMATCH,
                f"{distractor.rule.value} carries {distractor.error_pattern_id}, "
                f"expected {expected_pattern}",
            )

    # ---- hints ----
    if len(step.hints) != HINT_TIERS:
        fail(FailureName.HINT_COUNT, f"{len(step.hints)} hints, need {HINT_TIERS}")
    else:
        for tier, hint in enumerate(step.hints[:-1], start=1):
            if answer in written_numbers(hint):
                fail(FailureName.HINT_REVEALS_ANSWER, f"tier {tier} shows {answer}")
        if answer not in written_numbers(step.hints[-1]):
            fail(FailureName.HINT_MISSING_ANSWER, "the last hint must show the answer")
    return failures


def verify(
    puzzle: SumGridPuzzle,
    *,
    catalog: SumGridCatalog,
    topic_exists: Callable[[str], bool],
) -> VerificationResult:
    """Every way `puzzle` breaks the rules, by name. An empty list means it may be used.

    `topic_exists` answers whether a topic id is in the taxonomy database.
    """
    failures: list[Failure] = []
    spec = LEVELS.get(puzzle.level)
    if (
        spec is None
        or puzzle.puzzle_type != PUZZLE_TYPE
        or puzzle.generator_version != GENERATOR_VERSION
    ):
        return VerificationResult(
            [
                Failure(
                    FailureName.UNSUPPORTED_PUZZLE,
                    f"type {puzzle.puzzle_type}, version {puzzle.generator_version}, "
                    f"level {puzzle.level}",
                )
            ]
        )

    try:
        expected_id = make_sum_grid_id(puzzle.generator_version, puzzle.level, puzzle.seed)
    except ValueError:
        expected_id = None
    if puzzle.puzzle_id != expected_id:
        failures.append(
            Failure(FailureName.PUZZLE_ID_MISMATCH, f"{puzzle.puzzle_id} does not describe it")
        )

    # ---- the shape of the grid ----
    size = spec.size
    square = len(puzzle.cells) == size and all(len(row) == size for row in puzzle.cells)
    if (
        puzzle.size != size
        or not square
        or len(puzzle.row_targets) != size
        or len(puzzle.col_targets) != size
    ):
        # Nothing below makes sense on a grid of another shape.
        failures.append(
            Failure(FailureName.BAD_GRID, f"level {puzzle.level} needs a {size} by {size} grid")
        )
        return VerificationResult(failures)

    cells = puzzle.cells
    blanks = [(r, c) for r in range(size) for c in range(size) if cells[r][c] is None]
    for row in cells:
        for value in row:
            if value is not None and not spec.min_value <= value <= spec.max_value:
                failures.append(
                    Failure(
                        FailureName.VALUE_OUT_OF_RANGE,
                        f"{value} is outside {spec.min_value} to {spec.max_value}",
                    )
                )
    for target in (*puzzle.row_targets, *puzzle.col_targets):
        if not size * spec.min_value <= target <= spec.max_target:
            failures.append(Failure(FailureName.TARGET_OUT_OF_RANGE, f"a target of {target}"))

    # ---- where the blanks are ----
    if not spec.min_blanks <= len(blanks) <= spec.max_blanks:
        failures.append(
            Failure(
                FailureName.BAD_BLANK_COUNT,
                f"{len(blanks)} blanks, need {spec.min_blanks} to {spec.max_blanks}",
            )
        )
    for kind in ("row", "col"):
        for index in range(size):
            if all(cell in blanks for cell in _line_cells(kind, index, size)):
                failures.append(
                    Failure(
                        FailureName.LINE_WITHOUT_A_NUMBER,
                        f"{kind} {index} is blank from end to end",
                    )
                )

    # ---- the steps name the blanks, each once ----
    step_cells = [(step.cell.row, step.cell.col) for step in puzzle.steps]
    if sorted(step_cells) != blanks:
        failures.append(
            Failure(FailureName.BAD_STEPS, f"steps for {step_cells}, blanks at {blanks}")
        )
        return VerificationResult(failures)

    # ---- exactly one solution, and it is the stored one ----
    solutions = count_solutions(
        cells, puzzle.row_targets, puzzle.col_targets, spec.min_value, spec.max_value
    )
    stored: list[list[int]] = [[value or 0 for value in row] for row in cells]
    for step in puzzle.steps:
        stored[step.cell.row][step.cell.col] = step.answer
    if solutions.count == 0:
        failures.append(Failure(FailureName.NO_SOLUTION, "no numbers in range meet every target"))
    elif solutions.count > 1:
        failures.append(
            Failure(FailureName.MULTIPLE_SOLUTIONS, "more than one way to fill the blanks")
        )
    elif solutions.first != stored:
        failures.append(
            Failure(
                FailureName.WRONG_ANSWER,
                f"stored {[step.answer for step in puzzle.steps]}, the grid solves to "
                f"{[solutions.first[r][c] for r, c in step_cells] if solutions.first else None}",
            )
        )
    # The targets against the stored grid, whatever the search found.
    row_sums = [sum(row) for row in stored]
    col_sums = [sum(stored[r][c] for r in range(size)) for c in range(size)]
    if row_sums != puzzle.row_targets or col_sums != puzzle.col_targets:
        failures.append(
            Failure(
                FailureName.TARGET_MISMATCH,
                f"rows sum to {row_sums}, columns to {col_sums}; targets are "
                f"{puzzle.row_targets} and {puzzle.col_targets}",
            )
        )
    for step in puzzle.steps:
        if not spec.min_value <= step.answer <= spec.max_value:
            failures.append(Failure(FailureName.VALUE_OUT_OF_RANGE, f"an answer of {step.answer}"))

    # ---- no guessing: replay the stored order on what is known ----
    # The solution used from here on is the one the search found, where it
    # found exactly one; the stored answers are only compared with it above.
    solved = solutions.first if solutions.count == 1 and solutions.first else stored
    unknown = set(blanks)
    for index, step in enumerate(puzzle.steps):
        cell = (step.cell.row, step.cell.col)
        in_range = 0 <= step.line.index < size
        line = _line_cells(step.line.kind, step.line.index, size) if in_range else []
        still_unknown = [position for position in line if position in unknown]
        if still_unknown != [cell]:
            failures.append(
                Failure(
                    FailureName.NEEDS_A_GUESS,
                    f"{step.line.kind} {step.line.index} has unknowns at {still_unknown}, "
                    f"so {cell} cannot be worked out from it yet",
                    index,
                )
            )
            unknown.discard(cell)
            continue
        unknown.discard(cell)
        # What the child sees: this line's other cells, and the other line's target.
        row, col = cell
        if step.line.kind == "row":
            target, crossing = puzzle.row_targets[row], puzzle.col_targets[col]
        else:
            target, crossing = puzzle.col_targets[col], puzzle.row_targets[row]
        view = StepView(
            target=target,
            known_cells=tuple(solved[r][c] for r, c in line if (r, c) != cell),
            crossing_target=crossing,
        )
        failures += _check_options_and_hints(index, step, view, spec, catalog)

    expected_topics = step_topic_ids(puzzle.level)
    if puzzle.topic_ids != expected_topics:
        failures.append(
            Failure(FailureName.WRONG_TOPICS, f"{puzzle.topic_ids}, expected {expected_topics}")
        )
    for topic_id in puzzle.topic_ids:
        if not topic_exists(topic_id):
            failures.append(Failure(FailureName.UNKNOWN_TOPIC, f"{topic_id} is not a topic"))

    return VerificationResult(failures, nodes=solutions.nodes)
