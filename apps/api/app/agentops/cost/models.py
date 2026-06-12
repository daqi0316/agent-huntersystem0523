"""LLM 生成记录 — SQLAlchemy + Pydantic schema。

每个 LLM 调用的完整记录，含 token 消耗和估算成本。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMGenerationRecord(Base):
    """每条 LLM API 调用的持久化记录。"""

    __tablename__ = "agent_llm_generations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    trace_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    span_id: Mapped[str] = mapped_column(String(36), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    # LLM 标识
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="", index=True)

    # Token 消耗
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 性能
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 成本（预计算）
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cost_currency: Mapped[str] = mapped_column(String(8), default="USD")

    # 内容摘要（不存完整 payload，只存前 500 字符供调试）
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 失败信息
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 扩展 metadata
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<LLMGenerationRecord {self.id[:8]} "
            f"model={self.model} tokens={self.total_tokens} "
            f"cost={self.estimated_cost}>"
        )
