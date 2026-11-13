"""The six equation forms: how each is laid out, and reading numbers back out of one.

Every form is one fact, part + part = whole, with one of the three hidden.
"first" and "second" always mean the two visible numbers in reading order,
left to right across the equals sign:

    form     reads as        first  second  hidden
    a+?=c    a + □ = c       part   whole   part
    ?+b=c    □ + b = c       part   whole   part
    a-?=c    a − □ = c       whole  part    part
    ?-b=c    □ − b = c       part   part    whole
    c=a+?    c = a + □       whole  part    part
    c=?-b    c = □ − b       part   part    whole
"""

from dataclasses import dataclass
from typing import Literal

from app.puzzles.types.missing_number.models import (
    Equation,
    Form,
    NumberToken,
    OperatorToken,
    PuzzleStep,
    Token,
    UnknownToken,
)

Role = Literal["part", "whole"]
# "x" and "y" stand for the first and second visible numbers, "?" for the box.
Slot = Literal["x", "y", "?", "+", "-"]


@dataclass(frozen=True)
class FormSpec:
    form: Form
    left: tuple[Slot, ...]
    right: tuple[Slot, ...]
    operator: Literal["+", "-"]
    # Roles of the first and second visible numbers.
    roles: tuple[Role, Role]

    @property
    def unknown_role(self) -> Role:
        return "whole" if self.roles == ("part", "part") else "part"


FORMS: dict[Form, FormSpec] = {
    "a+?=c": FormSpec("a+?=c", ("x", "+", "?"), ("y",), "+", ("part", "whole")),
    "?+b=c": FormSpec("?+b=c", ("?", "+", "x"), ("y",), "+", ("part", "whole")),
    "a-?=c": FormSpec("a-?=c", ("x", "-", "?"), ("y",), "-", ("whole", "part")),
    "?-b=c": FormSpec("?-b=c", ("?", "-", "x"), ("y",), "-", ("part", "part")),
    "c=a+?": FormSpec("c=a+?", ("x",), ("y", "+", "?"), "+", ("whole", "part")),
    "c=?-b": FormSpec("c=?-b", ("x",), ("?", "-", "y"), "-", ("part", "part")),
}

ALL_FORMS: tuple[Form, ...] = tuple(FORMS)


def build_equation(form: Form, first: int, second: int) -> Equation:
    def tokens(slots: tuple[Slot, ...]) -> list[Token]:
        out: list[Token] = []
        for slot in slots:
            if slot == "x":
                out.append(NumberToken(value=first))
            elif slot == "y":
                out.append(NumberToken(value=second))
            elif slot == "?":
                out.append(UnknownToken())
            else:
                out.append(OperatorToken(symbol=slot))
        return out

    spec = FORMS[form]
    return Equation(left=tokens(spec.left), right=tokens(spec.right))


def visible_numbers(equation: Equation) -> list[int]:
    """The numbers a child can see, in reading order."""
    return [
        token.value for token in (*equation.left, *equation.right) if isinstance(token, NumberToken)
    ]


def operands(step: PuzzleStep) -> tuple[int, int]:
    """The step's first and second visible numbers. Raises ValueError if there are not two."""
    numbers = visible_numbers(step.equation)
    if len(numbers) != 2:
        raise ValueError(f"expected two visible numbers, found {len(numbers)}")
    return numbers[0], numbers[1]


def render(equation: Equation, box: str = "□") -> str:
    """Plain text, for logs and reports: '8 + □ = 11'."""

    def side(tokens: list[Token]) -> str:
        parts = []
        for token in tokens:
            if isinstance(token, NumberToken):
                parts.append(str(token.value))
            elif isinstance(token, OperatorToken):
                parts.append("−" if token.symbol == "-" else "+")
            else:
                parts.append(box)
        return " ".join(parts)

    return f"{side(equation.left)} = {side(equation.right)}"
