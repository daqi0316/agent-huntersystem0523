"""add business_events table for P2-A event system

Revision ID: p2_a_business_events
Revises: a9b8c7d6e5f4
Create Date: 2026-06-10 16:00:00.000000

P2-A: 业务事件持久化 — 结构化存储业务事件（screening / jd / interview / evaluation）
- event_type: 业务事件类型（原枚举值）
- entity_type + entity_id: 关联的业务实体
- domain_fields: JSON 字段，存 match_score / decision / reason_codes 等结构化数据
- trace_id: 关联 AgentOps 执行链路
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2_a_business_events"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(32), nullable=False, server_default="", index=True),
        sa.Column("entity_id", sa.String(36), nullable=False, server_default="", index=True),
        sa.Column("domain_fields", sa.JSON, nullable=True, comment="领域数据: match_score / decision / reason_codes ..."),
        sa.Column("trace_id", sa.String(36), nullable=True, index=True, comment="关联的 AgentOps trace ID"),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("tags", sa.Text, nullable=True, comment="JSON array of tags"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True,
                   comment="事件发生时间"),
        sa.Column("duration_ms", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("business_events")
