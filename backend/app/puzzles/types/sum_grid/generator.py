"""Builds a Sum Grid from a seed. Reproducible, and nothing else.

    generate(seed, level, catalog) -> SumGridPuzzle

The same inputs and GENERATOR_VERSION always give the same puzzle: all
randomness comes from one local random.Random(seed). Bump GENERATOR_VERSION in
levels.py whenever a change here (or in rules, hints or levels) can alter the
output for an existing seed.

This module does not check its own work, and it does not count solutions:
verifier.py does that, separately, and generate_verified
(app/puzzles/core/verified.py) puts the two together. A seed that cannot be
completed raises GenerationError.

How a puzzle is built:

1. A full grid: every cell a number in the level's range, every row and
   column sum within the level's largest target.
2. The blanks. Every way of blanking the level's number of cells is listed,
   and kept if every row and column still shows a number, if a deduction
   order exists, and if no blank's second hint would have to quote its answer.
   One of those is picked by the seed.
3. The deduction order (`deduction_order`): at each step, the first blank in
   reading order that is the only unknown in its row or in its column. If
   both lines work, the row is the one recorded. The order is stored with the
   puzzle, each step with the line it is solved from.
4. Each blank then gets its three wrong options and its hints.

Level 3 has a preference on top (never a requirement): among the ways of
blanking, the ones where most steps have a multiple of ten among the known
cells of their line, so the TENS_AS_ONES mistake has something to act on.
"""

import random
from itertools import combinations

from app.puzzles.core import GenerationError
from app.puzzles.core.ids import MAX_SEED
from app.puzzles.types.sum_grid.hints import build_hints, quoted_numbers
from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import (
    DISTRACTORS_PER_STEP,
    GENERATOR_VERSION,
    LEVELS,
    LevelSpec,
    step_topic_ids,
)
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog
from app.puzzles.types.sum_grid.models import (
    Cell,
    Distractor,
    HintSource,
    Line,
    MistakeRule,
    SumGridPuzzle,
    SumGridStep,
)
from app.puzzles.types.sum_grid.rules import StepView, distractor_value

# The order mistake rules are tried in within a tier. _distractors puts the
# rules that have a taxonomy error pattern ahead of the ones that do not.
DISTRACTOR_RULE_ORDER: tuple[MistakeRule, ...] = (
    MistakeRule.ADD_VISIBLE,
    MistakeRule.FORGOT_ONE,
    MistakeRule.PLACE_VALUE_SLIP,
    MistakeRule.CARRY_DROPPED,
    MistakeRule.TENS_AS_ONES,
    MistakeRule.WRONG_LINE,
    MistakeRule.OFF_BY_ONE_OVER,
    MistakeRule.OFF_BY_ONE_UNDER,
)
# How many full grids are drawn before the seed is given up on. A level-3
# grid needs every line to stay within 100, which most random grids do not.
GRID_DRAWS = 300
# How many grids are tried for one that has a usable set of blanks.
BLANK_DRAWS = 20

Position = tuple[int, int]
Order = list[tuple[Position, Line]]


def _full_grid(rng: random.Random, spec: LevelSpec) -> list[list[int]] | None:
    """A grid with every cell in range and every line within the largest target."""
    size = spec.size
    tens = [value for value in range(spec.min_value, spec.max_value + 1) if value % 10 == 0]

    def cell() -> int:
        if tens and rng.random() < spec.tens_share:
            return rng.choice(tens)
        return rng.randint(spec.min_value, spec.max_value)

    for _ in range(GRID_DRAWS):
        grid = [[cell() for _ in range(size)] for _ in range(size)]
        rows = [sum(row) for row in grid]
        cols = [sum(grid[r][c] for r in range(size)) for c in range(size)]
        if max(*rows, *cols) <= spec.max_target:
            return grid
    return None


def deduction_order(size: int, blanks: frozenset[Position]) -> Order | None:
    """An order in which every blank is the only unknown in one of its lines, or None.

    At each step: the first blank in reading order that can be worked out, from
    its row if the row has no other unknown, otherwise from its column.
    """
    unknown = set(blanks)
    order: Order = []
    while unknown:
        for row, col in sorted(unknown):
            if not any((row, c) in unknown for c in range(size) if c != col):
                line = Line(kind="row", index=row)
            elif not any((r, col) in unknown for r in range(size) if r != row):
                line = Line(kind="col", index=col)
            else:
                continue
            order.append(((row, col), line))
            unknown.remove((row, col))
            break
        else:
            return None
    return order


def _views(grid: list[list[int]], order: Order) -> list[StepView]:
    """What the child sees at each step. Earlier blanks are known by then."""
    size = len(grid)
    views = []
    for (row, col), line in order:
        if line.kind == "row":
            known = tuple(grid[row][c] for c in range(size) if c != col)
            target = sum(grid[row])
            crossing = sum(grid[r][col] for r in range(size))
        else:
            known = tuple(grid[r][col] for r in range(size) if r != row)
            target = sum(grid[r][col] for r in range(size))
            crossing = sum(grid[row])
        views.append(StepView(target=target, known_cells=known, crossing_target=crossing))
    return views


