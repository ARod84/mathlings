"""Missing Number Chains: each step is an equation with one number hidden.

`MissingNumberChains` is what the registry holds. The modules next to it are
the puzzle library itself: generator, independent verifier, mistake rules,
diagnoser and hints.
"""

from app.puzzles.types.missing_number.puzzle_type import MissingNumberChains, MissingNumberParams

__all__ = ["MissingNumberChains", "MissingNumberParams"]
