"""Sum Grid: a small grid of numbers with a target for every row and column.

`SumGrid` is what the registry holds. The modules next to it are the puzzle
library itself: generator, independent verifier (which counts the solutions
and replays the solving order), mistake rules, diagnoser and hints.
"""

from app.puzzles.types.sum_grid.puzzle_type import SumGrid, SumGridParams

__all__ = ["SumGrid", "SumGridParams"]
