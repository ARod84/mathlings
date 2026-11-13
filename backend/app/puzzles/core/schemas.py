"""What the puzzle API sends and receives that is the same for every game.

A game's own shapes (its new-puzzle request and its public puzzle) live with
the type, in app/puzzles/types/<game>/schemas.py.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ANSWER = 10_000


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: int = Field(ge=0, le=MAX_ANSWER)


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
