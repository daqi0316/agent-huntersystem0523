from __future__ import annotations

import os
import uuid
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview
from app.models.interview_recording import (
    InterviewRecording,
    InterviewRecordingStatus,
    InterviewRecordingStorageBackend,
)


ALLOWED_AUDIO_MIME_TYPES = {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4"}
MAX_AUDIO_BYTES = 50 * 1024 * 1024


class InterviewRecordingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TranscriptionResult:
    full_text: str
    segments: list[dict[str, Any]]
    model_used: str

    def to_json(self) -> dict[str, Any]:
        return {
            "full_text": self.full_text,
            "segments": self.segments,
            "model_used": self.model_used,
        }


class MockASRProvider:
    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        filename = Path(audio_path).name
        text = f"这是 mock ASR 转录结果，来源文件：{filename}。候选人回答清晰，面试官可基于该文本补充结构化评价。"
        return TranscriptionResult(
            full_text=text,
            segments=[
                {
                    "start_time": 0,
                    "end_time": 5,
                    "text": text,
                    "speaker": None,
                    "confidence": 1.0,
                }
            ],
            model_used="mock-asr",
        )


@dataclass(frozen=True)
class StoredRecordingFile:
    storage_backend: InterviewRecordingStorageBackend
    file_path: str | None
    object_key: str | None


class RecordingStorage(Protocol):
    async def save(self, file_bytes: bytes, object_name: str, mime_type: str, dt: datetime) -> StoredRecordingFile:
        ...


class LocalRecordingStorage:
    def __init__(self, storage_root: str | Path | None = None):
        self.storage_root = Path(
            storage_root or os.getenv("INTERVIEW_RECORDING_STORAGE_DIR", "./recordings/interviews")
        )

    async def save(self, file_bytes: bytes, object_name: str, mime_type: str, dt: datetime) -> StoredRecordingFile:
        file_path = self._storage_path(dt, object_name)
        await asyncio.to_thread(self._write_file, file_path, file_bytes)
        return StoredRecordingFile(
            storage_backend=InterviewRecordingStorageBackend.LOCAL,
            file_path=str(file_path),
            object_key=None,
        )

    @staticmethod
    def _write_file(file_path: Path, file_bytes: bytes) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_bytes)

    def _storage_path(self, dt: datetime, filename: str) -> Path:
        return self.storage_root / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}" / filename


class MinioRecordingStorage:
    def __init__(self, fallback: RecordingStorage | None = None):
        self.fallback = fallback or LocalRecordingStorage()

    async def save(self, file_bytes: bytes, object_name: str, mime_type: str, dt: datetime) -> StoredRecordingFile:
        try:
            return await asyncio.to_thread(self._save_minio, file_bytes, object_name, mime_type, dt)
        except Exception:
            return await self.fallback.save(file_bytes, object_name, mime_type, dt)

    @staticmethod
    def _save_minio(file_bytes: bytes, object_name: str, mime_type: str, dt: datetime) -> StoredRecordingFile:
        from app.core.config import settings as cfg
        from minio import Minio

        client = Minio(
            cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            secure=False,
        )
        bucket = cfg.minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        object_key = f"interview-recordings/{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{object_name}"
        client.put_object(
            bucket,
            object_key,
            BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=mime_type,
        )
        return StoredRecordingFile(
            storage_backend=InterviewRecordingStorageBackend.MINIO,
            file_path=None,
            object_key=object_key,
        )


