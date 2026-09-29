"""add commitment recurrence

Revision ID: 20260928_0004
Revises: 20260926_0003
Create Date: 2026-09-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0004"
down_revision: Union[str, Sequence[str], None] = "20260926_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("planned_commitments", sa.Column("recurrence", sa.String(length=32), nullable=True))
    op.add_column("planned_commitments", sa.Column("times_per_week", sa.Integer(), nullable=True))
    op.add_column("planned_commitments", sa.Column("weekdays", sa.JSON(), nullable=True))
    op.add_column("planned_commitments", sa.Column("month_day", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE planned_commitments
        SET recurrence = 'weekly', weekdays = '[0]'::json
        WHERE unlock_streak > 0
        """
    )
    op.execute(
        """
        UPDATE planned_commitments
        SET recurrence = 'times_per_week', times_per_week = 3, weekdays = '[0, 2, 4]'::json
        WHERE unlock_streak = 0 AND position > 0
        """
    )
    op.execute(
        """
        UPDATE planned_commitments
        SET recurrence = 'daily', weekdays = '[]'::json
        WHERE recurrence IS NULL
        """
    )
    op.alter_column("planned_commitments", "recurrence", nullable=False)
    op.alter_column("planned_commitments", "weekdays", nullable=False)
    op.create_check_constraint(
        "ck_planned_commitments_recurrence",
        "planned_commitments",
        "recurrence IN ('daily', 'times_per_week', 'weekly', 'monthly')",
    )
    op.create_check_constraint(
        "ck_planned_commitments_times",
        "planned_commitments",
        "times_per_week IS NULL OR (times_per_week >= 1 AND times_per_week <= 7)",
    )
    op.create_check_constraint(
        "ck_planned_commitments_month_day",
        "planned_commitments",
        "month_day IS NULL OR (month_day >= 1 AND month_day <= 28)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_planned_commitments_month_day", "planned_commitments", type_="check")
    op.drop_constraint("ck_planned_commitments_times", "planned_commitments", type_="check")
    op.drop_constraint("ck_planned_commitments_recurrence", "planned_commitments", type_="check")
    op.drop_column("planned_commitments", "month_day")
    op.drop_column("planned_commitments", "weekdays")
    op.drop_column("planned_commitments", "times_per_week")
    op.drop_column("planned_commitments", "recurrence")
