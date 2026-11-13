"""Anonymous practice history: players, checked answers and hint requests.

No personal data lives in these tables. A player is a random UUID the browser
made; see the note above Player in app/models.py.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

AutoString = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        "player",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "attempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("puzzle_id", AutoString(), nullable=False),
        sa.Column("generator_version", AutoString(), nullable=False),
        sa.Column("game", AutoString(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("form", AutoString(), nullable=False),
        sa.Column("answer", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("matched_rules", sa.JSON(), nullable=False),
        sa.Column("error_pattern_ids", sa.JSON(), nullable=False),
        sa.Column("reteach_topic_id", AutoString(), nullable=True),
        sa.Column("topic_ids", sa.JSON(), nullable=False),
        sa.Column("attempt_on_step", sa.Integer(), nullable=False),
        sa.Column("hint_tier_before", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attempt_player_created", "attempt", ["player_id", "created_at"])
    op.create_index("ix_attempt_player_step", "attempt", ["player_id", "puzzle_id", "step_index"])
    op.create_table(
        "hint_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("puzzle_id", AutoString(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hint_request_player_step", "hint_request", ["player_id", "puzzle_id", "step_index"]
    )


def downgrade() -> None:
    op.drop_index("ix_hint_request_player_step", table_name="hint_request")
    op.drop_table("hint_request")
    op.drop_index("ix_attempt_player_step", table_name="attempt")
    op.drop_index("ix_attempt_player_created", table_name="attempt")
    op.drop_table("attempt")
    op.drop_table("player")
