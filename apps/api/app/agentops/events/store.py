"""EventStore — 业务事件持久化。

提供:
  - BusinessEventModel: SQLAlchemy 模型（business_events 表）
  - EventStore: 异步 CRUD 服务
  - write_event(): 快捷写入

DB 持久化让业务事件可查询、可回溯、可用于 dashboard 分析。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, Text, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.agentops.events.schemas import BusinessEvent
from app.core.database import AsyncSessionLocal, Base

logger = logging.getLogger(__name__)


class BusinessEventModel(Base):
    """业务事件持久化模型 — business_events 表。"""

    __tablename__ = "business_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)

    # 领域数据（以 JSON 持久化）
    domain_fields: Mapped[dict[str, object] | None] = mapped_column("domain_fields", JSON, nullable=True, default=dict)

    # 执行链路关联
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 元数据
    tags: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON array of tags")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 审计时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "domain_fields": self.domain_fields or {},
            "trace_id": self.trace_id or "",
            "user_id": self.user_id or "",
            "session_id": self.session_id or "",
            "tags": json.loads(self.tags) if self.tags else [],
            "error": self.error or "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "duration_ms": self.duration_ms,
        }


class EventStore:
    """异步业务事件存储 — DB 读写。"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def save(self, event: BusinessEvent) -> BusinessEventModel | None:
        """持久化一个业务事件到 DB。"""
        db = self.db or AsyncSessionLocal()
        try:
            tags_json = json.dumps(event.tags, ensure_ascii=False) if event.tags else None
            model = BusinessEventModel(
                id=event.event_id,
                event_type=event.event_type,
                name=event.name,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                domain_fields=dict(event.domain_fields) if event.domain_fields else None,
                trace_id=event.trace_id or None,
                user_id=event.user_id or None,
                session_id=event.session_id or None,
                tags=tags_json,
                error=event.error or None,
            )
            db.add(model)
            if self.db:
                # 调用方管理 commit
                pass
            else:
                await db.commit()
                await db.refresh(model)
            return model
        except Exception as exc:
            logger.warning("EventStore.save failed: %s", exc)
            return None
        finally:
            if not self.db:
                await db.close()

    async def list(
        self,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BusinessEventModel], int]:
        """按条件查询业务事件。"""
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(BusinessEventModel)
            count_stmt = select(func.count(BusinessEventModel.id))

            if event_type:
                stmt = stmt.where(BusinessEventModel.event_type == event_type)
                count_stmt = count_stmt.where(BusinessEventModel.event_type == event_type)
            if entity_type:
                stmt = stmt.where(BusinessEventModel.entity_type == entity_type)
                count_stmt = count_stmt.where(BusinessEventModel.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(BusinessEventModel.entity_id == entity_id)
                count_stmt = count_stmt.where(BusinessEventModel.entity_id == entity_id)
            if user_id:
                stmt = stmt.where(BusinessEventModel.user_id == user_id)
                count_stmt = count_stmt.where(BusinessEventModel.user_id == user_id)
            if trace_id:
                stmt = stmt.where(BusinessEventModel.trace_id == trace_id)
                count_stmt = count_stmt.where(BusinessEventModel.trace_id == trace_id)

            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            stmt = stmt.order_by(desc(BusinessEventModel.created_at)).offset(offset).limit(limit)
            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total
        finally:
            if not self.db:
                await db.close()


async def write_event(
    event: BusinessEvent,
    db: AsyncSession | None = None,
) -> BusinessEventModel | None:
    """快捷写入 — 单函数入口。"""
    store = EventStore(db=db)
    return await store.save(event)
