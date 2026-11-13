"""Mistake rules: what a child who makes a known mistake would write in the box.

Each rule is a pure function of one step. It returns the wrong answer the
mistake produces, or None when the mistake cannot happen on that form or
happens to give the right answer.

What each rule gives, per form (x and y are the first and second visible
numbers in reading order; "-" means the rule does not apply):

    form                 a+?=c   ?+b=c   a-?=c   ?-b=c   c=a+?   c=?-b
    reads as             x+□=y   □+x=y   x−□=y   □−x=y   x=y+□   x=□−y
    correct answer       y−x     y−x     x−y     x+y     x−y     x+y
    -------------------  ------  ------  ------  ------  ------  ------
    ADD_VISIBLE          x+y     x+y     -       -       x+y     -
    ANSWER_LEFT_BACKWARDS  -     -       -       -       -       x−y
    POSITION_CONFUSION   -       -       -       y−x     -       -
    PLACE_VALUE_SLIP     y⊖x     y⊖x     x⊖y     x⊕y     x⊖y     x⊕y
    OFF_BY_ONE_OVER      answer + 1, every form
    OFF_BY_ONE_UNDER     answer − 1, every form

    ⊖  column-by-column subtraction with no exchanging: in each column the
       smaller digit is taken from the larger.   380 ⊖ 245 = 145
    ⊕  column-by-column addition with the carries dropped.   275 ⊕ 148 = 313

Why the dashes are there:

- ADD_VISIBLE on a-?=c: the mistake is "do the sum you can see". With a minus
  sign showing, that sum is x − y, which is the right answer, so there is no
  wrong value to offer. Adding there would be a different, unsupported guess.
- ADD_VISIBLE on ?-b=c and c=?-b: adding the two visible numbers is correct.
- ANSWER_LEFT_BACKWARDS is defined by the taxonomy only for c=?-b ("5 = □ − 3
  solved as 5 − 3"). On c=a+? the matching slip would be x + y, which is
  already ADD_VISIBLE, so it is left to that rule.
- POSITION_CONFUSION is defined only for ?-b=c ("□ − 120 = 250 as 250 − 120").
  On ?+b=c the matching slip is again x + y.
- ANSWER_LEFT_BACKWARDS and POSITION_CONFUSION give nothing when the
  subtraction would go below zero (5 = □ − 9): what the child does then is not
  known, so no value is invented.
- PLACE_VALUE_SLIP is for level 3 only, and gives nothing when no column needs
  an exchange or a carry (the slip then gives the right answer).
- OFF_BY_ONE is two rules, one per direction, so that each rule has one output.

NEAR_MISS is not a mistake rule and has no function here: it is a filler value
a fixed distance from the answer (LevelSpec.near_miss_offsets).
"""

from collections.abc import Callable

from app.puzzles.types.missing_number.equations import operands
from app.puzzles.types.missing_number.levels import LevelSpec
from app.puzzles.types.missing_number.models import MistakeRule, PuzzleStep

RuleFunction = Callable[[PuzzleStep], int | None]


def _digits(value: int, width: int) -> list[int]:
    return [int(char) for char in str(value).zfill(width)]


def subtract_without_exchange(minuend: int, subtrahend: int) -> int:
    """Each column on its own, smaller digit from larger: 380 and 245 give 145."""
    width = max(len(str(minuend)), len(str(subtrahend)))
    columns = zip(_digits(minuend, width), _digits(subtrahend, width), strict=True)
    return int("".join(str(abs(top - bottom)) for top, bottom in columns))


def add_without_carry(first: int, second: int) -> int:
    """Each column on its own, carries dropped: 275 and 148 give 313."""
    width = max(len(str(first)), len(str(second)))
    columns = zip(_digits(first, width), _digits(second, width), strict=True)
    return int("".join(str((a + b) % 10) for a, b in columns))


def add_visible(step: PuzzleStep) -> int | None:
    if step.form not in ("a+?=c", "?+b=c", "c=a+?"):
        return None
    x, y = operands(step)
    return x + y


def answer_left_backwards(step: PuzzleStep) -> int | None:
    if step.form != "c=?-b":
        return None
    x, y = operands(step)
    return x - y if x >= y else None


def position_confusion(step: PuzzleStep) -> int | None:
    if step.form != "?-b=c":
        return None
    x, y = operands(step)
    return y - x if y >= x else None


def place_value_slip(step: PuzzleStep) -> int | None:
    x, y = operands(step)
    if step.form in ("a+?=c", "?+b=c"):
        return subtract_without_exchange(y, x)
    if step.form in ("a-?=c", "c=a+?"):
        return subtract_without_exchange(x, y)
    return add_without_carry(x, y)


def off_by_one_over(step: PuzzleStep) -> int | None:
    return step.answer + 1


def off_by_one_under(step: PuzzleStep) -> int | None:
    return step.answer - 1


RULES: dict[MistakeRule, RuleFunction] = {
    MistakeRule.ADD_VISIBLE: add_visible,
    MistakeRule.ANSWER_LEFT_BACKWARDS: answer_left_backwards,
    MistakeRule.POSITION_CONFUSION: position_confusion,
    MistakeRule.PLACE_VALUE_SLIP: place_value_slip,
    MistakeRule.OFF_BY_ONE_OVER: off_by_one_over,
    MistakeRule.OFF_BY_ONE_UNDER: off_by_one_under,
}


def rule_output(rule: MistakeRule, step: PuzzleStep, spec: LevelSpec) -> int | None:
    """What a child making this mistake would answer, or None.

    None when the rule does not apply to the form or the level, or when the
    mistake lands on the right answer or below zero. The value has no upper
    limit here: a child typing freely can give any number, so the diagnoser
    needs to see it. distractor_value applies the cap for answer options.
    """
    function = RULES.get(rule)
    if function is None:
        return None
    if rule is MistakeRule.PLACE_VALUE_SLIP and not spec.place_value_rule:
        return None
    value = function(step)
    if value is None or value < 0 or value == step.answer:
        return None
    return value


def distractor_value(rule: MistakeRule, step: PuzzleStep, spec: LevelSpec) -> int | None:
    """The rule's output if it can be offered as an answer option, else None.

    Stricter than rule_output only in that an option may not exceed the
    level's distractor_max. That cap is above max_value: a mistake often
    lands past the level's range, and those are the answers worth offering.
    """
    value = rule_output(rule, step, spec)
    if value is None or value > spec.distractor_max:
        return None
    return value


def is_near_miss(value: int, step: PuzzleStep, spec: LevelSpec) -> bool:
    """True if `value` is a valid NEAR_MISS filler for the step."""
    return (
        0 <= value <= spec.max_value
        and value != step.answer
        and abs(value - step.answer) in spec.near_miss_offsets
    )
