"""P6-3: self-serve signup — subscription 加 trial_end_at + 14天试用。

trial 14 天: 注册后自动建 subscription, plan=starter (免费), trial_end_at=now+14d。
trial 到期: plan 自动降级 (无降级 = 不让用, 强制付费)。
trial 警告: D+11 飞书/短信提醒 (走 P6-5 触达)。

Revision ID: p6_3_trial
Revises: p5_15_onboarding
Create Date: 2026-06-06 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p6_3_trial"
down_revision: Union[str, Sequence[str], None] = "p5_15_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription",
        sa.Column(
            "trial_end_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "subscription",
        sa.Column(
            "trial_reminded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_subscription_trial_end",
        "subscription",
        ["trial_end_at"],
    )

    op.create_table(
        "referral_code",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("seat_reward", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_referral_code"),
        sa.UniqueConstraint("org_id", "code", name="uq_referral_org_code"),
    )
    op.create_index("ix_referral_org", "referral_code", ["org_id", "active"])

    op.create_table(
        "referral_use",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("referral_code_id", sa.String(length=36), nullable=False),
        sa.Column("inviter_org_id", sa.String(length=36), nullable=False),
        sa.Column("new_org_id", sa.String(length=36), nullable=False),
        sa.Column("new_user_id", sa.String(length=36), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("seat_rewarded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("new_org_id", name="uq_referral_new_org"),
    )
    op.create_index("ix_referral_use_code", "referral_use", ["referral_code_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_use_code", table_name="referral_use")
    op.drop_table("referral_use")
    op.drop_index("ix_referral_org", table_name="referral_code")
    op.drop_table("referral_code")
    op.drop_index("ix_subscription_trial_end", table_name="subscription")
    op.drop_column("subscription", "trial_reminded")
    op.drop_column("subscription", "trial_end_at")
