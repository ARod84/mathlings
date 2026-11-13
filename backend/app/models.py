"""Database tables. The taxonomy tables are filled by app.taxonomy.importer; the
player tables (player, attempt, hint_request) by app.players.service.

The schema is created by the Alembic migration, not by SQLModel.metadata.create_all;
tests/test_migration.py fails if the two drift apart.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlmodel import Field, SQLModel


class TaxonomySource(SQLModel, table=True):
    """Which version of os-taxonomy the database holds. Always a single row (id 1)."""

    __tablename__ = "taxonomy_source"

    id: int | None = Field(default=None, primary_key=True)
    commit_sha: str = Field(sa_column=Column(String(40), nullable=False))
    taxonomy_version: str
    research_schema_version: int
    # Set when the row is created or an import changes any data; an import
    # that changes nothing leaves it alone.
    imported_at: datetime
    # {"topics.json": "<sha256>", ...} for the files that were read.
    file_checksums: dict[str, str] = Field(sa_column=Column(JSON, nullable=False))
    # Shown to users wherever taxonomy content appears.
    attribution: str = Field(sa_column=Column(Text, nullable=False))


class Topic(SQLModel, table=True):
    __tablename__ = "topic"
    __table_args__ = (
        Index("ix_topic_domain", "domain"),
        Index("ix_topic_in_scope", "in_scope"),
    )

    # Upstream id (mt_...), stable across dataset versions.
    id: str = Field(primary_key=True)
    type: str
    subject: str
    domain: str
    name: str
    description: str = Field(sa_column=Column(Text, nullable=False))
    evidence: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # Raw upstream text with the {{name}} placeholder kept; see render_assessment_prompt.
    assessment_prompt_template: str = Field(sa_column=Column(Text, nullable=False))
    age_range_start: int
    age_range_end: int
    # Null for a few upstream topics.
    centrality: float | None = None
    # True: mathematics, ages 7-12. False: imported only because an in-scope
    # topic needs it as a (possibly indirect) prerequisite.
    in_scope: bool


class Prerequisite(SQLModel, table=True):
    """topic_id depends on prerequisite_id."""

    __tablename__ = "prerequisite"
    __table_args__ = (
        UniqueConstraint("topic_id", "prerequisite_id", name="uq_prerequisite_pair"),
        Index("ix_prerequisite_prerequisite_id", "prerequisite_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    topic_id: str = Field(sa_column=Column(String, ForeignKey("topic.id"), nullable=False))
    prerequisite_id: str = Field(sa_column=Column(String, ForeignKey("topic.id"), nullable=False))
    # "hard" or "soft".
    strength: str
    reason: str = Field(sa_column=Column(Text, nullable=False))


class TeachingResearch(SQLModel, table=True):
    __tablename__ = "teaching_research"
    __table_args__ = (UniqueConstraint("topic_id", name="uq_teaching_research_topic_id"),)

    id: int | None = Field(default=None, primary_key=True)
    topic_id: str = Field(sa_column=Column(String, ForeignKey("topic.id"), nullable=False))
    pedagogy: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    learn: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # Upstream allows a record without an assessment.
    assess: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    sources: list[Any] = Field(sa_column=Column(JSON, nullable=False))
    confidence: str


class ErrorPattern(SQLModel, table=True):
    """One typical mistake for a topic, taken out of teaching_research.assess.errorPatterns.

    distractor feeds wrong answer options, next_move feeds hints, and
    reteach_prerequisite_id says which topic to step back to.
    """

    __tablename__ = "error_pattern"
    __table_args__ = (
        UniqueConstraint("topic_id", "position", name="uq_error_pattern_topic_position"),
        Index("ix_error_pattern_topic_id", "topic_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    topic_id: str = Field(sa_column=Column(String, ForeignKey("topic.id"), nullable=False))
    # Order within the upstream list, from 0. With topic_id it identifies the
    # row across re-imports, so ids stay stable.
    position: int
    kind: str
    pattern: str = Field(sa_column=Column(Text, nullable=False))
    next_move: str = Field(sa_column=Column(Text, nullable=False))
    distractor: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    revealed_by: str = Field(sa_column=Column(Text, nullable=False))
    reteach_prerequisite_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("topic.id"), nullable=True)
    )


class Cluster(SQLModel, table=True):
    """Parent-friendly summary of a subject and domain for an age band."""

    __tablename__ = "cluster"
    __table_args__ = (
        UniqueConstraint("subject", "domain", "age_range_start", name="uq_cluster_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    subject: str
    domain: str
    age_range_start: int
    summary: str = Field(sa_column=Column(Text, nullable=False))


# ---- players: anonymous practice history ----
#
# Privacy rules for everything below (this is for children):
#   - no personal data: no name, email, birthday, age, IP address or user agent
#   - a player is a random UUIDv4 made by the browser; the server never makes one
#   - the id is a pseudonymous identifier, NOT authentication: anyone who has it
#     can read or delete its history, which is acceptable only because the history
#     is anonymous practice data. Do not hang anything personal off these tables.
#   - deleting a player deletes its rows for real; there is no soft delete


def _player_fk() -> Column:
    return Column(Uuid, ForeignKey("player.id", ondelete="CASCADE"), nullable=False)


class Player(SQLModel, table=True):
    """One browser's practice history. The id comes from the X-Player-Id header."""

    __tablename__ = "player"

    id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    created_at: datetime
    # Moved forward on every stored check or hint.
    last_seen_at: datetime


class Attempt(SQLModel, table=True):
    """One checked answer to one step of a puzzle."""

    __tablename__ = "attempt"
    __table_args__ = (
        Index("ix_attempt_player_created", "player_id", "created_at"),
        Index("ix_attempt_player_step", "player_id", "puzzle_id", "step_index"),
    )

    id: int | None = Field(default=None, primary_key=True)
    player_id: uuid.UUID = Field(sa_column=_player_fk())
    puzzle_id: str
    generator_version: str
    # The puzzle type's game name; the key the game has in shared/game-topics.json.
    game: str
    level: int
    step_index: int
    # No longer written: the form of a missing-number step is now in `details`.
    # Rows from before migration 0004 have it in both. To be dropped in a later cleanup.
    form: str | None = None
    # What the puzzle type wants kept about the step (PuzzleType.attempt_details).
    # For a missing-number chain: {"form": "a+?=c"}.
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    answer: int
    correct: bool
    # Mistake-rule names that give this answer; empty when right or unrecognized.
    matched_rules: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # "<topic id>#<position>" of each matched rule's taxonomy error pattern.
    error_pattern_ids: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # A topic id, kept as plain text: a later taxonomy import may drop the topic,
    # and that must not break or erase history.
    reteach_topic_id: str | None = None
    # The topics this step practises, primary first (PuzzleType.step_topic_ids).
    # Narrower than the puzzle's list. Rows from before migration 0003 held the
    # puzzle's list; that migration rewrote them.
    topic_ids: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # 1 for this player's first try at this step, 2 for the second, and so on.
    attempt_on_step: int
    # Highest hint tier this player fetched for this step before this check; 0 for none.
    hint_tier_before: int
    created_at: datetime


class HintRequest(SQLModel, table=True):
    """One hint tier fetched for one step."""

    __tablename__ = "hint_request"
    __table_args__ = (Index("ix_hint_request_player_step", "player_id", "puzzle_id", "step_index"),)

    id: int | None = Field(default=None, primary_key=True)
    player_id: uuid.UUID = Field(sa_column=_player_fk())
    puzzle_id: str
    step_index: int
    tier: int
    created_at: datetime
