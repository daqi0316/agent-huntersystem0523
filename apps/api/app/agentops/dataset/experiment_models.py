"""Experiment DB models — 实验定义与运行记录。

ExperimentModel: 描述一次实验（名称、评估方法、配置变体）
ExperimentRunModel: 记录一次实验执行的结果
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.agentops.dataset.experiment_schemas import (
    ExperimentResponse,
    ExperimentRunResponse,
    ExperimentRunSummaryResponse,
)
from app.core.database import AsyncSessionLocal, Base


class ExperimentModel(Base):
    """实验定义 — agent_experiment 表。"""

    __tablename__ = "agent_experiment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # dataset item 关联
    dataset_item_ids: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of dataset item IDs"
    )

    # 评估配置
    evaluator_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rule_based")
    evaluator_config: Mapped[dict[str, Any] | None] = mapped_column("evaluator_config", JSON, nullable=True)

    # 变体配置
    variants: Mapped[dict[str, Any] | None] = mapped_column("variants", JSON, nullable=True)

    # 标签
    tags: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON array of tags")

    # 创建者
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # 审计时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC),
    )

    def to_response(self) -> ExperimentResponse:
        return ExperimentResponse(
            id=self.id,
            name=self.name,
            description=self.description or "",
            status=self.status,
            dataset_item_ids=json.loads(self.dataset_item_ids) if self.dataset_item_ids else [],
            evaluator_type=self.evaluator_type,
            evaluator_config=self.evaluator_config or {},
            variants=self.variants if isinstance(self.variants, list) else [],
            tags=json.loads(self.tags) if self.tags else [],
            created_by=self.created_by or "",
            created_at=self.created_at.isoformat() if self.created_at else "",
            updated_at=self.updated_at.isoformat() if self.updated_at else "",
        )


class ExperimentRunModel(Base):
    """实验运行记录 — agent_experiment_run 表。"""

    __tablename__ = "agent_experiment_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # 统计
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    passed_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)

    # 详细结果
    results: Mapped[dict[str, Any] | None] = mapped_column("results", JSON, nullable=True)

    # 时间
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 审计
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )

    def to_response(self) -> ExperimentRunResponse:
        return ExperimentRunResponse(
            id=self.id,
            experiment_id=self.experiment_id,
            variant_index=self.variant_index,
            status=self.status,
            total_items=self.total_items,
            passed_items=self.passed_items,
            failed_items=self.failed_items,
            avg_score=self.avg_score,
            results=self.results if isinstance(self.results, list) else [],
            started_at=self.started_at.isoformat() if self.started_at else "",
            completed_at=self.completed_at.isoformat() if self.completed_at else "",
            duration_ms=self.duration_ms,
            error_message=self.error_message or "",
        )

    def to_summary(self) -> ExperimentRunSummaryResponse:
        return ExperimentRunSummaryResponse(
            id=self.id,
            experiment_id=self.experiment_id,
            variant_index=self.variant_index,
            status=self.status,
            total_items=self.total_items,
            passed_items=self.passed_items,
            avg_score=self.avg_score,
            started_at=self.started_at.isoformat() if self.started_at else "",
            completed_at=self.completed_at.isoformat() if self.completed_at else "",
            duration_ms=self.duration_ms,
        )


class ExperimentStore:
    """Experiment 数据访问层。"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def save_experiment(self, model: ExperimentModel) -> ExperimentModel | None:
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

    async def get_experiment(self, experiment_id: str) -> ExperimentModel | None:
        db = self.db or AsyncSessionLocal()
        try:
            result = await db.execute(
                select(ExperimentModel).where(ExperimentModel.id == experiment_id)
            )
            return result.scalar_one_or_none()
        finally:
            if not self.db:
                await db.close()

    async def list_experiments(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ExperimentModel], int]:
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(ExperimentModel)
            count_stmt = select(func.count(ExperimentModel.id))
            if status:
                stmt = stmt.where(ExperimentModel.status == status)
                count_stmt = count_stmt.where(ExperimentModel.status == status)

            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            stmt = stmt.order_by(desc(ExperimentModel.created_at)).offset(offset).limit(limit)
            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total
        finally:
            if not self.db:
                await db.close()

    async def save_run(self, model: ExperimentRunModel) -> ExperimentRunModel | None:
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

    async def get_run(self, run_id: str) -> ExperimentRunModel | None:
        db = self.db or AsyncSessionLocal()
        try:
            result = await db.execute(
                select(ExperimentRunModel).where(ExperimentRunModel.id == run_id)
            )
            return result.scalar_one_or_none()
        finally:
            if not self.db:
                await db.close()

    async def list_runs_by_experiment(
        self, experiment_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExperimentRunModel], int]:
        db = self.db or AsyncSessionLocal()
        try:
            stmt = select(ExperimentRunModel).where(
                ExperimentRunModel.experiment_id == experiment_id
            )
            count_stmt = select(func.count(ExperimentRunModel.id)).where(
                ExperimentRunModel.experiment_id == experiment_id
            )
            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            stmt = stmt.order_by(desc(ExperimentRunModel.created_at)).offset(offset).limit(limit)
            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total
        finally:
            if not self.db:
                await db.close()
