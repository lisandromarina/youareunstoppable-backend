"""record onboarding steps for the activation funnel

Revision ID: 20260929_0005
Revises: 20260928_0004
Create Date: 2026-09-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0005"
down_revision: Union[str, Sequence[str], None] = "20260928_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "onboarding_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "step", name="uq_onboarding_steps_user_step"),
        sa.CheckConstraint(
            "step IN ('begin', 'identity', 'direction')",
            name="ck_onboarding_steps_step",
        ),
    )


def downgrade() -> None:
    op.drop_table("onboarding_steps")
