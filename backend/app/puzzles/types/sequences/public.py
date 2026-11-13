"""The child-facing view of a sequence: the row and the options, no answers, rules or hints."""

from app.puzzles.core.options import shuffled_options
from app.puzzles.types.sequences.models import SequencePuzzle
from app.puzzles.types.sequences.schemas import SequencePublic, SequenceStepPublic


def to_public(puzzle: SequencePuzzle) -> SequencePublic:
    blanks = set(puzzle.blanks)
    return SequencePublic(
        puzzle_id=puzzle.puzzle_id,
        level=puzzle.level,
        length=len(puzzle.steps),
        topic_ids=list(puzzle.topic_ids),
        terms=[None if position in blanks else term for position, term in enumerate(puzzle.terms)],
        steps=[
            SequenceStepPublic(
                index=index,
                position=step.position,
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
