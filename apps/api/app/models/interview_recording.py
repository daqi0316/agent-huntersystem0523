import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class InterviewRecordingStorageBackend(str, enum.Enum):
    MINIO = "minio"
    LOCAL = "local"


class InterviewRecordingStatus(str, enum.Enum):
    UPLOADING = "uploading"
    RECORDED = "recorded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED = "failed"
    DELETED = "deleted"


class InterviewRecording(Base):
    __tablename__ = "interview_recordings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    storage_backend: Mapped[InterviewRecordingStorageBackend] = mapped_column(
        enum_column(InterviewRecordingStorageBackend, "interview_recording_storage_backend"),
        nullable=False,
        default=InterviewRecordingStorageBackend.LOCAL,
    )
    object_key: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[InterviewRecordingStatus] = mapped_column(
        enum_column(InterviewRecordingStatus, "interview_recording_status"),
        nullable=False,
        default=InterviewRecordingStatus.RECORDED,
        index=True,
    )
    transcript_text: Mapped[str | None] = mapped_column(Text)
    transcript_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    consent_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
