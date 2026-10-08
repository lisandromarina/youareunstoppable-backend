"""add one-time commitments

Revision ID: 20261007_0007
Revises: 20261004_0006
Create Date: 2026-10-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0007"
down_revision: Union[str, Sequence[str], None] = "20261004_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_planned_commitments_recurrence", "planned_commitments", type_="check")
    op.add_column("planned_commitments", sa.Column("due_on", sa.Date(), nullable=True))
    op.add_column("planned_commitments", sa.Column("reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_planned_commitments_recurrence",
        "planned_commitments",
        "recurrence IN ('daily', 'times_per_week', 'weekly', 'monthly', 'once')",
    )
    op.create_check_constraint(
        "ck_planned_commitments_due_on",
        "planned_commitments",
        "(recurrence = 'once' AND due_on IS NOT NULL) OR (recurrence <> 'once' AND due_on IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_planned_commitments_due_on", "planned_commitments", type_="check")
    op.drop_constraint("ck_planned_commitments_recurrence", "planned_commitments", type_="check")
    op.drop_column("planned_commitments", "reason")
    op.drop_column("planned_commitments", "due_on")
    op.create_check_constraint(
        "ck_planned_commitments_recurrence",
        "planned_commitments",
        "recurrence IN ('daily', 'times_per_week', 'weekly', 'monthly')",
    )
