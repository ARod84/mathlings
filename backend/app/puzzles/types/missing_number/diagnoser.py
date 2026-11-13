"""Works out which known mistake produced a child's wrong answer.

    diagnose(puzzle, step_index, child_answer, catalog=..., step_back=...) -> Diagnosis

Every mistake rule is recomputed on the step and compared with the answer.
Several rules can give the same number, so all that match are returned, the
ones with a taxonomy error pattern first. An answer no rule explains is
reported as unrecognized: that is a normal outcome, and no match is forced.
"""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.puzzles.types.missing_number.levels import LEVELS
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog
from app.puzzles.types.missing_number.models import MistakeRule, Puzzle
from app.puzzles.types.missing_number.rules import RULES, rule_output


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
    puzzle: Puzzle,
    step_index: int,
    child_answer: int,
    *,
    catalog: MisconceptionCatalog,
    step_back: Callable[[str], str | None],
) -> Diagnosis:
    """Diagnose one answer to one step.

    `step_back(topic_id)` returns the best topic to step back to from a topic,
    or None; pass `first_step_back(service)` to use the prerequisite graph.
    It is only called when a mistake is recognized and its error pattern does
    not name a topic to reteach.
    """
    step = puzzle.steps[step_index]
    if child_answer == step.answer:
        return Diagnosis(correct=True)

    spec = LEVELS[puzzle.level]
    matched = [rule for rule in RULES if rule_output(rule, step, spec) == child_answer]
    if not matched:
        return Diagnosis(correct=False, unrecognized=True)

    # Stable sort: linked rules move to the front, each group keeps rule order.
    matched.sort(key=lambda rule: not catalog.is_linked(rule))
    pattern = next(
        (
            link
            for rule in matched
            if (link := catalog.link_for(rule, spec.primary_topic_id)) is not None
        ),
        None,
    )
    # A pattern written for another level's topic names a reteach topic for
    # that level, so it is only followed when it belongs to this puzzle's topic.
    reteach = (
        pattern.reteach_topic_id
        if pattern is not None and pattern.topic_id == spec.primary_topic_id
        else None
    )
    return Diagnosis(
        correct=False,
        matched_rules=matched,
        error_pattern_id=pattern.error_pattern_id if pattern else None,
        reteach_topic_id=reteach or step_back(spec.primary_topic_id),
    )
