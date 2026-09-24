"""move the subscription link onto subscriptions.user_id

Revision ID: 20260924_0002
Revises: 20260923_0001
Create Date: 2026-09-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0002"
down_revision: Union[str, Sequence[str], None] = "20260923_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE subscriptions
        SET user_id = users.id
        FROM users
        WHERE users.subscription_id = subscriptions.id
        """
    )
    op.alter_column("subscriptions", "user_id", nullable=False)
    op.create_unique_constraint("uq_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_foreign_key(
        "fk_subscriptions_user_id",
        "subscriptions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.drop_constraint("users_subscription_id_fkey", "users", type_="foreignkey")
    op.drop_constraint("users_subscription_id_key", "users", type_="unique")
    op.drop_column("users", "subscription_id")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET subscription_id = subscriptions.id
        FROM subscriptions
        WHERE subscriptions.user_id = users.id
        """
    )
    op.alter_column("users", "subscription_id", nullable=False)
    op.create_foreign_key(
        "users_subscription_id_fkey",
        "users",
        "subscriptions",
        ["subscription_id"],
        ["id"],
    )
    op.create_unique_constraint("users_subscription_id_key", "users", ["subscription_id"])
    op.drop_constraint("fk_subscriptions_user_id", "subscriptions", type_="foreignkey")
    op.drop_constraint("uq_subscriptions_user_id", "subscriptions", type_="unique")
    op.drop_column("subscriptions", "user_id")
