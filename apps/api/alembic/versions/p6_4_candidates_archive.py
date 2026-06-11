"""P6-4: 候选人数归档表 — candidates_archive (180 天冷数据)。

创建 ``candidates_archive`` 表，结构与 ``candidates`` 一致，增加 ``archived_at`` 列。
归档脚本将 > 180 天未更新的终端状态候选人移入此表。

Revision ID: p6_4_candidates_archive
Revises: m3_6_red_flag_rules
Create Date: 2026-06-11 22:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_4_candidates_archive"
down_revision: Union[str, Sequence[str], None] = "m3_6_red_flag_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidates_archive",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column("education", sa.Text(), nullable=True),
        sa.Column("current_company", sa.String(length=255), nullable=True),
        sa.Column("current_title", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "archived", "blacklisted", "pending_eval", "evaluating", "evaluated", "in_interview", "completed", "failed", name="candidate_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "recruitment_state",
            sa.Enum(
                "new_application", "screening", "screening_passed", "screening_rejected",
                "first_interview_pending", "first_interview_scheduled", "first_interview_feedback_pending",
                "first_interview_passed", "first_interview_rejected",
                "second_interview_pending", "second_interview_scheduled", "second_interview_feedback_pending",
                "second_interview_passed", "second_interview_rejected",
                "offer_negotiation", "offer_sent", "offer_accepted", "offer_rejected",
                "onboarding_pending", "hired", "probation_tracking", "probation_passed",
                "probation_rejected",
                name="recruitment_candidate_state",
            ),
            nullable=False,
            server_default="new_application",
        ),
        sa.Column("sourcing_task_id", sa.String(length=64), nullable=True),
        sa.Column("source_platforms", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("source_urls", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("ai_analysis", sa.JSON(), nullable=True),
        sa.Column("match_scores", sa.JSON(), nullable=True),
        sa.Column("data_quality_score", sa.Float(), nullable=True),
        sa.Column("dedup_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        # ── 归档元数据 ──
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archive_reason", sa.String(length=64), nullable=False, server_default="180d_auto"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_candidates_archive_email"),
    )
    op.create_index("ix_candidates_archive_org_id", "candidates_archive", ["org_id"])
    op.create_index("ix_candidates_archive_archived_at", "candidates_archive", ["archived_at"])
    op.create_index("ix_candidates_archive_status", "candidates_archive", ["status"])


def downgrade() -> None:
    op.drop_index("ix_candidates_archive_status", table_name="candidates_archive")
    op.drop_index("ix_candidates_archive_archived_at", table_name="candidates_archive")
    op.drop_index("ix_candidates_archive_org_id", table_name="candidates_archive")
    op.drop_table("candidates_archive")
    # drop enum types created by this migration (safe because nothing else uses them)
    sa.Enum(name="candidate_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="recruitment_candidate_state").drop(op.get_bind(), checkfirst=True)