class InterviewRecordingService:
    def __init__(
        self,
        db: AsyncSession,
        storage_root: str | Path | None = None,
        storage: RecordingStorage | None = None,
    ):
        self.db = db
        self.storage = storage or MinioRecordingStorage(LocalRecordingStorage(storage_root))

    async def upload_recording(
        self,
        interview_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        user_id: str,
        consent_confirmed: bool,
        duration_seconds: float | None = None,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> InterviewRecording:
        if not consent_confirmed:
            raise InterviewRecordingError("CONSENT_REQUIRED", "录音前必须确认候选人/面试参与方已同意")
        if not filename:
            raise InterviewRecordingError("INVALID_FILE", "文件名不能为空")
        if not file_bytes:
            raise InterviewRecordingError("EMPTY_FILE", "录音文件为空")
        if len(file_bytes) > MAX_AUDIO_BYTES:
            raise InterviewRecordingError("FILE_TOO_LARGE", f"录音文件过大，最大支持 {MAX_AUDIO_BYTES // 1024 // 1024}MB")
        if mime_type not in ALLOWED_AUDIO_MIME_TYPES:
            raise InterviewRecordingError("UNSUPPORTED_MIME", f"不支持的音频类型: {mime_type}")

        interview = await self._get_interview(interview_id)
        if interview is None:
            raise InterviewRecordingError("NOT_FOUND", "面试不存在")

        now = datetime.now(timezone.utc)
        recording_id = f"REC-{interview_id}-{now.strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:8]}"
        object_name = self._safe_filename(recording_id, filename)
        stored = await self.storage.save(file_bytes, object_name, mime_type, now)

        recording = InterviewRecording(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            recording_id=recording_id,
            storage_backend=stored.storage_backend,
            file_path=stored.file_path,
            object_key=stored.object_key,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            file_size_bytes=len(file_bytes),
            sample_rate=sample_rate,
            channels=channels,
            status=InterviewRecordingStatus.RECORDED,
            consent_confirmed_at=now,
            consent_by_user_id=user_id,
            created_by=user_id,
        )
        self.db.add(recording)
        await self.db.commit()
        await self.db.refresh(recording)
        return recording

    async def get_recording(self, interview_id: str, recording_id: str) -> InterviewRecording | None:
        result = await self.db.execute(
            select(InterviewRecording).where(
                InterviewRecording.interview_id == interview_id,
                InterviewRecording.id == recording_id,
                InterviewRecording.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_recordings(self, interview_id: str) -> list[InterviewRecording]:
        result = await self.db.execute(
            select(InterviewRecording)
            .where(
                InterviewRecording.interview_id == interview_id,
                InterviewRecording.deleted_at.is_(None),
            )
            .order_by(InterviewRecording.created_at.desc())
        )
        return list(result.scalars().all())

    async def transcribe_recording(
        self,
        interview_id: str,
        recording_id: str,
        provider: MockASRProvider | None = None,
    ) -> InterviewRecording:
        recording = await self.get_recording(interview_id, recording_id)
        if recording is None:
            raise InterviewRecordingError("NOT_FOUND", "录音不存在")
        if recording.status == InterviewRecordingStatus.TRANSCRIBED and recording.transcript_text:
            return recording
        if not recording.file_path and not recording.object_key:
            raise InterviewRecordingError("MISSING_AUDIO", "录音文件路径不存在")

        recording.status = InterviewRecordingStatus.TRANSCRIBING
        recording.error_message = None
        await self.db.commit()
        await self.db.refresh(recording)

        try:
            asr = provider or MockASRProvider()
            result = await asr.transcribe(recording.file_path or recording.object_key or "")
            recording.transcript_text = result.full_text
            recording.transcript_json = result.to_json()
            recording.status = InterviewRecordingStatus.TRANSCRIBED
        except Exception as e:
            recording.status = InterviewRecordingStatus.FAILED
            recording.error_message = str(e)
            await self.db.commit()
            raise InterviewRecordingError("TRANSCRIBE_FAILED", str(e))

        await self.db.commit()
        await self.db.refresh(recording)
        return recording

    async def _get_interview(self, interview_id: str) -> Interview | None:
        try:
            uuid.UUID(interview_id)
        except (ValueError, AttributeError):
            return None
        result = await self.db.execute(select(Interview).where(Interview.id == interview_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _safe_filename(recording_id: str, filename: str) -> str:
        ext = Path(filename).suffix.lower() or ".webm"
        if ext not in {".webm", ".wav", ".mp3", ".mp4", ".mpeg"}:
            ext = ".webm"
        return f"{recording_id}{ext}"

    @staticmethod
    def to_dict(recording: InterviewRecording) -> dict[str, Any]:
        return {
            "id": recording.id,
            "interview_id": recording.interview_id,
            "recording_id": recording.recording_id,
            "storage_backend": recording.storage_backend.value if recording.storage_backend else "",
            "object_key": recording.object_key or "",
            "file_path": recording.file_path or "",
            "mime_type": recording.mime_type,
            "duration_seconds": recording.duration_seconds,
            "file_size_bytes": recording.file_size_bytes,
            "sample_rate": recording.sample_rate,
            "channels": recording.channels,
            "status": recording.status.value if recording.status else "",
            "transcript_text": recording.transcript_text or "",
            "transcript_json": recording.transcript_json or {},
            "consent_confirmed_at": recording.consent_confirmed_at.isoformat() if recording.consent_confirmed_at else "",
            "consent_by_user_id": recording.consent_by_user_id,
            "created_by": recording.created_by,
            "error_message": recording.error_message or "",
            "created_at": recording.created_at.isoformat() if recording.created_at else "",
            "updated_at": recording.updated_at.isoformat() if recording.updated_at else "",
        }
