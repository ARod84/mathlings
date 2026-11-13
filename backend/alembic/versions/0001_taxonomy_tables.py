"""Taxonomy tables: source, topics, prerequisites, research, error patterns, clusters.

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

AutoString = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        "taxonomy_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("taxonomy_version", AutoString(), nullable=False),
        sa.Column("research_schema_version", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("file_checksums", sa.JSON(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "topic",
        sa.Column("id", AutoString(), nullable=False),
        sa.Column("type", AutoString(), nullable=False),
        sa.Column("subject", AutoString(), nullable=False),
        sa.Column("domain", AutoString(), nullable=False),
        sa.Column("name", AutoString(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("assessment_prompt_template", sa.Text(), nullable=False),
        sa.Column("age_range_start", sa.Integer(), nullable=False),
        sa.Column("age_range_end", sa.Integer(), nullable=False),
        sa.Column("centrality", sa.Float(), nullable=True),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topic_domain", "topic", ["domain"])
    op.create_index("ix_topic_in_scope", "topic", ["in_scope"])
    op.create_table(
        "prerequisite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("prerequisite_id", sa.String(), nullable=False),
        sa.Column("strength", AutoString(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"]),
        sa.ForeignKeyConstraint(["prerequisite_id"], ["topic.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "prerequisite_id", name="uq_prerequisite_pair"),
    )
    op.create_index("ix_prerequisite_prerequisite_id", "prerequisite", ["prerequisite_id"])
    op.create_table(
        "teaching_research",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("pedagogy", sa.JSON(), nullable=False),
        sa.Column("learn", sa.JSON(), nullable=False),
        sa.Column("assess", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("confidence", AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", name="uq_teaching_research_topic_id"),
    )
    op.create_table(
        "error_pattern",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", AutoString(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("next_move", sa.Text(), nullable=False),
        sa.Column("distractor", sa.Text(), nullable=True),
        sa.Column("revealed_by", sa.Text(), nullable=False),
        sa.Column("reteach_prerequisite_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"]),
        sa.ForeignKeyConstraint(["reteach_prerequisite_id"], ["topic.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "position", name="uq_error_pattern_topic_position"),
    )
    op.create_index("ix_error_pattern_topic_id", "error_pattern", ["topic_id"])
    op.create_table(
        "cluster",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject", AutoString(), nullable=False),
        sa.Column("domain", AutoString(), nullable=False),
        sa.Column("age_range_start", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject", "domain", "age_range_start", name="uq_cluster_key"),
    )


def downgrade() -> None:
    op.drop_table("cluster")
    op.drop_index("ix_error_pattern_topic_id", table_name="error_pattern")
    op.drop_table("error_pattern")
    op.drop_table("teaching_research")
    op.drop_index("ix_prerequisite_prerequisite_id", table_name="prerequisite")
    op.drop_table("prerequisite")
    op.drop_index("ix_topic_in_scope", table_name="topic")
    op.drop_index("ix_topic_domain", table_name="topic")
    op.drop_table("topic")
    op.drop_table("taxonomy_source")
