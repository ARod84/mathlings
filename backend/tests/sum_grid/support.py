"""Helpers for the Sum Grid tests: a catalog that needs no database, and hand-built grids."""

from app.puzzles.types.sum_grid.hints import build_hints
from app.puzzles.types.sum_grid.ids import make_sum_grid_id
from app.puzzles.types.sum_grid.levels import (
    GENERATOR_VERSION,
    LEVELS,
    TOPIC_ADD_SUBTRACT_7,
    TOPIC_ADDING_WITHIN_100,
    TOPIC_FLUENT_WITHIN_20,
    TOPIC_THREE_SMALL_NUMBERS,
    TOPIC_UNKNOWN_ADD_SUB,
    step_topic_ids,
)
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog, resolve_catalog
from app.puzzles.types.sum_grid.models import (
    Cell,
    Distractor,
    Line,
    MistakeRule,
    SumGridPuzzle,
    SumGridStep,
)
from app.puzzles.types.sum_grid.rules import StepView, distractor_value
from app.taxonomy.schemas import ErrorPatternOut
from tests.puzzles.support import _row

TOPIC_EQUALS_SIGN = "mt_oIzycTBeE4"
TOPIC_WITHIN_1000 = "mt_ewmuMMPAzP"
TOPIC_TWO_DIGITS = "mt_THl9GLxwoL"
TOPIC_BONDS_TO_9 = "mt_e8CZ7E5qW7"
TOPIC_GROUPING = "mt_T76hKqXf0z"
TOPIC_WITHIN_20 = "mt_m1W6nTQJ2b"

KNOWN_TOPICS = {
    TOPIC_FLUENT_WITHIN_20,
    TOPIC_UNKNOWN_ADD_SUB,
    TOPIC_THREE_SMALL_NUMBERS,
    TOPIC_ADD_SUBTRACT_7,
    TOPIC_ADDING_WITHIN_100,
    TOPIC_EQUALS_SIGN,
    TOPIC_WITHIN_1000,
    TOPIC_TWO_DIGITS,
    TOPIC_BONDS_TO_9,
    TOPIC_GROUPING,
    TOPIC_WITHIN_20,
}

# The opening words and the positions are copied from the real taxonomy rows
# (pinned commit). Every pattern of each topic is here, in order.
ERROR_PATTERN_ROWS: dict[str, list[ErrorPatternOut]] = {
    TOPIC_UNKNOWN_ADD_SUB: [
        _row(
            0,
            "Adds the two visible numbers regardless of the box's position",
            TOPIC_EQUALS_SIGN,
            "Model on a bar: 11 is the whole, 8 a part.",
        ),
        _row(1, "Reads the answer-left form as backwards", TOPIC_EQUALS_SIGN, "Balance model."),
        _row(2, "Solves only by slow trial-and-error", None, "Prompt the inverse."),
    ],
    TOPIC_THREE_SMALL_NUMBERS: [
        _row(0, "Adds strictly left-to-right", TOPIC_BONDS_TO_9, "Scan for a ten first."),
        _row(1, "'You have to add them in the order", TOPIC_GROUPING, "Any two may go first."),
        _row(
            2,
            "Makes ten with a pair but then loses or double-counts the third addend.",
            None,
            "Physically set the third tile aside and bring it in last.",
        ),
    ],
    TOPIC_ADD_SUBTRACT_7: [
        _row(0, "Place-value misalignment", TOPIC_WITHIN_1000, "Provide a column grid."),
        _row(
            1,
            "Smaller-from-larger — in 502−276 does 6−2 in the ones",
            TOPIC_WITHIN_1000,
            "Return to concrete decomposition.",
        ),
        _row(2, "Carry omitted or misplaced — in 347+185", None, "Write the carried digit."),
        _row(3, "Borrow-across-zero", TOPIC_WITHIN_1000, "Model the cascade."),
    ],
    TOPIC_ADDING_WITHIN_100: [
        _row(
            0,
            "Treats a multiple of ten as ones — 'thirty-eight plus forty is forty-two'",
            TOPIC_TWO_DIGITS,
            "Rebuild with ten-rods: forty is four tens.",
        ),
        _row(1, "Doesn't bridge the ten", TOPIC_WITHIN_20, "Make-ten on a bead string."),
        _row(2, "Counts on in ones by finger or tally", None, "Do NOT ban the counting."),
    ],
}

# Where the prerequisite graph steps back to, for a topic whose pattern names nowhere.
STEP_BACK = {
    TOPIC_FLUENT_WITHIN_20: TOPIC_WITHIN_20,
    TOPIC_THREE_SMALL_NUMBERS: TOPIC_GROUPING,
    TOPIC_ADD_SUBTRACT_7: TOPIC_WITHIN_1000,
}


def make_catalog() -> SumGridCatalog:
    return resolve_catalog(lambda topic_id: ERROR_PATTERN_ROWS[topic_id])


def topic_exists(topic_id: str) -> bool:
    return topic_id in KNOWN_TOPICS


def step_back(topic_id: str) -> str | None:
    return STEP_BACK.get(topic_id)


