"""The child-facing view of a Sum Grid: the grid, targets and options; no answers or rules."""

from app.puzzles.core.options import shuffled_options
from app.puzzles.types.sum_grid.models import SumGridPuzzle
from app.puzzles.types.sum_grid.schemas import SumGridPublic, SumGridStepPublic


def to_public(puzzle: SumGridPuzzle) -> SumGridPublic:
    return SumGridPublic(
        puzzle_id=puzzle.puzzle_id,
        level=puzzle.level,
        size=puzzle.size,
        length=len(puzzle.steps),
        topic_ids=list(puzzle.topic_ids),
        cells=[list(row) for row in puzzle.cells],
        row_targets=list(puzzle.row_targets),
        col_targets=list(puzzle.col_targets),
        steps=[
            SumGridStepPublic(
                index=index,
                cell=step.cell,
                line=step.line,
                options=shuffled_options(
                    puzzle.puzzle_id,
                    index,
                    [step.answer, *(distractor.value for distractor in step.distractors)],
                ),
                hint_tiers=len(step.hints),
            )
            for index, step in enumerate(puzzle.steps)
        ],
    )
