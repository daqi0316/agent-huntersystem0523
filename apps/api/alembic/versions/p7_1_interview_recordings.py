"""P7-1: interview_recordings table for interview audio MVP.

Revision ID: p7_1_interview_recordings
Revises: merge_p6_12_v1_2
Create Date: 2026-06-08 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "p7_1_interview_recordings"
down_revision: Union[str, Sequence[str], None] = "merge_p6_12_v1_2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_recordings",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("interview_id", postgresql.UUID(), nullable=False),
        sa.Column("recording_id", sa.String(length=128), nullable=False),
        sa.Column(
            "storage_backend",
            sa.Enum("minio", "local", name="interview_recording_storage_backend"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=500), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "uploading", "recorded", "transcribing", "transcribed", "failed", "deleted",
                name="interview_recording_status",
            ),
            nullable=False,
        ),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("transcript_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("consent_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id"),
    )
    op.create_index("ix_interview_recordings_interview_id", "interview_recordings", ["interview_id"])
    op.create_index("ix_interview_recordings_status", "interview_recordings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_interview_recordings_status", table_name="interview_recordings")
    op.drop_index("ix_interview_recordings_interview_id", table_name="interview_recordings")
    op.drop_table("interview_recordings")
    sa.Enum(name="interview_recording_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="interview_recording_storage_backend").drop(op.get_bind(), checkfirst=True)
