"""AgentFeedbackModel — feedback 持久化模型。

DB 层面不限制 category / source 枚举值，允许前向兼容的新枚举标签。
校验交由 Pydantic schema 层处理。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, JSON, String, Text, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.agentops.feedback.schemas import FeedbackCategory, FeedbackResponse, FeedbackSource, FeedbackStats
from app.core.database import AsyncSessionLocal, Base


class AgentFeedbackModel(Base):
    """用户反馈持久化模型 — agent_feedback 表。"""

    __tablename__ = "agent_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="end_user", index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    # 反馈文本理由
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 执行链路关联（与 agentops tracing 打通）
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 业务实体关联（若通过 entity 引用而非 trace 链路）
    target_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 谁提交的反馈
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # 标签与元数据
    tags: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON array of tags")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata_json", JSON, nullable=True)

    # 审计时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC),
    )

    def to_response(self) -> FeedbackResponse:
        tags_list: list[str] = json.loads(self.tags) if self.tags else []
        return FeedbackResponse(
            id=self.id,
            category=FeedbackCategory(self.category),
            source=FeedbackSource(self.source),
            score=self.score,
            reason=self.reason or "",
            trace_id=self.trace_id or "",
            span_id=self.span_id or "",
            message_id=self.message_id or "",
            session_id=self.session_id or "",
            target_entity_type=self.target_entity_type or "",
            target_entity_id=self.target_entity_id or "",
            user_id=self.user_id or "",
            tags=tags_list,
            created_at=self.created_at.isoformat() if self.created_at else "",
            updated_at=self.updated_at.isoformat() if self.updated_at else "",
        )


class FeedbackStore:
    """反馈数据访问层 — DB 读写。"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def save(self, model: AgentFeedbackModel) -> AgentFeedbackModel | None:
        """持久化一条反馈。"""
        db = self.db or AsyncSessionLocal()
        try:
            db.add(model)
            if not self.db:
                await db.commit()
                await db.refresh(model)
            return model
        except Exception:
            if not self.db:
                await db.rollback()
            raise
        finally:
            if not self.db:
                await db.close()

    async def get(self, feedback_id: str) -> AgentFeedbackModel | None:
        """按 ID 查询。"""
        db = self.db or AsyncSessionLocal()
        try:
            result = await db.execute(
                select(AgentFeedbackModel).where(AgentFeedbackModel.id == feedback_id)
            )
            return result.scalar_one_or_none()
        finally:
            if not self.db:
                await db.close()

    async def list(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentFeedbackModel], int]:
        """按条件查询反馈列表（按创建时间倒序）。"""
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(AgentFeedbackModel)
            count_stmt = select(func.count(AgentFeedbackModel.id))

            if category:
                stmt = stmt.where(AgentFeedbackModel.category == category)
                count_stmt = count_stmt.where(AgentFeedbackModel.category == category)
            if source:
                stmt = stmt.where(AgentFeedbackModel.source == source)
                count_stmt = count_stmt.where(AgentFeedbackModel.source == source)
            if trace_id:
                stmt = stmt.where(AgentFeedbackModel.trace_id == trace_id)
                count_stmt = count_stmt.where(AgentFeedbackModel.trace_id == trace_id)
            if user_id:
                stmt = stmt.where(AgentFeedbackModel.user_id == user_id)
                count_stmt = count_stmt.where(AgentFeedbackModel.user_id == user_id)
            if session_id:
                stmt = stmt.where(AgentFeedbackModel.session_id == session_id)
                count_stmt = count_stmt.where(AgentFeedbackModel.session_id == session_id)
            if entity_type:
                stmt = stmt.where(AgentFeedbackModel.target_entity_type == entity_type)
                count_stmt = count_stmt.where(AgentFeedbackModel.target_entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(AgentFeedbackModel.target_entity_id == entity_id)
                count_stmt = count_stmt.where(AgentFeedbackModel.target_entity_id == entity_id)

            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            stmt = stmt.order_by(desc(AgentFeedbackModel.created_at)).offset(offset).limit(limit)
            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total
        finally:
            if not self.db:
                await db.close()

    async def stats(
        self,
        *,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> FeedbackStats:
        """聚合统计 — 按 category 计算平均分和条数。"""
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(
                AgentFeedbackModel.category,
                func.avg(AgentFeedbackModel.score).label("avg_score"),
                func.count(AgentFeedbackModel.id).label("count"),
            )
            if trace_id:
                stmt = stmt.where(AgentFeedbackModel.trace_id == trace_id)
            if user_id:
                stmt = stmt.where(AgentFeedbackModel.user_id == user_id)
            if session_id:
                stmt = stmt.where(AgentFeedbackModel.session_id == session_id)
            stmt = stmt.group_by(AgentFeedbackModel.category)

            result = await db.execute(stmt)
            rows = result.all()

            category_stats: dict[str, dict[str, float]] = {}
            total_count = 0
            total_score_sum = 0.0
            for row in rows:
                cat = row[0]
                avg_score = float(row[1]) if row[1] is not None else 0.0
                count = int(row[2])
                category_stats[cat] = {"avg_score": round(avg_score, 4), "count": count}
                total_count += count
                total_score_sum += avg_score * count

            overall_avg = round(total_score_sum / total_count, 4) if total_count > 0 else 0.0
            return FeedbackStats(
                total_count=total_count,
                overall_avg_score=overall_avg,
                category_stats=category_stats,
            )
        finally:
            if not self.db:
                await db.close()
