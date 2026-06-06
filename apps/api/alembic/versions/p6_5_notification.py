"""P6-5: in-app notification 表 (漏建, 现补)。

Revision ID: p6_5_notification
Revises: merge_p6_3_p6_8
Create Date: 2026-06-06 20:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_5_notification"
down_revision: Union[str, Sequence[str], None] = "merge_p6_3_p6_8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "invite_received", "trial_expiring",
                "payment_success", "payment_failed",
                "appeal_filed", "appeal_resolved",
                "onboarding_day1", "onboarding_day3", "onboarding_day7", "onboarding_day14",
                "churn_risk", "system",
                name="notification_type",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_org_id", "notification", ["org_id"])
    op.create_index("ix_notification_user_id", "notification", ["user_id"])
    op.create_index("ix_notification_read", "notification", ["read"])


def downgrade() -> None:
    op.drop_index("ix_notification_read", table_name="notification")
    op.drop_index("ix_notification_user_id", table_name="notification")
    op.drop_index("ix_notification_org_id", table_name="notification")
    op.drop_table("notification")
    sa.Enum(name="notification_type").drop(op.get_bind(), checkfirst=True)
