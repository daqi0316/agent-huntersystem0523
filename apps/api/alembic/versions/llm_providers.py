"""v2.0: llm_providers 表 — 多模型接入架构

- 建 llm_provider_type enum
- 建 llm_providers 表（含 capabilities JSONB + 唯一索引约束）
- 插入 5 条种子预设数据

Revision ID: llm_providers
Revises: p7_1_interview_recordings
Create Date: 2026-06-12

背景: 原有 LLM 层只支持单模型（通过 LLM_PROVIDER 环境变量切换）。
新架构支持多模型并行注册、主备切换、能力声明。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "llm_providers"
down_revision: Union[str, Sequence[str], None] = "043c3b04ac57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── 预设种子数据 ──

PRESETS = [
    {
        "name": "本地 OMLX",
        "provider_type": "openai_compat",
        "base_url": "http://localhost:8000/v1",
        "model_name": "Qwen3.6-35B-A3B-4bit",
        "api_key_enc": None,
        "capabilities": {
            "chat": True,
            "function_calling": True,
            "streaming": True,
            "embedding": True,
            "vision": False,
            "max_context_window": 128000,
            "max_output_tokens": 4096,
        },
        "is_primary": True,
        "is_fallback": False,
        "timeout_seconds": 30,
        "max_retries": 2,
        "sort_order": 10,
    },
    {
        "name": "DeepSeek V3",
        "provider_type": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "api_key_enc": None,
        "capabilities": {
            "chat": True,
            "function_calling": True,
            "streaming": True,
            "embedding": False,
            "vision": False,
            "max_context_window": 128000,
            "max_output_tokens": 8192,
        },
        "is_primary": False,
        "is_fallback": True,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 20,
    },
    {
        "name": "GPT-4o",
        "provider_type": "openai_compat",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "api_key_enc": None,
        "capabilities": {
            "chat": True,
            "function_calling": True,
            "streaming": True,
            "embedding": True,
            "vision": True,
            "max_context_window": 128000,
            "max_output_tokens": 16384,
        },
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 30,
    },
    {
        "name": "Claude Sonnet",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model_name": "claude-sonnet-4-20250514",
        "api_key_enc": None,
        "capabilities": {
            "chat": True,
            "function_calling": True,
            "streaming": True,
            "embedding": False,
            "vision": True,
            "max_context_window": 200000,
            "max_output_tokens": 8192,
        },
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 40,
    },
    {
        "name": "通义千问 Max",
        "provider_type": "openai_compat",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-max",
        "api_key_enc": None,
        "capabilities": {
            "chat": True,
            "function_calling": True,
            "streaming": True,
            "embedding": True,
            "vision": True,
            "max_context_window": 128000,
            "max_output_tokens": 8192,
        },
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 50,
    },
]


def upgrade() -> None:
    # ── 建表（enum 由 provider_type 列自动创建）──
    op.create_table(
        "llm_providers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "provider_type",
            sa.Enum("openai_compat", "anthropic", name="llm_provider_type"),
            nullable=False,
        ),
        sa.Column("base_url", sa.String(1024), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("api_key_enc", sa.Text, nullable=True),
        sa.Column("key_salt", sa.String(64), nullable=True),
        sa.Column("key_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("30")),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default=sa.text("2")),
        sa.Column("capabilities", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_fallback", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "NOT (is_primary AND is_fallback)",
            name="ck_llm_providers_not_both_primary_fallback",
        ),
    )

    # ── 索引 ──
    op.create_index(
        "idx_llm_providers_single_primary",
        "llm_providers",
        ["is_primary"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )
    op.create_index(
        "idx_llm_providers_single_fallback",
        "llm_providers",
        ["is_fallback"],
        unique=True,
        postgresql_where=sa.text("is_fallback = true"),
    )
    op.create_index(
        "idx_llm_providers_active",
        "llm_providers",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── 种子数据 ──
    import json

    for preset in PRESETS:
        row = dict(preset)
        caps_json = json.dumps(row.pop("capabilities"))
        op.execute(
            sa.text(
                """
                INSERT INTO llm_providers
                    (id, name, provider_type, base_url, model_name, api_key_enc,
                     capabilities, is_primary, is_fallback, timeout_seconds, max_retries, sort_order)
                VALUES
                    (gen_random_uuid(), :name, CAST(:provider_type AS llm_provider_type),
                     :base_url, :model_name, :api_key_enc,
                     CAST(:capabilities AS jsonb), :is_primary, :is_fallback,
                     :timeout_seconds, :max_retries, :sort_order)
                """
            ).params(
                name=row["name"],
                provider_type=row["provider_type"],
                base_url=row["base_url"],
                model_name=row["model_name"],
                api_key_enc=row["api_key_enc"],
                capabilities=caps_json,
                is_primary=row["is_primary"],
                is_fallback=row["is_fallback"],
                timeout_seconds=row["timeout_seconds"],
                max_retries=row["max_retries"],
                sort_order=row["sort_order"],
            )
        )


def downgrade() -> None:
    op.drop_table("llm_providers")
    sa.Enum(name="llm_provider_type").drop(op.get_bind())
