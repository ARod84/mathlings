"""Which taxonomy error pattern each sequence mistake rule corresponds to.

RULE_PATTERNS is the explicit, hand-reviewed mapping. How it is matched
against the real rows is shared by every puzzle type: app/puzzles/core/catalog.py.

Linked, and why the pattern says the same thing as the rule:

- STOPS_AT_ZERO. "Thinks the sequence 'stops' at zero … so 5, 3, 1 halts or
  ends at 0" (linear sequences) and "Numbers stop at (or bounce off) zero"
  (negative numbers). The same idea on the two topics a through-zero step
  practises; the first is used, because linear sequences is the primary topic.
- SIGN_DROPPED. "Reads or writes the negative sign wrongly — records the term
  as 1 instead of −1".
- WRONG_DIRECTION. "Treats a decreasing sequence as a different kind,
  continuing it upward".
- BOUNDARY_SLIP. "50s/100s digit slip — loses place in the 50s (…, 450, 500,
  550) or miscounts at boundaries".
- CONSTANT_GAP. "States a sequence rule from one or two cases and assumes it
  holds without testing further": the child takes the last step as the rule
  and does not test it against the steps before.

Deliberately not linked:

- COUNT_BY_ONE. The nearest pattern is "sub-counts by smaller steps — builds
  the 8s by counting on in 4s (or ones) each time rather than stepping by 8;
  slow and breaks under load". That is a slow way of reaching the right
  answer. COUNT_BY_ONE is a wrong answer: one more instead of one step more.
  Linking them would send the tutor to "connect the 8s to the known 4s" for a
  child who did something else.
- SKIPPED_TERM and OFF_BY_ONE_*: the taxonomy has no pattern for them.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence

from app.puzzles.core.catalog import (
    PatternMatch,
    ResolvedPattern,
    RuleCatalog,
    resolve_rule_patterns,
)
from app.puzzles.types.sequences.levels import (
    TOPIC_GENERALISING,
    TOPIC_LINEAR_SEQUENCES,
    TOPIC_NEGATIVE_NUMBERS,
    TOPIC_SKIP_COUNTING,
)
from app.puzzles.types.sequences.models import MistakeRule
from app.taxonomy.schemas import ErrorPatternOut

RULE_PATTERNS: dict[MistakeRule, tuple[PatternMatch, ...]] = {
    MistakeRule.STOPS_AT_ZERO: (
        PatternMatch(TOPIC_LINEAR_SEQUENCES, "Thinks the sequence 'stops' at zero"),
        PatternMatch(TOPIC_NEGATIVE_NUMBERS, "Numbers stop at (or bounce off) zero"),
    ),
    MistakeRule.SIGN_DROPPED: (
        PatternMatch(TOPIC_LINEAR_SEQUENCES, "Reads or writes the negative sign wrongly"),
    ),
    MistakeRule.WRONG_DIRECTION: (
        PatternMatch(TOPIC_LINEAR_SEQUENCES, "Treats a decreasing sequence as a different kind"),
    ),
    MistakeRule.BOUNDARY_SLIP: (PatternMatch(TOPIC_SKIP_COUNTING, "50s/100s digit slip"),),
    MistakeRule.CONSTANT_GAP: (
        PatternMatch(TOPIC_GENERALISING, "States a sequence rule from one or two cases"),
    ),
}


class SequenceCatalog(RuleCatalog[MistakeRule]):
    """The sequence rules, resolved."""

    def __init__(self, links: Mapping[MistakeRule, Sequence[ResolvedPattern]]) -> None:
        super().__init__(links, MistakeRule)


def resolve_catalog(
    patterns_for_topic: Callable[[str], Iterable[ErrorPatternOut]],
) -> SequenceCatalog:
    """Match RULE_PATTERNS against real error-pattern rows. One lookup per topic."""
    return SequenceCatalog(resolve_rule_patterns(RULE_PATTERNS, patterns_for_topic))
