"""LlmProvider — 多模型接入数据模型。

每个记录代表一个可用的 LLM 模型配置（提供者 + 模型 + Key）。
全表最多一个 is_primary=True，最多一个 is_fallback=True。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class LlmProviderType(str, Enum):
    """Provider 类型枚举 — 新增类型只需加一个 enum value + 一个 Provider 类。"""

    OPENAI_COMPAT = "openai_compat"
    ANTHROPIC = "anthropic"


class LlmProvider(Base):
    """LLM 模型提供者配置。"""

    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="展示名，如 DeepSeek V3"
    )
    provider_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="openai_compat / anthropic"
    )

    # ── 连接配置 ──
    base_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="API 端点地址"
    )
    model_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="API 用的模型名"
    )
    api_key_enc: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AES-256-GCM 加密的 API Key"
    )
    key_salt: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="密钥派生盐，支持轮换"
    )
    key_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次换 Key 时间"
    )

    # ── 运行时参数 ──
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False, comment="单次请求超时（秒）"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False, comment="失败重试次数"
    )

    # ── 能力声明 ──
    capabilities: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="模型能力声明，如 {chat, function_calling, embedding, vision, ...}",
    )

    # ── 主备标记 ──
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否主模型（全表最多一个 true）"
    )
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否备用模型（全表最多一个 true）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="系统启用状态"
    )

    # ── 排序 + 元数据 ──
    sort_order: Mapped[int] = mapped_column(
        Integer, default=100, nullable=False, comment="列表展示排序"
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="使用者备注"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ── 约束 ──
    __table_args__ = (
        CheckConstraint(
            "NOT (is_primary AND is_fallback)",
            name="ck_llm_providers_not_both_primary_fallback",
        ),
        Index(
            "idx_llm_providers_single_primary",
            is_primary,
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
        Index(
            "idx_llm_providers_single_fallback",
            is_fallback,
            unique=True,
            postgresql_where=text("is_fallback = true"),
        ),
        Index(
            "idx_llm_providers_active",
            is_active,
            postgresql_where=text("is_active = true"),
        ),
    )

    def __repr__(self) -> str:
        return f"<LlmProvider {self.name} ({self.provider_type}) primary={self.is_primary} fallback={self.is_fallback}>"
