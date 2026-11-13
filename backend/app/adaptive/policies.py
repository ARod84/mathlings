"""Which game has a recommendation policy, and what a game without one gets.

    POLICIES["missing-number"]      # the policy in policy.py
    no_policy(puzzle_type)          # for a registered game that has none

A policy turns a player's observations into a Recommendation. Only Missing
Number Chains has one. A game that is registered as a puzzle type but has no
policy still gets an answer from /players/me/next: its lowest level with the
type's default parameters, and reason_code "no_policy", so the caller can
tell that nothing was decided.

To give a game a policy, write its `recommend` (see policy.py for the shape)
and add an entry to POLICIES.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.adaptive.bkt import Observation
from app.adaptive.policy import Recommendation, recommend_from
from app.puzzles.core import PuzzleType
from app.puzzles.types.missing_number.ids import InvalidPuzzleId, parse_puzzle_id
from app.puzzles.types.missing_number.levels import GAME as MISSING_NUMBER


def is_focused(puzzle_id: str) -> bool:
    """True if the id says the chain was generated with a focus."""
    try:
        return parse_puzzle_id(puzzle_id).focus is not None
    except InvalidPuzzleId:
        return False


@dataclass(frozen=True)
class Policy:
    # Observations, oldest first, to what to play next.
    recommend: Callable[[Sequence[Observation]], Recommendation]
    # Was the puzzle with this id made to target a mistake? Read from the id alone.
    is_focused: Callable[[str], bool] = lambda _puzzle_id: False


POLICIES: dict[str, Policy] = {
    MISSING_NUMBER: Policy(recommend=recommend_from, is_focused=is_focused),
}


def no_policy(puzzle_type: type[PuzzleType]) -> Recommendation:
    """What a game without a policy is told: start at the bottom, with the defaults."""
    level = min(puzzle_type.levels)
    return Recommendation(
        level=level,
        length=None,
        reason_code="no_policy",
        reason=(
            f"{puzzle_type.game} has no recommendation policy yet, so this is its "
            f"default: level {level} with the game's default settings."
        ),
        params=puzzle_type.params_to_request(puzzle_type.default_params()),
    )
