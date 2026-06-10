"""m3_4: 公司专属招聘知识库 — company_recruiting_knowledge_items。

P2-2: 在 Qdrant RAG 之上加结构化知识管理：
- 可引用、可过期、可版本化
- 自动沉淀知识必须 proposed，人工确认后才 active

Revision ID: m3_4_company_knowledge_items
Revises: m3_3
Create Date: 2026-06-09 16:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "m3_4_company_knowledge_items"
down_revision: Union[str, Sequence[str], None] = "m3_3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_recruiting_knowledge_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False, index=True),
        sa.Column("job_profile_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("job_profiles.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column(
            "knowledge_type",
            sa.Enum("interviewer_preference", "team_culture", "hiring_manager_preference",
                     "historical_lesson", "compensation_policy", "rejection_pattern",
                     "successful_profile", "interview_question",
                     name="knowledge_item_type", values_callable=lambda x: [e.value for e in x]),
            nullable=False, index=True,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "proposed", "active", "expired", "archived",
                     name="knowledge_item_status", values_callable=lambda x: [e.value for e in x]),
            nullable=False, server_default="draft", index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("embedding_id", sa.String(128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crk_org_type", "company_recruiting_knowledge_items", ["org_id", "knowledge_type"])
    op.create_index("ix_crk_org_status", "company_recruiting_knowledge_items", ["org_id", "status"])
    op.create_index("ix_crk_org_job_profile", "company_recruiting_knowledge_items", ["org_id", "job_profile_id"])
    op.create_index("ix_crk_effective", "company_recruiting_knowledge_items", ["org_id", "effective_from", "effective_to"])


def downgrade() -> None:
    op.drop_table("company_recruiting_knowledge_items")
    op.execute("DROP TYPE IF EXISTS knowledge_item_type")
    op.execute("DROP TYPE IF EXISTS knowledge_item_status")
