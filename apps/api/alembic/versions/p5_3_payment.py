"""P5-3: 国内支付 — payment_orders + subscriptions 表

Revision ID: p5_3_payment
Revises: p5_2_wechat_oauth
Create Date: 2026-06-06 11:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_3_payment"
down_revision: Union[str, Sequence[str], None] = "p5_2_wechat_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_order",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "plan",
            sa.Enum("starter", "pro", "enterprise", name="payment_plan"),
            nullable=False,
        ),
        sa.Column("billing_cycle", sa.String(length=16), nullable=False, server_default="monthly"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column(
            "status",
            sa.Enum("pending", "paid", "refunded", "expired", "cancelled", name="payment_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="wechat"),
        sa.Column("out_trade_no", sa.String(length=64), nullable=False),
        sa.Column("prepay_id", sa.String(length=128), nullable=True),
        sa.Column("transaction_id", sa.String(length=64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_amount_cents", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("out_trade_no", name="uq_payment_order_out_trade_no"),
    )
    op.create_index("ix_payment_order_org_status", "payment_order", ["org_id", "status"])
    op.create_index("ix_payment_order_user_id", "payment_order", ["user_id"])
    op.create_index("ix_payment_order_expires", "payment_order", ["expires_at"])

    op.create_table(
        "subscription",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column(
            "plan",
            sa.Enum("starter", "pro", "enterprise", name="payment_plan"),
            nullable=False,
        ),
        sa.Column("billing_cycle", sa.String(length=16), nullable=False, server_default="monthly"),
        sa.Column(
            "status",
            sa.Enum("active", "expired", "cancelled", "grace_period", name="subscription_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_payment_order_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", name="uq_subscription_org"),
    )
    op.create_index("ix_subscription_period_end", "subscription", ["current_period_end"])
    op.create_index("ix_subscription_status", "subscription", ["status"])


def downgrade() -> None:
    op.drop_index("ix_subscription_status", table_name="subscription")
    op.drop_index("ix_subscription_period_end", table_name="subscription")
    op.drop_table("subscription")
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.drop_index("ix_payment_order_expires", table_name="payment_order")
    op.drop_index("ix_payment_order_user_id", table_name="payment_order")
    op.drop_index("ix_payment_order_org_status", table_name="payment_order")
    op.drop_table("payment_order")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS payment_plan")
