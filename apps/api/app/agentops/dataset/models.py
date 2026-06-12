"""ExperimentDatasetItemModel — dataset item 持久化模型。

与 feedback 采用类似策略：DB 层不限制 category/source 枚举值，
校验交由 Pydantic schema 层处理。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.agentops.dataset.schemas import DatasetItemCategory, DatasetItemResponse, DatasetItemSource, DatasetStats
from app.core.database import AsyncSessionLocal, Base


class ExperimentDatasetItemModel(Base):
    """回归测试集数据项 — agent_dataset_item 表。"""

    __tablename__ = "agent_dataset_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual", index=True)

    # 原始执行链路关联
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 业务实体关联
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 核心数据快照
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column("input_snapshot", JSON, nullable=True)
    expected_output: Mapped[dict[str, Any] | None] = mapped_column("expected_output", JSON, nullable=True)
    actual_output: Mapped[dict[str, Any] | None] = mapped_column("actual_output", JSON, nullable=True)

    # 反馈关联
    feedback_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # 标签与描述
    tags: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON array of tags")
    is_bad_case: Mapped[bool] = mapped_column(default=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 人工修正
    corrected_output: Mapped[dict[str, Any] | None] = mapped_column("corrected_output", JSON, nullable=True)
    correction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 评分与优先级
    priority: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    # 自由元数据
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata_json", JSON, nullable=True)

    # 审计时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC),
    )

    def to_response(self) -> DatasetItemResponse:
        tags_list: list[str] = json.loads(self.tags) if self.tags else []
        return DatasetItemResponse(
            id=self.id,
            category=self.category,
            source=self.source,
            trace_id=self.trace_id or "",
            span_id=self.span_id or "",
            session_id=self.session_id or "",
            entity_type=self.entity_type or "",
            entity_id=self.entity_id or "",
            input_snapshot=self.input_snapshot or {},
            expected_output=self.expected_output or {},
            actual_output=self.actual_output or {},
            feedback_id=self.feedback_id or "",
            tags=tags_list,
            is_bad_case=self.is_bad_case or False,
            description=self.description or "",
            corrected_output=self.corrected_output,
            correction_notes=self.correction_notes or "",
            priority=self.priority or 0,
            score=self.score or 0.0,
            metadata=self.metadata_json or {},
            created_at=self.created_at.isoformat() if self.created_at else "",
            updated_at=self.updated_at.isoformat() if self.updated_at else "",
        )


class DatasetStore:
    """Dataset 数据访问层 — DB 读写。"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def save(self, model: ExperimentDatasetItemModel) -> ExperimentDatasetItemModel | None:
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

    async def get(self, item_id: str) -> ExperimentDatasetItemModel | None:
        db = self.db or AsyncSessionLocal()
        try:
            result = await db.execute(
                select(ExperimentDatasetItemModel).where(ExperimentDatasetItemModel.id == item_id)
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
        session_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        feedback_id: str | None = None,
        is_bad_case: bool | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ExperimentDatasetItemModel], int]:
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(ExperimentDatasetItemModel)
            count_stmt = select(func.count(ExperimentDatasetItemModel.id))

            if category:
                stmt = stmt.where(ExperimentDatasetItemModel.category == category)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.category == category)
            if source:
                stmt = stmt.where(ExperimentDatasetItemModel.source == source)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.source == source)
            if trace_id:
                stmt = stmt.where(ExperimentDatasetItemModel.trace_id == trace_id)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.trace_id == trace_id)
            if session_id:
                stmt = stmt.where(ExperimentDatasetItemModel.session_id == session_id)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.session_id == session_id)
            if entity_type:
                stmt = stmt.where(ExperimentDatasetItemModel.entity_type == entity_type)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(ExperimentDatasetItemModel.entity_id == entity_id)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.entity_id == entity_id)
            if feedback_id:
                stmt = stmt.where(ExperimentDatasetItemModel.feedback_id == feedback_id)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.feedback_id == feedback_id)
            if is_bad_case is not None:
                stmt = stmt.where(ExperimentDatasetItemModel.is_bad_case == is_bad_case)
                count_stmt = count_stmt.where(ExperimentDatasetItemModel.is_bad_case == is_bad_case)

            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            stmt = stmt.order_by(desc(ExperimentDatasetItemModel.created_at)).offset(offset).limit(limit)
            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total
        finally:
            if not self.db:
                await db.close()

    async def delete(self, item_id: str) -> bool:
        db = self.db or AsyncSessionLocal()
        try:
            result = await db.execute(
                select(ExperimentDatasetItemModel).where(ExperimentDatasetItemModel.id == item_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return False
            await db.delete(model)
            if not self.db:
                await db.commit()
            return True
        except Exception:
            if not self.db:
                await db.rollback()
            raise
        finally:
            if not self.db:
                await db.close()

    async def stats(self) -> DatasetStats:
        db = self.db or AsyncSessionLocal()
        try:
            # total
            total_result = await db.execute(select(func.count(ExperimentDatasetItemModel.id)))
            total_count = total_result.scalar() or 0

            # category counts
            cat_result = await db.execute(
                select(
                    ExperimentDatasetItemModel.category,
                    func.count(ExperimentDatasetItemModel.id).label("count"),
                ).group_by(ExperimentDatasetItemModel.category)
            )
            category_counts: dict[str, int] = {}
            for row in cat_result.all():
                category_counts[str(row[0])] = int(row[1])

            # source counts
            src_result = await db.execute(
                select(
                    ExperimentDatasetItemModel.source,
                    func.count(ExperimentDatasetItemModel.id).label("count"),
                ).group_by(ExperimentDatasetItemModel.source)
            )
            source_counts: dict[str, int] = {}
            for row in src_result.all():
                source_counts[str(row[0])] = int(row[1])

            # bad case count
            bad_result = await db.execute(
                select(func.count(ExperimentDatasetItemModel.id)).where(
                    ExperimentDatasetItemModel.is_bad_case == True  # noqa: E712
                )
            )
            bad_case_count = bad_result.scalar() or 0

            # recent 7 days
            from datetime import timedelta, timezone
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            recent_result = await db.execute(
                select(func.count(ExperimentDatasetItemModel.id)).where(
                    ExperimentDatasetItemModel.created_at >= week_ago
                )
            )
            recent_items = recent_result.scalar() or 0

            return DatasetStats(
                total_count=total_count,
                category_counts=category_counts,
                source_counts=source_counts,
                bad_case_count=bad_case_count,
                recent_items=recent_items,
            )
        finally:
            if not self.db:
                await db.close()
