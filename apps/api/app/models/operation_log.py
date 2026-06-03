import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Float, Boolean, Enum as SAEnum, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OperationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class ErrorCategory(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    BUSINESS = "business"


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[OperationStatus] = mapped_column(
        String(17), nullable=False, default=OperationStatus.PENDING, index=True,
    )
    error_category: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True,
        comment="system=LLM/DB故障(报警), user=用户输入错(记录不报警), business=业务拒绝(正常)",
    )
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, comment="不可变标记，true 后禁止 update")
    superseded_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, comment="修正链：如需更正，新记录指向被替代的记录",
    )
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_oplog_agent_status_created", "agent_name", "status", "created_at"),
        Index("idx_oplog_error_cat", "error_category", "created_at"),
    )
