"""Mistake rules: what a child who makes a known mistake would put in a blank.

Each rule is a pure function of the sequence and the position of the blank.
It returns the wrong answer the mistake produces, or None when the mistake
cannot happen there or happens to give the right answer.

What each rule gives, per kind of sequence. p is the term before the blank,
a the right answer, d the step into the blank (a − p; negative going down),
and for a growing sequence g is the step before that one and c the growth
(d = g + c). "-" means the rule does not apply.

                       constant, up      constant, down        growing
    example            4, 8, 12, □       9, 6, 3, 0, □         1, 2, 4, 7, □
    right answer       p + d             p + d  (d < 0)        p + g + c
    -----------------  ----------------  --------------------  ----------------
    STOPS_AT_ZERO      -                 0, if a < 0           -
    SIGN_DROPPED       -                 −a, if a < 0          -
    WRONG_DIRECTION    -                 p − d  (p + |d|)      -
    BOUNDARY_SLIP      p ⊕ d *           p ⊖ |d| *             -
    CONSTANT_GAP       -                 -                     p + g
    COUNT_BY_ONE       p + 1, if d ≠ 1   p − 1, if d ≠ −1      p + 1, if d ≠ 1
    SKIPPED_TERM       a + d             a + d                 a + d + c
    OFF_BY_ONE_OVER    a + 1, every kind
    OFF_BY_ONE_UNDER   a − 1, every kind

    ⊕  column-by-column addition with the carries dropped.   450 ⊕ 50 = 400
    ⊖  column-by-column subtraction with no exchanging.      500 ⊖ 50 = 550
    *  only where the step crosses a hundreds boundary; see below.

The examples: 16 is right for 4, 8, 12, □; SKIPPED_TERM gives 20 and
COUNT_BY_ONE 13. For 9, 6, 3, 0, □ the answer is −3; STOPS_AT_ZERO gives 0,
SIGN_DROPPED 3, WRONG_DIRECTION 3 as well (0 + 3). For 1, 2, 4, 7, □ the
answer is 11; CONSTANT_GAP gives 10 (the last step, +3, again).

Why the dashes and the conditions are there:

- STOPS_AT_ZERO and SIGN_DROPPED need an answer below zero. Above zero there
  is no sign to drop, and nothing has stopped.
- WRONG_DIRECTION is the taxonomy's "continues a decreasing sequence upward",
  so it needs a sequence that goes down. A growing sequence here always goes up.
- BOUNDARY_SLIP is the taxonomy's "50s/100s digit slip": losing the place at
  a hundreds boundary. It applies only when the term before the blank already
  has three digits, the answer is in another hundred, and both are in the same
  thousand and not negative. Then the slip is the written sum done without
  carrying (450 + 50 → 400) or the written difference without exchanging
  (500 − 50 → 550). Where no column carries, the slip gives the right answer,
  and sometimes it gives the term before the blank back (501 ⊖ 2 = 501);
  either way there is nothing to offer. Crossing 1000, or working below 100, is a
  different slip that the taxonomy does not describe.
- CONSTANT_GAP needs a step that changes, so a growing sequence, and two terms
  before the blank to take the last step from.
- COUNT_BY_ONE gives the right answer when the step is 1.
- SKIPPED_TERM is the term after the right one, under the real rule.
- OFF_BY_ONE is two rules, one per direction, so that each rule has one output.

Several rules can give the same number (above, SIGN_DROPPED and
WRONG_DIRECTION both give 3). The generator offers the number once, under the
first rule in its order; the diagnoser reports every rule that matches.

NEAR_MISS is not a mistake rule and has no function here: it is a filler value
a fixed distance from the answer (LevelSpec.near_miss_offsets).
"""

from collections.abc import Callable, Sequence

from app.puzzles.core.arithmetic import add_without_carry, subtract_without_exchange
from app.puzzles.types.sequences.levels import OPTION_CEILING, OPTION_FLOOR, Kind, LevelSpec
from app.puzzles.types.sequences.models import MistakeRule

