import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OperationStatsHourly(Base):
    """Agent 操作小时级聚合 — 避免实时扫全表。"""

    __tablename__ = "operation_stats_hourly"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bucket_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    total_ops: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    system_error_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("bucket_hour", "agent_name", name="uq_stats_hour_agent"),
    )
