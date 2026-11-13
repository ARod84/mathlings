""" "Next in Line": a row of numbers that follows a pattern, with one or two blanks.

`NumberSequences` is what the registry holds. The modules next to it are the
puzzle library itself: generator, independent verifier (which proves the
answer is the only one), mistake rules, diagnoser and hints.
"""

from app.puzzles.types.sequences.puzzle_type import NumberSequences, SequenceParams

__all__ = ["NumberSequences", "SequenceParams"]
