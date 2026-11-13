"""What the player API returns. Database rows are never returned as they are.

Nothing here can identify a child, and the player id itself is never echoed
back: the browser already has it, and the server has no reason to reveal it.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.adaptive.schemas import TopicMasteryOut


class MistakeCount(BaseModel):
    rule: str = Field(description="Mistake-rule name, for example ADD_VISIBLE.")
    count: int


class TopicPractice(BaseModel):
    topic_id: str
    attempts: int = Field(description="Checked answers on puzzles tagged with this topic.")
    steps: int = Field(description="Different steps tried.")
    first_try_correct_rate: float | None = Field(
        description="Share of steps answered right on the first try, 0 to 1."
    )
    hints_per_step: float | None = Field(description="Hint tiers fetched, per step tried.")
    top_mistakes: list[MistakeCount] = Field(
        description="The three most frequent known mistakes, most frequent first."
    )
    last_practised: datetime


class PracticeTotals(BaseModel):
    attempts: int
    steps: int
    correct: int = Field(description="Checked answers that were right.")
    hint_requests: int
    first_try_correct_rate: float | None
    hints_per_step: float | None


class PlayerSummary(BaseModel):
    player_since: datetime
    totals: PracticeTotals
    topics: list[TopicPractice] = Field(description="Most practised first.")
    mastery: list[TopicMasteryOut] = Field(
        default_factory=list,
        description="Estimated mastery per topic and level, from the first try at each step.",
    )


class PlayerNotFoundBody(BaseModel):
    detail: str
