"""What the adaptive endpoints return. None of it is meant for a child's eyes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TopicMasteryOut(BaseModel):
    topic_id: str
    level: int = Field(description="Each level keeps its own estimate of the same topic.")
    p_known: float = Field(
        description="Estimated probability that the topic is known, 0 to 1. From Bayesian "
        "Knowledge Tracing with hand-set (not fitted) parameters."
    )
    observations: int = Field(description="First tries the estimate is built from (at most 200).")
    last_practised: datetime | None


class NamedMastery(BaseModel):
    topic_id: str
    name: str
    level: int
    p_known: float
    observations: int


class NextPuzzle(BaseModel):
    level: int = Field(ge=1, le=3)
    length: int = Field(description="Number of steps in the chain.")
    reason_code: Literal["cold_start", "promote", "step_down", "consolidate"]
    reason: str = Field(description="Why, in a sentence for an adult. Never show it to a child.")
    focus_rule: str | None = Field(
        description="A mistake rule that keeps coming up, for example ADD_VISIBLE. "
        "Information only: nothing acts on it yet."
    )
    mastery: list[NamedMastery] = Field(
        description="The mastery values the decision used: the recommended level's topics "
        "first, then everything else the player has practised."
    )
