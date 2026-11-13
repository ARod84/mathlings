"""Recompute attempt.topic_ids per step instead of per puzzle.

Until now an attempt carried the topics of its whole puzzle, so a step that
does not practise "what the equals sign means" still counted toward it
whenever another step of the same puzzle did. From here on an attempt carries
the topics of its own step (app.puzzles.levels.step_topic_ids). This rewrites
the existing rows from their stored level and form.

The mapping below is a frozen copy of step_topic_ids as it was when this
migration was written. A migration must keep doing the same thing forever, so
it does not import the application.

Data only: no table changes. The downgrade leaves the rows alone, because the
old per-puzzle lists cannot be rebuilt from an attempt row, and the per-step
lists are a subset of them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UNKNOWN_ADD_SUB = "mt_3JgrHY221M"
EQUALS_SIGN = "mt_oIzycTBeE4"
MISSING_NUMBER = "mt_XuHmIn2xje"
INVERSE = "mt_ehGS_uVSJv"

ALL_FORMS = ("a+?=c", "?+b=c", "a-?=c", "?-b=c", "c=a+?", "c=?-b")
ANSWER_LEFT_FORMS = ("c=a+?", "c=?-b")


def step_topic_ids(level: int, form: str) -> list[str]:
    if level == 3:
        return [MISSING_NUMBER, INVERSE]
    if form in ANSWER_LEFT_FORMS:
        return [UNKNOWN_ADD_SUB, EQUALS_SIGN]
    return [UNKNOWN_ADD_SUB]


def upgrade() -> None:
    attempt = sa.table(
        "attempt",
        sa.column("game", sa.String),
        sa.column("level", sa.Integer),
        sa.column("form", sa.String),
        sa.column("topic_ids", sa.JSON),
    )
    connection = op.get_bind()
    for level in (1, 2, 3):
        for form in ALL_FORMS:
            connection.execute(
                sa.update(attempt)
                .where(
                    attempt.c.game == "missing-number",
                    attempt.c.level == level,
                    attempt.c.form == form,
                )
                .values(topic_ids=sa.literal(json.dumps(step_topic_ids(level, form))))
            )


def downgrade() -> None:
    pass
