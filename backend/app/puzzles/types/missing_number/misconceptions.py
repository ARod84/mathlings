"""Which taxonomy error pattern each chain mistake rule corresponds to.

RULE_PATTERNS is the explicit, hand-reviewed mapping. How it is matched
against the real rows, and what a resolved catalog can answer, is shared by
every puzzle type: app/puzzles/core/catalog.py.

OFF_BY_ONE_* and PLACE_VALUE_SLIP are deliberately absent: the taxonomy has no
pattern that says the same thing, and a near match would mislead the tutor.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence

from app.puzzles.core.catalog import (
    MisconceptionResolutionError,
    PatternMatch,
    ResolvedPattern,
    RuleCatalog,
    error_pattern_key,
    resolve_rule_patterns,
)
from app.puzzles.types.missing_number.levels import TOPIC_MISSING_NUMBER, TOPIC_UNKNOWN_ADD_SUB
from app.puzzles.types.missing_number.models import MistakeRule
from app.taxonomy.schemas import ErrorPatternOut

__all__ = [
    "RULE_PATTERNS",
    "MisconceptionCatalog",
    "MisconceptionResolutionError",
    "PatternMatch",
    "ResolvedPattern",
    "error_pattern_key",
    "resolve_catalog",
]

RULE_PATTERNS: dict[MistakeRule, tuple[PatternMatch, ...]] = {
    MistakeRule.ADD_VISIBLE: (
        PatternMatch(TOPIC_UNKNOWN_ADD_SUB, "Adds the two visible numbers regardless of the box"),
        PatternMatch(TOPIC_MISSING_NUMBER, "Operator view of '='"),
    ),
    MistakeRule.ANSWER_LEFT_BACKWARDS: (
        PatternMatch(TOPIC_UNKNOWN_ADD_SUB, "Reads the answer-left form as backwards"),
    ),
    MistakeRule.POSITION_CONFUSION: (PatternMatch(TOPIC_MISSING_NUMBER, "Position confusion"),),
}


class MisconceptionCatalog(RuleCatalog[MistakeRule]):
    """The chain rules, resolved."""

    def __init__(self, links: Mapping[MistakeRule, Sequence[ResolvedPattern]]) -> None:
        super().__init__(links, MistakeRule)


def resolve_catalog(
    patterns_for_topic: Callable[[str], Iterable[ErrorPatternOut]],
) -> MisconceptionCatalog:
    """Match RULE_PATTERNS against real error-pattern rows. One lookup per topic."""
    return MisconceptionCatalog(resolve_rule_patterns(RULE_PATTERNS, patterns_for_topic))
