"""Works out which known mistake produced a child's wrong answer to a blank.

    diagnose(puzzle, step_index, child_answer, catalog=..., step_back=...) -> Diagnosis

Every mistake rule is recomputed on the blank and compared with the answer.
Several rules can give the same number, so all that match are returned, the
ones with a taxonomy error pattern first. An answer no rule explains is
reported as unrecognized: that is a normal outcome, and no match is forced.
"""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.puzzles.core.catalog import explain
from app.puzzles.types.sum_grid.levels import LEVELS
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog
from app.puzzles.types.sum_grid.models import MistakeRule, SumGridPuzzle
from app.puzzles.types.sum_grid.rules import RULES, rule_output, step_view


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
    puzzle: SumGridPuzzle,
    step_index: int,
    child_answer: int,
    *,
    catalog: SumGridCatalog,
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

    spec = LEVELS[puzzle.level]
    view = step_view(puzzle, step_index)
    matched = [rule for rule in RULES if rule_output(rule, view, spec) == child_answer]
    if not matched:
        return Diagnosis(correct=False, unrecognized=True)

    # A step practises both of its level's topics, and a pattern on either
    # one names where to step back to (TENS_AS_ONES is on the second).
    explained = explain(
        matched,
        catalog=catalog,
        primary_topic_id=spec.topic_ids[0],
        topic_ids=spec.topic_ids,
        step_back=step_back,
    )
    return Diagnosis(
        correct=False,
        matched_rules=explained.matched_rules,
        error_pattern_id=explained.error_pattern_id,
        reteach_topic_id=explained.reteach_topic_id,
    )
