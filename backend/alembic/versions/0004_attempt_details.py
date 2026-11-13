"""Give an attempt a place for facts that only its puzzle type has.

Until now an attempt had a `form` column, which only a missing-number chain
can fill. From here on a puzzle type stores what it wants kept about a step
in `details` (JSON): for a chain, {"form": "a+?=c"}.

- adds attempt.details, and fills it for the existing rows from their form
- makes attempt.form nullable; new rows leave it empty

The form column itself stays for now, with its old values in place, so
nothing that still reads it breaks. Dropping it is a later migration.

The downgrade puts the form back from details for rows written since, and
drops details. A row of a game that has no form gets an empty one.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

AutoString = sqlmodel.sql.sqltypes.AutoString

# Text, not JSON: the values below are built in SQL, already as JSON text.
attempt = sa.table("attempt", sa.column("form", sa.String), sa.column("details", sa.Text))


def upgrade() -> None:
    with op.batch_alter_table("attempt") as batch:
        batch.add_column(sa.Column("details", sa.JSON(), nullable=True))
        batch.alter_column("form", existing_type=AutoString(), nullable=True)
    op.execute(sa.update(attempt).values(details=sa.func.json_object("form", attempt.c.form)))
    with op.batch_alter_table("attempt") as batch:
        batch.alter_column("details", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.execute(
        sa.update(attempt).values(
            form=sa.func.coalesce(
                attempt.c.form, sa.func.json_extract(attempt.c.details, "$.form"), ""
            )
        )
    )
    with op.batch_alter_table("attempt") as batch:
        batch.alter_column("form", existing_type=AutoString(), nullable=False)
        batch.drop_column("details")
