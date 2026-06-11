import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SourcingTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourcingTask(Base):
    __tablename__ = "sourcing_tasks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization.id"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    # 任务参数
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, comment="搜索关键词")
    platforms: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, comment="目标平台列表")
    filters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, comment="筛选条件: 城市/薪资/年限等")

    # 执行状态 — 用 String 而非 SAEnum 避免 enum type migration 复杂度
    status: Mapped[str] = mapped_column(
        String(20), default=SourcingTaskStatus.PENDING.value, index=True,
        comment="pending/running/completed/partial/failed/cancelled",
    )
    progress: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, comment="各平台进度快照")
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    after_dedup: Mapped[int] = mapped_column(Integer, default=0)
    new_this_run: Mapped[int] = mapped_column(Integer, default=0, comment="本批新增(去重后)")

    # 调度
    priority: Mapped[int] = mapped_column(Integer, default=50, comment="优先级 0-100")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 审计
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关联
    logs = relationship("CrawlLog", back_populates="task", lazy="dynamic")
