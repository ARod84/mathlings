"""Which taxonomy error pattern each mistake rule of a puzzle type corresponds to.

A puzzle type declares an explicit, hand-reviewed mapping from its mistake
rules to patterns, naming each pattern by its topic and the opening words of
its text, because the taxonomy gives error patterns no id of their own.
`resolve_rule_patterns` matches those against the real rows once, when the
type is loaded, and fails loudly if a pattern is missing or matches more than
one row, for example after the pinned taxonomy commit changes.

An error pattern's id here is "<topic id>#<position>", the pair the
error_pattern table is unique on. It is the same in every database built from
the same taxonomy commit, unlike the table's auto-increment id.

A rule with no entry is simply unlinked. That is the right answer whenever the
taxonomy has no pattern that says the same thing: a near match would mislead
the tutor.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.taxonomy.schemas import ErrorPatternOut


@dataclass(frozen=True)
class PatternMatch:
    topic_id: str
    # The error pattern on that topic whose text starts with this.
    starts_with: str


@dataclass(frozen=True)
class ResolvedPattern:
    error_pattern_id: str
    topic_id: str
    pattern: str
    next_move: str
    reteach_topic_id: str | None


class MisconceptionResolutionError(Exception):
    """A rule mapping does not line up with the error patterns in the database."""


def error_pattern_key(topic_id: str, position: int) -> str:
    return f"{topic_id}#{position}"


class RuleCatalog[RuleT: StrEnum]:
    """The resolved mapping: for each rule, the real error patterns it stands for."""

    def __init__(
        self, links: Mapping[RuleT, Sequence[ResolvedPattern]], rules: Iterable[RuleT]
    ) -> None:
        # Every rule of the type, linked or not, in the type's own order. For reports.
        self._rules = tuple(rules)
        self._links = {rule: tuple(patterns) for rule, patterns in links.items()}
        self._by_id = {
            pattern.error_pattern_id: pattern
            for patterns in self._links.values()
            for pattern in patterns
        }

    def link_for(self, rule: RuleT, primary_topic_id: str) -> ResolvedPattern | None:
        """The pattern for a rule: the one on the step's primary topic if there is
        one, otherwise the rule's pattern on another topic (same mistake, other level)."""
        patterns = self._links.get(rule, ())
        for pattern in patterns:
            if pattern.topic_id == primary_topic_id:
                return pattern
        return patterns[0] if patterns else None

    def get(self, error_pattern_id: str) -> ResolvedPattern | None:
        return self._by_id.get(error_pattern_id)

    def is_linked(self, rule: RuleT) -> bool:
        return bool(self._links.get(rule))

    def table(self) -> list[tuple[RuleT, ResolvedPattern | None]]:
        """Every rule with each of its patterns, or None where it has none. For reports."""
        rows: list[tuple[RuleT, ResolvedPattern | None]] = []
        for rule in self._rules:
            patterns = self._links.get(rule, ())
            rows.extend((rule, pattern) for pattern in patterns)
            if not patterns:
                rows.append((rule, None))
        return rows


def resolve_rule_patterns[RuleT: StrEnum](
    rule_patterns: Mapping[RuleT, Sequence[PatternMatch]],
    patterns_for_topic: Callable[[str], Iterable[ErrorPatternOut]],
) -> dict[RuleT, list[ResolvedPattern]]:
    """Match a rule mapping against real error-pattern rows. One lookup per topic."""
    rows_by_topic: dict[str, list[ErrorPatternOut]] = {}
    links: dict[RuleT, list[ResolvedPattern]] = {}
    for rule, matches in rule_patterns.items():
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
    return links


@dataclass(frozen=True)
class Explanation[RuleT: StrEnum]:
    """What the catalog says about a wrong answer that some rules produce."""

    # The matching rules, the ones with a taxonomy error pattern first.
    matched_rules: list[RuleT]
    # The error pattern of the first linked rule, if any matched.
    error_pattern_id: str | None
    # Where to step back to.
    reteach_topic_id: str | None


def explain[RuleT: StrEnum](
    matched: Sequence[RuleT],
    *,
    catalog: RuleCatalog[RuleT],
    primary_topic_id: str,
    step_back: Callable[[str], str | None],
    topic_ids: Sequence[str] = (),
) -> Explanation[RuleT]:
    """Order the rules that give a wrong answer, and say where to step back to.

    `matched` is every rule that gives exactly the child's answer, in the
    type's rule order; it must not be empty. `topic_ids` are the topics the
    step practises, if it has more than its primary one. `step_back(topic_id)`
    is only called when no pattern on one of the step's own topics names a
    topic to reteach.
    """
    own_topics = {primary_topic_id, *topic_ids}
    # Stable sort: linked rules move to the front, each group keeps rule order.
    ordered = sorted(matched, key=lambda rule: not catalog.is_linked(rule))
    pattern = next(
        (
            link
            for rule in ordered
            if (link := catalog.link_for(rule, primary_topic_id)) is not None
        ),
        None,
    )
    # A pattern written for another level's topic names a reteach topic for
    # that level, so it is only followed when it belongs to one of this step's topics.
    reteach = (
        pattern.reteach_topic_id if pattern is not None and pattern.topic_id in own_topics else None
    )
    return Explanation(
        matched_rules=ordered,
        error_pattern_id=pattern.error_pattern_id if pattern else None,
        reteach_topic_id=reteach or step_back(primary_topic_id),
    )
