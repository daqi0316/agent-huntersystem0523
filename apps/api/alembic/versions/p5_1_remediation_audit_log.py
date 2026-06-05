"""P5-1 补救: audit_log 表 (跨 org 切换 / 邀请接受 / 成员变更 落库)

Revision ID: p5_1_remediation_audit_log
Revises: p5_1_pr_8_default_org_migration
Create Date: 2026-06-05 19:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_1_remediation_audit_log"
down_revision: Union[str, Sequence[str], None] = "p5_1_pr_8_default_org_migration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "org_switch",
                "invite_accept",
                "membership_add",
                "membership_remove",
                "membership_role_change",
                name="audit_log_action",
            ),
            nullable=False,
        ),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_org_time", "audit_log", ["org_id", "created_at"])
    op.create_index("ix_audit_log_actor_time", "audit_log", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_time", table_name="audit_log")
    op.drop_index("ix_audit_log_org_time", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DROP TYPE IF EXISTS audit_log_action")
