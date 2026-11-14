"""What the puzzle API sends and receives that is the same for every game.

A game's own shapes (its new-puzzle request and its public puzzle) live with
the type, in app/puzzles/types/<game>/schemas.py.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: int = Field(
        description="A whole number. Each game has its own bounds (PuzzleType.answer_min and "
        "answer_max): 0 to 10000 for missing-number, -1000 to 10000 for sequences, 0 to 1000 for "
        "sum-grid. An answer "
        "outside the bounds of the puzzle's game is a 422."
    )
    context: Literal["daily"] | None = Field(
        default=None,
        description="Where this check comes from. `daily` for Today's Puzzle (GET /daily); it is "
        "kept in the stored attempt's details as `context`. Leave out for ordinary play.",
    )


class ReteachTopic(BaseModel):
    id: str
    name: str


class DiagnosisPublic(BaseModel):
    matched_rules: list[str] = Field(
        description="Names of the known mistakes that give this answer. For analytics and "
        "development; not for showing to a child."
    )
    unrecognized: bool = Field(description="Wrong, and no known mistake explains it.")
    reteach_topic: ReteachTopic | None = Field(description="Where to step back to, if anywhere.")


class CheckResult(BaseModel):
    correct: bool
    feedback: Literal["correct", "try_again"]
    diagnosis: DiagnosisPublic
    next_step: int | None = Field(
        description="Index of the next step after a correct answer; null on the last step "
        "and after a wrong answer."
    )


class HintOut(BaseModel):
    tier: int
    text: str


class PuzzleNotFoundBody(BaseModel):
    detail: str
    puzzle_id: str


class PuzzleGoneBody(BaseModel):
    detail: str
    current_version: str


class UnknownGameBody(BaseModel):
    detail: str
    game: str
    games: list[str] = Field(description="The games this server has puzzles for.")
