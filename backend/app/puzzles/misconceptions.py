"""Which taxonomy error pattern each mistake rule corresponds to.

RULE_PATTERNS is the explicit, hand-reviewed mapping. It names each pattern by
its topic and the opening words of its text, because the taxonomy gives error
patterns no id of their own. `resolve_catalog` matches those against the real
rows once, at startup, and fails loudly if a pattern is missing or matches
more than one row, for example after the pinned taxonomy commit changes.

An error pattern's id here is "<topic id>#<position>", the pair the
error_pattern table is unique on. It is the same in every database built from
the same taxonomy commit, unlike the table's auto-increment id.

OFF_BY_ONE_* and PLACE_VALUE_SLIP are deliberately absent: the taxonomy has no
pattern that says the same thing, and a near match would mislead the tutor.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.puzzles.levels import TOPIC_MISSING_NUMBER, TOPIC_UNKNOWN_ADD_SUB
from app.puzzles.models import MistakeRule
from app.taxonomy.schemas import ErrorPatternOut


@dataclass(frozen=True)
class PatternMatch:
    topic_id: str
    # The error pattern on that topic whose text starts with this.
    starts_with: str


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


@dataclass(frozen=True)
class ResolvedPattern:
    error_pattern_id: str
    topic_id: str
    pattern: str
    next_move: str
    reteach_topic_id: str | None


class MisconceptionResolutionError(Exception):
    """RULE_PATTERNS does not line up with the error patterns in the database."""


def error_pattern_key(topic_id: str, position: int) -> str:
    return f"{topic_id}#{position}"


class MisconceptionCatalog:
    """The resolved mapping: for each rule, the real error patterns it stands for."""

    def __init__(self, links: Mapping[MistakeRule, Sequence[ResolvedPattern]]) -> None:
        self._links = {rule: tuple(patterns) for rule, patterns in links.items()}
        self._by_id = {
            pattern.error_pattern_id: pattern
            for patterns in self._links.values()
            for pattern in patterns
        }

    def link_for(self, rule: MistakeRule, primary_topic_id: str) -> ResolvedPattern | None:
        """The pattern for a rule: the one on the puzzle's primary topic if there is
        one, otherwise the rule's pattern on another topic (same mistake, other level)."""
        patterns = self._links.get(rule, ())
        for pattern in patterns:
            if pattern.topic_id == primary_topic_id:
                return pattern
        return patterns[0] if patterns else None

    def get(self, error_pattern_id: str) -> ResolvedPattern | None:
        return self._by_id.get(error_pattern_id)

    def is_linked(self, rule: MistakeRule) -> bool:
        return bool(self._links.get(rule))

    def table(self) -> list[tuple[MistakeRule, ResolvedPattern | None]]:
        """Every rule with each of its patterns, or None where it has none. For reports."""
        rows: list[tuple[MistakeRule, ResolvedPattern | None]] = []
        for rule in MistakeRule:
            patterns = self._links.get(rule, ())
            rows.extend((rule, pattern) for pattern in patterns)
            if not patterns:
                rows.append((rule, None))
        return rows


def resolve_catalog(
    patterns_for_topic: Callable[[str], Iterable[ErrorPatternOut]],
) -> MisconceptionCatalog:
    """Match RULE_PATTERNS against real error-pattern rows. One lookup per topic."""
    rows_by_topic: dict[str, list[ErrorPatternOut]] = {}
    links: dict[MistakeRule, list[ResolvedPattern]] = {}
    for rule, matches in RULE_PATTERNS.items():
        for match in matches:
            if match.topic_id not in rows_by_topic:
                rows_by_topic[match.topic_id] = list(patterns_for_topic(match.topic_id))
            found = [
                row
                for row in rows_by_topic[match.topic_id]
                if row.pattern.startswith(match.starts_with)
            ]
            if len(found) != 1:
                raise MisconceptionResolutionError(
                    f"{rule.value}: expected exactly one error pattern on {match.topic_id} "
                    f"starting with {match.starts_with!r}, found {len(found)}"
                )
            row = found[0]
            links.setdefault(rule, []).append(
                ResolvedPattern(
                    error_pattern_id=error_pattern_key(match.topic_id, row.position),
                    topic_id=match.topic_id,
                    pattern=row.pattern,
                    next_move=row.next_move,
                    reteach_topic_id=(
                        row.reteach_prerequisite.id if row.reteach_prerequisite else None
                    ),
                )
            )
    return MisconceptionCatalog(links)