# Rules with a pattern on the level's own topics first, then other linked
# rules, then the rest: the order options are filled in.
_RULE_ORDER = (
    MistakeRule.ADD_VISIBLE,
    MistakeRule.FORGOT_ONE,
    MistakeRule.PLACE_VALUE_SLIP,
    MistakeRule.CARRY_DROPPED,
    MistakeRule.TENS_AS_ONES,
    MistakeRule.WRONG_LINE,
    MistakeRule.OFF_BY_ONE_OVER,
    MistakeRule.OFF_BY_ONE_UNDER,
)

# Written out by hand: a blank is given as (row, column, "row" or "col").
Blank = tuple[int, int, str]


def view_for(grid: list[list[int]], row: int, col: int, kind: str) -> StepView:
    """What the child sees for one blank, worked out here and not by the library."""
    size = len(grid)
    row_target = sum(grid[row])
    col_target = sum(grid[r][col] for r in range(size))
    if kind == "row":
        known = tuple(grid[row][c] for c in range(size) if c != col)
        return StepView(target=row_target, known_cells=known, crossing_target=col_target)
    known = tuple(grid[r][col] for r in range(size) if r != row)
    return StepView(target=col_target, known_cells=known, crossing_target=row_target)


def make_step(grid: list[list[int]], blank: Blank, *, level: int) -> SumGridStep:
    """A blank with valid hints and distractors, built by hand from the full grid."""
    spec = LEVELS[level]
    catalog = make_catalog()
    row, col, kind = blank
    view = view_for(grid, row, col, kind)
    line = Line(kind=kind, index=row if kind == "row" else col)

    def tier(rule: MistakeRule) -> int:
        link = catalog.link_for(rule, spec.topic_ids[0])
        if link is None:
            return 2
        return 0 if link.topic_id in spec.topic_ids else 1

    distractors: list[Distractor] = []
    used = {view.answer}
    for rule in sorted(_RULE_ORDER, key=tier):
        value = distractor_value(rule, view, spec)
        if value is None or value in used or len(distractors) == 3:
            continue
        link = catalog.link_for(rule, spec.topic_ids[0])
        distractors.append(
            Distractor(
                value=value, rule=rule, error_pattern_id=link.error_pattern_id if link else None
            )
        )
        used.add(value)
    for offset in spec.near_miss_offsets:
        for value in (view.answer + offset, view.answer - offset):
            if (
                len(distractors) < 3
                and spec.min_value <= value <= spec.max_value
                and value not in used
            ):
                distractors.append(Distractor(value=value, rule=MistakeRule.NEAR_MISS))
                used.add(value)
    return SumGridStep(
        cell=Cell(row=row, col=col),
        line=line,
        answer=grid[row][col],
        distractors=distractors,
        hints=build_hints(line, len(grid), view),
    )


def make_puzzle(
    grid: list[list[int]], blanks: list[Blank], *, level: int, seed: int = 7
) -> SumGridPuzzle:
    """A puzzle written by hand: the full grid, and the blanks in the order they are solved.

    Each blank's options and hints assume that the blanks before it in the
    list are already solved, which is what the stored order promises.
    """
    size = len(grid)
    hidden = {(row, col) for row, col, _kind in blanks}
    return SumGridPuzzle(
        puzzle_id=make_sum_grid_id(GENERATOR_VERSION, level, seed),
        generator_version=GENERATOR_VERSION,
        seed=seed,
        level=level,
        size=size,
        cells=[
            [None if (row, col) in hidden else grid[row][col] for col in range(size)]
            for row in range(size)
        ],
        row_targets=[sum(row) for row in grid],
        col_targets=[sum(grid[r][c] for r in range(size)) for c in range(size)],
        steps=[make_step(grid, blank, level=level) for blank in blanks],
        topic_ids=step_topic_ids(level),
    )


# ---- grids used across the tests ----

#  3 | □ |  9
#  □ | 5 |  7
#  5  11
SMALL = [[3, 6], [2, 5]]
SMALL_BLANKS: list[Blank] = [(0, 1, "row"), (1, 0, "row")]

#  □ | □ | 9 | 16
#  4 | □ | 8 | 15
#  7 | 6 | 1 | 14
# 13  14  18
MEDIUM = [[2, 5, 9], [4, 3, 8], [7, 6, 1]]
MEDIUM_BLANKS: list[Blank] = [(0, 0, "col"), (0, 1, "row"), (1, 1, "row")]

# 20 | 37 |  □ | 85
#  □ | 40 | 22 | 77
# 31 |  □ |  □ | 73
# 66   89   80
LARGE = [[20, 37, 28], [15, 40, 22], [31, 12, 30]]
LARGE_BLANKS: list[Blank] = [(0, 2, "row"), (1, 0, "row"), (2, 1, "col"), (2, 2, "row")]


def small() -> SumGridPuzzle:
    return make_puzzle(SMALL, SMALL_BLANKS, level=1)


def medium() -> SumGridPuzzle:
    return make_puzzle(MEDIUM, MEDIUM_BLANKS, level=2)


def large() -> SumGridPuzzle:
    return make_puzzle(LARGE, LARGE_BLANKS, level=3)
