"""The child-facing view of a chain: equations and options, no answers, rules or hint text."""

from app.puzzles.core.options import shuffled_options
from app.puzzles.types.missing_number.models import Equation, NumberToken, Puzzle
from app.puzzles.types.missing_number.schemas import LinkedToken, PuzzlePublic, PuzzleStepPublic


def linked_token(equation: Equation, link_position: int | None) -> LinkedToken | None:
    """Where the previous step's answer sits among the equation's tokens.

    `link_position` counts visible numbers in reading order (left side, then
    right); this turns it into a side and a token index on that side. It
    tells the browser nothing new: the number is already on show.
    """
    if link_position is None:
        return None
    seen = 0
    for side, tokens in (("left", equation.left), ("right", equation.right)):
        for index, token in enumerate(tokens):
            if not isinstance(token, NumberToken):
                continue
            if seen == link_position:
                return LinkedToken(side=side, index=index)
            seen += 1
    return None


def to_public(puzzle: Puzzle) -> PuzzlePublic:
    """The child-facing view: equations and options, no answers, rules or hint text."""
    return PuzzlePublic(
        puzzle_id=puzzle.puzzle_id,
        level=puzzle.level,
        length=len(puzzle.steps),
        topic_ids=list(puzzle.topic_ids),
        steps=[
            PuzzleStepPublic(
                index=index,
                equation=step.equation,
                options=shuffled_options(
                    puzzle.puzzle_id,
                    index,
                    [step.answer, *(distractor.value for distractor in step.distractors)],
                ),
                hint_tiers=len(step.hints),
                linked_token=linked_token(step.equation, step.link_position),
            )
            for index, step in enumerate(puzzle.steps)
        ],
    )
