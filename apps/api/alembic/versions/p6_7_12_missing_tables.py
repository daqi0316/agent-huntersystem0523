"""P6-12 + P6-7 漏建表补: csm_task + 3 experiment 表。

Revision ID: p6_7_12_missing_tables
Revises: p6_5_notification_meta
Create Date: 2026-06-06 21:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_7_12_missing_tables"
down_revision: Union[str, Sequence[str], None] = "p6_5_notification_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "csm_task",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum("health_drop", "no_login_7d", "trial_ending", "payment_failed", "churn_risk", "manual", name="csm_task_type"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("P1", "P2", "P3", name="csm_task_priority"),
            nullable=False, server_default="P3",
        ),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "resolved", "closed", name="csm_task_status"),
            nullable=False, server_default="open",
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", sa.String(length=36), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_csm_task_org_status", "csm_task", ["org_id", "status"])
    op.create_index("ix_csm_task_user_id", "csm_task", ["user_id"])

    op.create_table(
        "experiment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("variants", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("traffic_pct", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("primary_metric", sa.String(length=64), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_org_id", "experiment", ["org_id"])

    op.create_table(
        "experiment_assignment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("variant", sa.String(length=64), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_assignment_experiment_id", "experiment_assignment", ["experiment_id"])
    op.create_index("ix_experiment_assignment_user_id", "experiment_assignment", ["user_id"])

    op.create_table(
        "experiment_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("variant", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_event_experiment_id", "experiment_event", ["experiment_id"])
    op.create_index("ix_experiment_event_user_id", "experiment_event", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_event_user_id", table_name="experiment_event")
    op.drop_index("ix_experiment_event_experiment_id", table_name="experiment_event")
    op.drop_table("experiment_event")
    op.drop_index("ix_experiment_assignment_user_id", table_name="experiment_assignment")
    op.drop_index("ix_experiment_assignment_experiment_id", table_name="experiment_assignment")
    op.drop_table("experiment_assignment")
    op.drop_index("ix_experiment_org_id", table_name="experiment")
    op.drop_table("experiment")
    op.drop_index("ix_csm_task_user_id", table_name="csm_task")
    op.drop_index("ix_csm_task_org_status", table_name="csm_task")
    op.drop_table("csm_task")
    for e in ("csm_task_status", "csm_task_priority", "csm_task_type"):
        sa.Enum(name=e).drop(op.get_bind(), checkfirst=True)
