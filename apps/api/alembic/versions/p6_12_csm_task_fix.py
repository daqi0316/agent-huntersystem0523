"""P6-12: 修 csm_task 表 (与 model 字段对齐: type/severity/title/description)。

原 p6_7_12_missing_tables 用了错的字段名 (task_type/priority/reason), 改用 model 实际字段。

Revision ID: p6_12_csm_task_fix
Revises: p6_7_12_missing_tables
Create Date: 2026-06-06 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_12_csm_task_fix"
down_revision: Union[str, Sequence[str], None] = "p6_7_12_missing_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "csm_task" in inspector.get_table_names():
        op.drop_index("ix_csm_task_user_id", table_name="csm_task")
        op.drop_index("ix_csm_task_org_status", table_name="csm_task")
        op.drop_table("csm_task")
    for e in ("csm_task_status", "csm_task_priority", "csm_task_type"):
        sa.Enum(name=e).drop(bind, checkfirst=True)

    op.create_table(
        "csm_task",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column(
            "type",
            sa.Enum("health_drop", "no_login_7d", "trial_ending", "payment_failed", "churn_risk", "manual", name="csm_task_type"),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("P1", "P2", "P3", name="csm_task_severity"),
            nullable=False, server_default="P3",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "in_progress", "done", "dismissed", name="csm_task_status"),
            nullable=False, server_default="pending",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("assigned_to", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_csm_task_org_id", "csm_task", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_csm_task_user_id", table_name="csm_task")
    op.drop_index("ix_csm_task_org_id", table_name="csm_task")
    op.drop_table("csm_task")
    for e in ("csm_task_status", "csm_task_severity", "csm_task_type"):
        sa.Enum(name=e).drop(op.get_bind(), checkfirst=True)
