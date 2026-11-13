"""Works out which known mistake produced a child's wrong answer to a blank.

    diagnose(puzzle, step_index, child_answer, catalog=..., step_back=...) -> Diagnosis

Every mistake rule is recomputed on the blank and compared with the answer.
Several rules can give the same number (after 9, 6, 3, 0 both "dropped the
sign" and "went up instead of down" give 3), so all that match are returned,
the ones with a taxonomy error pattern first. An answer no rule explains is
reported as unrecognized: that is a normal outcome, and no match is forced.
"""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.puzzles.core.catalog import explain
from app.puzzles.types.sequences.levels import LEVELS
from app.puzzles.types.sequences.misconceptions import SequenceCatalog
from app.puzzles.types.sequences.models import MistakeRule, SequencePuzzle
from app.puzzles.types.sequences.rules import RULES, rule_output


class Diagnosis(BaseModel):
    model_config = ConfigDict(frozen=True)

    correct: bool
    # Every rule that gives exactly this answer; taxonomy-linked rules first.
    matched_rules: list[MistakeRule] = []
    # The error pattern of the first linked rule, if any matched.
    error_pattern_id: str | None = None
    # Where to step back to. None when the answer is right or unrecognized.
    reteach_topic_id: str | None = None
    # Wrong, and no known mistake explains it.
    unrecognized: bool = False


def diagnose(
    puzzle: SequencePuzzle,
    step_index: int,
    child_answer: int,
    *,
    catalog: SequenceCatalog,
    step_back: Callable[[str], str | None],
) -> Diagnosis:
    """Diagnose one answer to one blank.

    `step_back(topic_id)` returns the best topic to step back to from a topic,
    or None. It is only called when a mistake is recognized and its error
    pattern does not name a topic to reteach.
    """
    step = puzzle.steps[step_index]
    if child_answer == step.answer:
        return Diagnosis(correct=True)

    matched = [
        rule
        for rule in RULES
        if rule_output(rule, puzzle.terms, step.position, puzzle.kind) == child_answer
    ]
    if not matched:
        return Diagnosis(correct=False, unrecognized=True)

    # The step's primary topic depends on the kind of sequence (levels.py).
    explained = explain(
        matched,
        catalog=catalog,
        primary_topic_id=LEVELS[puzzle.level].topic_ids[puzzle.kind][0],
        step_back=step_back,
    )
    return Diagnosis(
        correct=False,
        matched_rules=explained.matched_rules,
        error_pattern_id=explained.error_pattern_id,
        reteach_topic_id=explained.reteach_topic_id,
    )
