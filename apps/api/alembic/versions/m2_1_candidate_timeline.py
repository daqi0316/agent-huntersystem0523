"""M2.1: candidate relationship timeline.

Revision ID: m2_1_candidate_timeline
Revises: m1_6_rejection_analytics
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_1_candidate_timeline"
down_revision: str | Sequence[str] | None = "m1_6_rejection_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    event_type = postgresql.ENUM(
        "call", "wechat", "email", "interview", "offer", "rejection", "followup",
        "note", "commitment", "risk", "application", "status", name="candidate_timeline_event_type"
    )
    source = postgresql.ENUM("manual", "system", "ai", "integration", name="candidate_timeline_source")
    followup_status = postgresql.ENUM("pending", "done", "overdue", "cancelled", name="candidate_followup_status")
    followup_priority = postgresql.ENUM("low", "medium", "high", "urgent", name="candidate_followup_priority")
    promised_by = postgresql.ENUM(
        "candidate", "recruiter", "interviewer", "hiring_manager", name="candidate_commitment_promised_by"
    )
    commitment_status = postgresql.ENUM("open", "fulfilled", "overdue", "cancelled", name="candidate_commitment_status")
    for enum_type in (event_type, source, followup_status, followup_priority, promised_by, commitment_status):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "candidate_timeline_events",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("event_type", postgresql.ENUM(name="candidate_timeline_event_type", create_type=False), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_id", sa.String(length=255), nullable=True),
        sa.Column("source", postgresql.ENUM(name="candidate_timeline_source", create_type=False), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_timeline_events_candidate_id", "candidate_timeline_events", ["candidate_id"])
    op.create_index("ix_candidate_timeline_events_event_type", "candidate_timeline_events", ["event_type"])
    op.create_index("ix_candidate_timeline_events_occurred_at", "candidate_timeline_events", ["occurred_at"])
    op.create_index("ix_candidate_timeline_candidate_occurred", "candidate_timeline_events", ["candidate_id", "occurred_at"])
    op.create_index("ix_candidate_timeline_application", "candidate_timeline_events", ["application_id"])

    op.create_table(
        "candidate_followup_tasks",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", postgresql.ENUM(name="candidate_followup_status", create_type=False), nullable=False),
        sa.Column("priority", postgresql.ENUM(name="candidate_followup_priority", create_type=False), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=True),
        sa.Column("auto_generated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("trigger_rule", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_followup_tasks_candidate_id", "candidate_followup_tasks", ["candidate_id"])
    op.create_index("ix_candidate_followup_tasks_application_id", "candidate_followup_tasks", ["application_id"])
    op.create_index("ix_candidate_followup_tasks_due_at", "candidate_followup_tasks", ["due_at"])
    op.create_index("ix_candidate_followup_tasks_status", "candidate_followup_tasks", ["status"])
    op.create_index("ix_candidate_followup_status_due", "candidate_followup_tasks", ["status", "due_at"])
    op.create_index("ix_candidate_followup_candidate_due", "candidate_followup_tasks", ["candidate_id", "due_at"])

    op.create_table(
        "candidate_commitments",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("promised_by", postgresql.ENUM(name="candidate_commitment_promised_by", create_type=False), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="candidate_commitment_status", create_type=False), nullable=False),
        sa.Column("related_event_id", postgresql.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_event_id"], ["candidate_timeline_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_commitments_candidate_id", "candidate_commitments", ["candidate_id"])
    op.create_index("ix_candidate_commitments_status", "candidate_commitments", ["status"])
    op.create_index("ix_candidate_commitments_related_event_id", "candidate_commitments", ["related_event_id"])
    op.create_index("ix_candidate_commitments_candidate_due", "candidate_commitments", ["candidate_id", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_candidate_commitments_candidate_due", table_name="candidate_commitments")
    op.drop_index("ix_candidate_commitments_related_event_id", table_name="candidate_commitments")
    op.drop_index("ix_candidate_commitments_status", table_name="candidate_commitments")
    op.drop_index("ix_candidate_commitments_candidate_id", table_name="candidate_commitments")
    op.drop_table("candidate_commitments")
    op.drop_index("ix_candidate_followup_candidate_due", table_name="candidate_followup_tasks")
    op.drop_index("ix_candidate_followup_status_due", table_name="candidate_followup_tasks")
    op.drop_index("ix_candidate_followup_tasks_status", table_name="candidate_followup_tasks")
    op.drop_index("ix_candidate_followup_tasks_due_at", table_name="candidate_followup_tasks")
    op.drop_index("ix_candidate_followup_tasks_application_id", table_name="candidate_followup_tasks")
    op.drop_index("ix_candidate_followup_tasks_candidate_id", table_name="candidate_followup_tasks")
    op.drop_table("candidate_followup_tasks")
    op.drop_index("ix_candidate_timeline_application", table_name="candidate_timeline_events")
    op.drop_index("ix_candidate_timeline_candidate_occurred", table_name="candidate_timeline_events")
    op.drop_index("ix_candidate_timeline_events_occurred_at", table_name="candidate_timeline_events")
    op.drop_index("ix_candidate_timeline_events_event_type", table_name="candidate_timeline_events")
    op.drop_index("ix_candidate_timeline_events_candidate_id", table_name="candidate_timeline_events")
    op.drop_table("candidate_timeline_events")
    bind = op.get_bind()
    for name in (
        "candidate_commitment_status", "candidate_commitment_promised_by", "candidate_followup_priority",
        "candidate_followup_status", "candidate_timeline_source", "candidate_timeline_event_type",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