def _blank_choices(spec: LevelSpec, grid: list[list[int]], count: int) -> list[tuple[Order, int]]:
    """Every allowed way to blank `count` cells, each with its order and its tens score."""
    size = spec.size
    cells = [(row, col) for row in range(size) for col in range(size)]
    choices: list[tuple[Order, int]] = []
    for chosen in combinations(cells, count):
        blanks = frozenset(chosen)
        # Every row and every column keeps a visible number.
        if any(all((line, i) in blanks for i in range(size)) for line in range(size)):
            continue
        if any(all((i, line) in blanks for i in range(size)) for line in range(size)):
            continue
        order = deduction_order(size, blanks)
        if order is None:
            continue
        views = _views(grid, order)
        # The second hint quotes these; the answer may not be one of them.
        if any(
            view.answer in quoted_numbers(line, size, view)
            for (_cell, line), view in zip(order, views, strict=True)
        ):
            continue
        with_tens = sum(any(cell % 10 == 0 for cell in view.known_cells) for view in views)
        choices.append((order, with_tens))
    return choices


def _distractors(
    rng: random.Random, spec: LevelSpec, catalog: SumGridCatalog, view: StepView
) -> list[Distractor] | None:
    """Three wrong answers for a blank, the most diagnosable first.

    1. mistake rules with a taxonomy error pattern: first the ones whose
       pattern is on one of this level's own topics, then the ones whose
       pattern belongs to another level's topic
    2. the other mistake rules
    3. NEAR_MISS fillers, only if the first two leave a slot empty

    Within a tier the order is fixed (DISTRACTOR_RULE_ORDER); the fillers are
    picked by the seed. The split of tier 1 matters at level 3, where five
    linked rules compete for three slots: the place-value mistakes, which are
    what the level is about, go before the ones borrowed from easier topics.
    """
    answer = view.answer
    primary_topic_id = spec.topic_ids[0]

    def tier(rule: MistakeRule) -> int:
        link = catalog.link_for(rule, primary_topic_id)
        if link is None:
            return 2
        return 0 if link.topic_id in spec.topic_ids else 1

    chosen: list[Distractor] = []
    used = {answer}
    # sorted() is stable, so each tier keeps DISTRACTOR_RULE_ORDER.
    for rule in sorted(DISTRACTOR_RULE_ORDER, key=tier):
        if len(chosen) == DISTRACTORS_PER_STEP:
            break
        value = distractor_value(rule, view, spec)
        if value is None or value in used:
            continue
        link = catalog.link_for(rule, primary_topic_id)
        chosen.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)

    if len(chosen) < DISTRACTORS_PER_STEP:
        near = [answer + sign * offset for offset in spec.near_miss_offsets for sign in (-1, 1)]
        near = [
            value
            for value in near
            if spec.min_value <= value <= spec.max_value and value not in used
        ]
        rng.shuffle(near)
        for value in near[: DISTRACTORS_PER_STEP - len(chosen)]:
            chosen.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
    return chosen if len(chosen) == DISTRACTORS_PER_STEP else None


def generate(seed: int, level: int, catalog: SumGridCatalog) -> SumGridPuzzle:
    """One puzzle for this exact seed. Raises GenerationError if the seed cannot work."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}; choose from {sorted(LEVELS)}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")

    spec = LEVELS[level]
    size = spec.size
    rng = random.Random(seed)
    count = rng.randint(spec.min_blanks, spec.max_blanks)

    # A grid can turn out to have no usable blanks: at level 1 a row that is a
    # double (6 + 6) cannot be asked about. Then another grid is drawn, from
    # the same seed, before the seed is given up on.
    choices: list[tuple[Order, int]] = []
    for _ in range(BLANK_DRAWS):
        grid = _full_grid(rng, spec)
        if grid is None:
            raise GenerationError(f"seed {seed}, level {level}: no grid within the target limit")
        choices = _blank_choices(spec, grid, count)
        if choices:
            break
    if not choices:
        raise GenerationError(f"seed {seed}, level {level}: no way to blank {count} cells")
    if spec.tens_as_ones_rule:
        # A preference: keep the ways where most steps have a multiple of ten to misread.
        best = max(score for _order, score in choices)
        choices = [choice for choice in choices if choice[1] == best]
    order, _score = rng.choice(choices)

    steps: list[SumGridStep] = []
    for ((row, col), line), view in zip(order, _views(grid, order), strict=True):
        distractors = _distractors(rng, spec, catalog, view)
        if distractors is None:
            raise GenerationError(
                f"seed {seed}, level {level}: not enough wrong options for {view.answer}"
            )
        sources: dict[str, HintSource] = {}
        for distractor in distractors:
            pattern = catalog.get(distractor.error_pattern_id or "")
            if pattern is not None:
                sources[pattern.error_pattern_id] = HintSource(
                    error_pattern_id=pattern.error_pattern_id, next_move=pattern.next_move
                )
        steps.append(
            SumGridStep(
                cell=Cell(row=row, col=col),
                line=line,
                answer=grid[row][col],
                distractors=distractors,
                hints=build_hints(line, size, view),
                hint_source=list(sources.values()),
            )
        )

    blanks = {position for position, _line in order}
    return SumGridPuzzle(
        puzzle_id=make_sum_grid_id(GENERATOR_VERSION, level, seed),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        size=size,
        cells=[
            [None if (row, col) in blanks else grid[row][col] for col in range(size)]
            for row in range(size)
        ],
        row_targets=[sum(row) for row in grid],
        col_targets=[sum(grid[r][c] for r in range(size)) for c in range(size)],
        steps=steps,
        topic_ids=step_topic_ids(level),
    )
