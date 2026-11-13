"""Response models. The API and the service return these, never the database tables."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TopicType = Literal["CONCEPTUAL", "PROCEDURAL", "REPRESENTATIONAL", "LANGUAGE", "META"]
Strength = Literal["hard", "soft"]
Depth = Literal["direct", "all"]

RESEARCH_NOTE = "Agent-authored research; sources not independently verified."


class DomainCount(BaseModel):
    subject: str
    domain: str
    topic_count: int


class TopicSummary(BaseModel):
    id: str
    name: str
    subject: str
    domain: str
    type: str
    age_range_start: int
    age_range_end: int
    in_scope: bool = Field(
        description="True for mathematics topics for ages 7-12. False for topics that are "
        "only here because an in-scope topic needs them first."
    )
    has_research: bool


class TopicDetail(TopicSummary):
    description: str
    evidence: list[str]
    centrality: float | None
    assessment_prompt: str = Field(
        description="The assessment prompt with the child's name filled in, or worded "
        "to 'you' when no name is given."
    )


class TopicPage(BaseModel):
    items: list[TopicSummary]
    total: int = Field(description="Number of topics matching the filters, before paging.")
    limit: int
    offset: int


class PrerequisiteItem(BaseModel):
    topic: TopicSummary
    strength: Strength
    reason: str
    distance: int = Field(description="1 for a direct prerequisite, 2 for one of its own, etc.")
    required_by: str = Field(
        description="Id of the topic that directly needs this one. For a direct "
        "prerequisite that is the topic asked about."
    )


class UnlockItem(BaseModel):
    topic: TopicSummary
    strength: Strength
    reason: str


class ErrorPatternOut(BaseModel):
    id: int
    kind: str
    pattern: str
    next_move: str
    distractor: str | None
    revealed_by: str
    reteach_prerequisite: TopicSummary | None


class ResearchActivity(BaseModel):
    title: str
    learner_actions: list[str]
    intended_insight: str
    feedback: list[str]


class TopicResearch(BaseModel):
    topic_id: str
    summary: str
    activities: list[ResearchActivity]
    common_misconceptions: list[str]
    key_representations: list[str]
    confidence: str
    research_note: str = RESEARCH_NOTE


class SourceInfo(BaseModel):
    commit_sha: str
    taxonomy_version: str
    imported_at: datetime
    attribution: str


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    taxonomy_loaded: bool
    topic_count: int


class TopicNotFoundBody(BaseModel):
    detail: str
    topic_id: str


class ErrorBody(BaseModel):
    detail: str
