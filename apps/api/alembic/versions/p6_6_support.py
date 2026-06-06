"""P6-6: 客户支持工单 — support_ticket + support_message 表 + audit_log_action 扩展。

Revision ID: p6_6_support
Revises: p5_9_legal
Create Date: 2026-06-06 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_6_support"
down_revision: Union[str, Sequence[str], None] = "p5_9_legal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_ticket",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "pending_customer", "pending_internal", "resolved", "closed", name="ticket_status"),
            nullable=False, server_default="open",
        ),
        sa.Column(
            "priority",
            sa.Enum("low", "normal", "high", "urgent", name="ticket_priority"),
            nullable=False, server_default="normal",
        ),
        sa.Column("assigned_to", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_ticket_org_status", "support_ticket", ["org_id", "status"])
    op.create_index("ix_support_ticket_user_id", "support_ticket", ["user_id"])

    op.create_table(
        "support_message",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column(
            "sender_type",
            sa.Enum("customer", "staff", "system", name="sender_type"),
            nullable=False,
        ),
        sa.Column("sender_id", sa.String(length=36), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_ticket.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_message_ticket_id", "support_message", ["ticket_id"])

    op.execute("ALTER TYPE audit_log_action ADD VALUE IF NOT EXISTS 'support_ticket_create'")
    op.execute("ALTER TYPE audit_log_action ADD VALUE IF NOT EXISTS 'support_ticket_reply'")
    op.execute("ALTER TYPE audit_log_action ADD VALUE IF NOT EXISTS 'support_ticket_close'")


def downgrade() -> None:
    op.drop_index("ix_support_message_ticket_id", table_name="support_message")
    op.drop_table("support_message")
    op.drop_index("ix_support_ticket_user_id", table_name="support_ticket")
    op.drop_index("ix_support_ticket_org_status", table_name="support_ticket")
    op.drop_table("support_ticket")
    for e in ("sender_type", "ticket_priority", "ticket_status"):
        sa.Enum(name=e).drop(op.get_bind(), checkfirst=True)
