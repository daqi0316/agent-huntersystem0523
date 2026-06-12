"""p2_c_agent_llm_generations — add agent_llm_generations table for cost tracking

Revision ID: p2_c_agent_llm_generations
Revises: p2_c_agent_experiment
Create Date: 2026-06-11 10:00:00.000000

P2-C Stage 15: LLM 成本追踪
- 存储每次 LLM API 调用的 token 消耗和估算成本
- 支持按模型/用户/时间维度聚合查询
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p2_c_agent_llm_generations"
down_revision: Union[str, Sequence[str], None] = "p2_c_agent_experiment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_llm_generations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("span_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("user_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("session_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default=""),
        # LLM 标识
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        # Token 消耗
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        # 性能
        sa.Column("duration_ms", sa.Float(), nullable=True),
        # 成本
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cost_currency", sa.String(8), nullable=False, server_default="USD"),
        # 内容摘要
        sa.Column("input_preview", sa.Text(), nullable=True),
        sa.Column("output_preview", sa.Text(), nullable=True),
        # 失败
        sa.Column("error", sa.Text(), nullable=True),
        # 扩展 metadata
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        # 时间戳
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 索引
    op.create_index("ix_llm_gen_created_at", "agent_llm_generations", ["created_at"])
    op.create_index("ix_llm_gen_model", "agent_llm_generations", ["model"])
    op.create_index("ix_llm_gen_user_id", "agent_llm_generations", ["user_id"])
    op.create_index("ix_llm_gen_trace_id", "agent_llm_generations", ["trace_id"])
    op.create_index("ix_llm_gen_tenant_id", "agent_llm_generations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_gen_tenant_id", table_name="agent_llm_generations")
    op.drop_index("ix_llm_gen_trace_id", table_name="agent_llm_generations")
    op.drop_index("ix_llm_gen_user_id", table_name="agent_llm_generations")
    op.drop_index("ix_llm_gen_model", table_name="agent_llm_generations")
    op.drop_index("ix_llm_gen_created_at", table_name="agent_llm_generations")
    op.drop_table("agent_llm_generations")