RuleFunction = Callable[[Sequence[int], int, Kind], int | None]


def stops_at_zero(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    if kind != "constant" or terms[position] >= 0:
        return None
    return 0


def sign_dropped(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    if kind != "constant" or terms[position] >= 0:
        return None
    return -terms[position]


def wrong_direction(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    before, answer = terms[position - 1], terms[position]
    if kind != "constant" or answer >= before:
        return None
    return before + (before - answer)


def boundary_slip(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    before, answer = terms[position - 1], terms[position]
    if kind != "constant" or before < 100 or answer < 0:
        return None
    if before // 100 == answer // 100 or before // 1000 != answer // 1000:
        return None
    if answer > before:
        value = add_without_carry(before, answer - before)
    else:
        value = subtract_without_exchange(before, before - answer)
    # 501 ⊖ 2 is 501 again: no child answers with the number they started from.
    return None if value == before else value


def constant_gap(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    if kind != "growing" or position < 2:
        return None
    return terms[position - 1] + (terms[position - 1] - terms[position - 2])


def count_by_one(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    before, answer = terms[position - 1], terms[position]
    return before + (1 if answer > before else -1)


def skipped_term(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    before, answer = terms[position - 1], terms[position]
    step = answer - before
    if kind == "growing":
        # The next step is bigger by the growth, which is the same all along the row.
        step += terms[2] - 2 * terms[1] + terms[0]
    return answer + step


def off_by_one_over(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    return terms[position] + 1


def off_by_one_under(terms: Sequence[int], position: int, kind: Kind) -> int | None:
    return terms[position] - 1


RULES: dict[MistakeRule, RuleFunction] = {
    MistakeRule.STOPS_AT_ZERO: stops_at_zero,
    MistakeRule.SIGN_DROPPED: sign_dropped,
    MistakeRule.WRONG_DIRECTION: wrong_direction,
    MistakeRule.BOUNDARY_SLIP: boundary_slip,
    MistakeRule.CONSTANT_GAP: constant_gap,
    MistakeRule.COUNT_BY_ONE: count_by_one,
    MistakeRule.SKIPPED_TERM: skipped_term,
    MistakeRule.OFF_BY_ONE_OVER: off_by_one_over,
    MistakeRule.OFF_BY_ONE_UNDER: off_by_one_under,
}


def rule_output(rule: MistakeRule, terms: Sequence[int], position: int, kind: Kind) -> int | None:
    """What a child making this mistake would answer for the blank at `position`, or None.

    None when the rule does not apply to this kind of sequence or this blank,
    or when the mistake lands on the right answer. `terms` is the whole
    sequence; a blank is never the first term. The value has no limit here:
    the diagnoser needs to see it. distractor_value applies the limits for
    answer options.
    """
    function = RULES.get(rule)
    if function is None or position < 1:
        return None
    value = function(terms, position, kind)
    if value is None or value == terms[position]:
        return None
    return value


def distractor_value(
    rule: MistakeRule, terms: Sequence[int], position: int, kind: Kind, spec: LevelSpec
) -> int | None:
    """The rule's output if it can be offered as an answer option, else None.

    Stricter than rule_output only in that an option stays inside the level's
    option range, and inside the range no option of any level may leave.
    """
    value = rule_output(rule, terms, position, kind)
    if value is None or not in_option_range(value, spec):
        return None
    return value


def in_option_range(value: int, spec: LevelSpec) -> bool:
    return max(spec.option_min, OPTION_FLOOR) <= value <= min(spec.option_max, OPTION_CEILING)


def is_near_miss(value: int, answer: int, spec: LevelSpec) -> bool:
    """True if `value` is a valid NEAR_MISS filler for a blank whose answer is `answer`."""
    return (
        spec.min_value <= value <= spec.max_value
        and value != answer
        and abs(value - answer) in spec.near_miss_offsets
    )
