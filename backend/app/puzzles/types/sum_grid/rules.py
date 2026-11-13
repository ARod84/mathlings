"""Mistake rules: what a child who makes a known mistake would put in a blank.

Each rule is a pure function of a StepView: what the child is looking at when
they solve one blank. It returns the wrong answer the mistake produces, or
None when the mistake cannot happen there or happens to give the right answer.

A blank is solved from one line (a row or a column) in which it is the only
unknown. In the table, T is that line's target, the known cells are the other
cells of the line (visible, or solved earlier), K is their sum, and X is the
target of the other line through the blank. The right answer is T − K.

                        2×2 line            3×3 line
    example             3 + □ = 9           20 + 37 + □ = 85
    right answer        9 − 3 = 6           85 − 57 = 28
    ------------------  ------------------  --------------------------------
    ADD_VISIBLE         T + K       12      T + K                  142
    FORGOT_ONE          -                   T − larger known cell  85 − 37 = 48
    PLACE_VALUE_SLIP    -                   level 3: T ⊖ K         85 ⊖ 57 = 32
    CARRY_DROPPED       -                   level 3: T − (a ⊕ b)   - here; see below
    TENS_AS_ONES        -                   level 3: 20 read as 2  85 − 39 = 46
    WRONG_LINE          X − K, if ≥ 0       X − K, if ≥ 0
    OFF_BY_ONE_OVER     answer + 1, every line
    OFF_BY_ONE_UNDER    answer − 1, every line

    ⊖  column-by-column subtraction with no exchanging: in each column the
       smaller digit is taken from the larger.   85 ⊖ 57 = 32
    ⊕  column-by-column addition with the carries dropped.   28 ⊕ 37 = 55

Why the dashes and the conditions are there:

- ADD_VISIBLE is the taxonomy's "adds the visible numbers regardless of the
  box's position": the child sees numbers and a total, and adds them all.
- FORGOT_ONE needs two known cells, so a 3×3 line: the child takes away one of
  them and loses the other. The larger one is the one taken away, so the rule
  has one output.
- PLACE_VALUE_SLIP and CARRY_DROPPED are for level 3, where the numbers have
  two digits. They are the two places a column-by-column slip can be made, and
  the taxonomy has a pattern for each. PLACE_VALUE_SLIP is in the subtraction:
  T ⊖ K, "smaller from larger". It gives nothing where no column needs an
  exchange. CARRY_DROPPED is in adding the two known cells, a ⊕ b, followed by
  a correct subtraction: for 28 + 37 + □ = 99 the child makes 55 of the known
  cells and answers 44. It gives nothing where that sum has no carry (20 + 37
  above), and nothing on a line with one known cell.
- TENS_AS_ONES is for level 3, and needs a multiple of ten among the known
  cells: the child reads 20 as 2. The first such cell along the line is the
  one misread. The generator prefers lines that have one (levels.tens_share).
- WRONG_LINE uses the other line's target with this line's known cells. It
  gives nothing when that would go below zero, and nothing when both targets
  are the same.
- OFF_BY_ONE is two rules, one per direction, so that each rule has one output.

NEAR_MISS is not a mistake rule and has no function here: it is a filler value
a fixed distance from the answer (LevelSpec.near_miss_offsets).
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.puzzles.core.arithmetic import add_without_carry, subtract_without_exchange
from app.puzzles.types.sum_grid.levels import LevelSpec
from app.puzzles.types.sum_grid.models import MistakeRule, SumGridPuzzle


@dataclass(frozen=True)
class StepView:
    """One blank as the child meets it."""

    # The target of the line the blank is solved from.
    target: int
    # The other cells of that line, in order along it: visible or solved earlier.
    known_cells: tuple[int, ...]
    # The target of the other line through the blank.
    crossing_target: int

    @property
    def known(self) -> int:
        return sum(self.known_cells)

    @property
    def answer(self) -> int:
        return self.target - self.known


RuleFunction = Callable[[StepView, LevelSpec], int | None]


def add_visible(view: StepView, spec: LevelSpec) -> int | None:
    return view.target + view.known


def forgot_one(view: StepView, spec: LevelSpec) -> int | None:
    if len(view.known_cells) < 2:
        return None
    return view.target - max(view.known_cells)


def place_value_slip(view: StepView, spec: LevelSpec) -> int | None:
    if not spec.place_value_rule:
        return None
    return subtract_without_exchange(view.target, view.known)


def carry_dropped(view: StepView, spec: LevelSpec) -> int | None:
    if not spec.place_value_rule or len(view.known_cells) != 2:
        return None
    first, second = view.known_cells
    return view.target - add_without_carry(first, second)


def tens_as_ones(view: StepView, spec: LevelSpec) -> int | None:
    if not spec.tens_as_ones_rule:
        return None
    misread = next((cell for cell in view.known_cells if cell % 10 == 0 and cell > 0), None)
    if misread is None:
        return None
    return view.target - (view.known - misread + misread // 10)


def wrong_line(view: StepView, spec: LevelSpec) -> int | None:
    value = view.crossing_target - view.known
    return value if value >= 0 else None


def off_by_one_over(view: StepView, spec: LevelSpec) -> int | None:
    return view.answer + 1


def off_by_one_under(view: StepView, spec: LevelSpec) -> int | None:
    return view.answer - 1


RULES: dict[MistakeRule, RuleFunction] = {
    MistakeRule.ADD_VISIBLE: add_visible,
    MistakeRule.FORGOT_ONE: forgot_one,
    MistakeRule.PLACE_VALUE_SLIP: place_value_slip,
    MistakeRule.CARRY_DROPPED: carry_dropped,
    MistakeRule.TENS_AS_ONES: tens_as_ones,
    MistakeRule.WRONG_LINE: wrong_line,
    MistakeRule.OFF_BY_ONE_OVER: off_by_one_over,
    MistakeRule.OFF_BY_ONE_UNDER: off_by_one_under,
}


def rule_output(rule: MistakeRule, view: StepView, spec: LevelSpec) -> int | None:
    """What a child making this mistake would answer, or None.

    None when the rule does not apply to this line or this level, or when the
    mistake lands on the right answer. The value has no limit here: the
    diagnoser needs to see it. distractor_value applies the limits for options.
    """
    function = RULES.get(rule)
    if function is None:
        return None
    value = function(view, spec)
    if value is None or value == view.answer:
        return None
    return value


def distractor_value(rule: MistakeRule, view: StepView, spec: LevelSpec) -> int | None:
    """The rule's output if it can be offered as an answer option, else None.

    Stricter than rule_output only in that an option is never below zero and
    never above the level's option_max.
    """
    value = rule_output(rule, view, spec)
    if value is None or not 0 <= value <= spec.option_max:
        return None
    return value


def is_near_miss(value: int, answer: int, spec: LevelSpec) -> bool:
    """True if `value` is a valid NEAR_MISS filler for a blank whose answer is `answer`."""
    return (
        spec.min_value <= value <= spec.max_value
        and value != answer
        and abs(value - answer) in spec.near_miss_offsets
    )


def step_view(puzzle: SumGridPuzzle, step_index: int) -> StepView:
    """The view of one step of a stored puzzle, with the earlier steps' answers filled in.

    For the diagnoser, which answers for a puzzle that has already been
    verified. The verifier does not use this: it builds its views from the
    grid it solved itself.
    """
    grid = [list(row) for row in puzzle.cells]
    for earlier in puzzle.steps[:step_index]:
        grid[earlier.cell.row][earlier.cell.col] = earlier.answer
    step = puzzle.steps[step_index]
    row, col = step.cell.row, step.cell.col
    if step.line.kind == "row":
        line = [grid[row][c] for c in range(puzzle.size) if c != col]
        target, crossing = puzzle.row_targets[row], puzzle.col_targets[col]
    else:
        line = [grid[r][col] for r in range(puzzle.size) if r != row]
        target, crossing = puzzle.col_targets[col], puzzle.row_targets[row]
    return StepView(
        target=target,
        known_cells=tuple(value for value in line if value is not None),
        crossing_target=crossing,
    )
