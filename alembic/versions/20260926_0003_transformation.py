"""create the transformation record

Revision ID: 20260926_0003
Revises: 20260924_0002
Create Date: 2026-09-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260926_0003"
down_revision: Union[str, Sequence[str], None] = "20260924_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transformations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("origin IN ('catalog', 'adaptive')", name="ck_transformations_origin"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "transformation_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transformation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", sa.String(length=64), nullable=False),
        sa.Column("direction_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("current_phase_position", sa.Integer(), nullable=False),
        sa.Column("day_in_phase", sa.Integer(), nullable=False),
        sa.Column("commitment_streak", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("day_in_phase >= 1", name="ck_paths_day_in_phase"),
        sa.CheckConstraint("commitment_streak >= 0", name="ck_paths_commitment_streak"),
        sa.CheckConstraint("current_phase_position >= 0", name="ck_paths_phase_position"),
        sa.ForeignKeyConstraint(
            ["transformation_id"], ["transformations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("transformation_id", "identity_id", name="uq_paths_identity"),
    )
    op.create_table(
        "path_phases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("headline", sa.String(length=120), nullable=False),
        sa.Column("length_days", sa.Integer(), nullable=False),
        sa.Column("catalog_phase_id", sa.String(length=160), nullable=True),
        sa.CheckConstraint("length_days >= 1", name="ck_path_phases_length"),
        sa.ForeignKeyConstraint(
            ["path_id"], ["transformation_paths.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("path_id", "position", name="uq_path_phases_position"),
    )
    op.create_table(
        "planned_commitments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("unlock_streak", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("catalog_commitment_id", sa.String(length=200), nullable=True),
        sa.CheckConstraint("unlock_streak >= 0", name="ck_planned_commitments_unlock"),
        sa.ForeignKeyConstraint(["phase_id"], ["path_phases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("phase_id", "position", name="uq_planned_commitments_position"),
    )
    op.create_table(
        "planned_implementations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["commitment_id"], ["planned_commitments.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "commitment_id",
            "position",
            name="uq_planned_implementations_position",
        ),
    )
    op.create_table(
        "days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transformation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_days_status"),
        sa.ForeignKeyConstraint(
            ["transformation_id"], ["transformations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("transformation_id", "calendar_date", name="uq_days_date"),
    )
    op.create_table(
        "day_commitments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("day_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planned_commitment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("implementation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("objective_snapshot", sa.Text(), nullable=False),
        sa.Column("title_snapshot", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'skipped')",
            name="ck_day_commitments_status",
        ),
        sa.ForeignKeyConstraint(["day_id"], ["days.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["path_id"], ["transformation_paths.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["planned_commitment_id"],
            ["planned_commitments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["implementation_id"],
            ["planned_implementations.id"],
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("day_commitments")
    op.drop_table("days")
    op.drop_table("planned_implementations")
    op.drop_table("planned_commitments")
    op.drop_table("path_phases")
    op.drop_table("transformation_paths")
    op.drop_table("transformations")
