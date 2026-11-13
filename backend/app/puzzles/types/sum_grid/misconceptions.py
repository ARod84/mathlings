"""Which taxonomy error pattern each Sum Grid mistake rule corresponds to.

RULE_PATTERNS is the explicit, hand-reviewed mapping. How it is matched
against the real rows is shared by every puzzle type: app/puzzles/core/catalog.py.

Linked, and why the pattern says the same thing as the rule:

- ADD_VISIBLE. "Adds the two visible numbers regardless of the box's position
  — 8 + ? = 11 becomes 8 + 11 = 19 in the box." A row with a blank and a
  target is that equation drawn in a grid.
- FORGOT_ONE. "Makes ten with a pair but then loses or double-counts the
  third addend." The child deals with one of the two known numbers and loses
  the other.
- PLACE_VALUE_SLIP. "Smaller-from-larger — in 502−276 does 6−2 in the ones
  rather than exchanging": the slip in the subtraction.
- CARRY_DROPPED. "Carry omitted or misplaced — in 347+185 forgets to add the
  carried ten": the slip in adding the two known numbers. The same topic as
  the one above, and a different thing to reteach, which is why they are two
  rules and not one.
- TENS_AS_ONES. "Treats a multiple of ten as ones — 'thirty-eight plus forty
  is forty-two' (adds the 4, not 40)."

Deliberately not linked: WRONG_LINE and OFF_BY_ONE_*. The taxonomy has no
pattern for reading the wrong total off a grid, or for being one out.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence

from app.puzzles.core.catalog import (
    PatternMatch,
    ResolvedPattern,
    RuleCatalog,
    resolve_rule_patterns,
)
from app.puzzles.types.sum_grid.levels import (
    TOPIC_ADD_SUBTRACT_7,
    TOPIC_ADDING_WITHIN_100,
    TOPIC_THREE_SMALL_NUMBERS,
    TOPIC_UNKNOWN_ADD_SUB,
)
from app.puzzles.types.sum_grid.models import MistakeRule
from app.taxonomy.schemas import ErrorPatternOut

RULE_PATTERNS: dict[MistakeRule, tuple[PatternMatch, ...]] = {
    MistakeRule.ADD_VISIBLE: (
        PatternMatch(TOPIC_UNKNOWN_ADD_SUB, "Adds the two visible numbers regardless of the box"),
    ),
    MistakeRule.FORGOT_ONE: (
        PatternMatch(TOPIC_THREE_SMALL_NUMBERS, "Makes ten with a pair but then loses"),
    ),
    MistakeRule.PLACE_VALUE_SLIP: (PatternMatch(TOPIC_ADD_SUBTRACT_7, "Smaller-from-larger"),),
    MistakeRule.CARRY_DROPPED: (PatternMatch(TOPIC_ADD_SUBTRACT_7, "Carry omitted or misplaced"),),
    MistakeRule.TENS_AS_ONES: (
        PatternMatch(TOPIC_ADDING_WITHIN_100, "Treats a multiple of ten as ones"),
    ),
}


class SumGridCatalog(RuleCatalog[MistakeRule]):
    """The Sum Grid rules, resolved."""

    def __init__(self, links: Mapping[MistakeRule, Sequence[ResolvedPattern]]) -> None:
        super().__init__(links, MistakeRule)


def resolve_catalog(
    patterns_for_topic: Callable[[str], Iterable[ErrorPatternOut]],
) -> SumGridCatalog:
    """Match RULE_PATTERNS against real error-pattern rows. One lookup per topic."""
    return SumGridCatalog(resolve_rule_patterns(RULE_PATTERNS, patterns_for_topic))
