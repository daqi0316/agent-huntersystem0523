from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.models.interview_recording import InterviewRecordingStatus
from app.services.interview_recording import (
    InterviewRecordingError,
    InterviewRecordingService,
    InterviewRecordingStorageBackend,
    LocalRecordingStorage,
    MockASRProvider,
    StoredRecordingFile,
)


@pytest.mark.asyncio
async def test_upload_recording_requires_consent(tmp_path):
    service = InterviewRecordingService(MagicMock(), storage_root=tmp_path)

    with pytest.raises(InterviewRecordingError) as exc:
        await service.upload_recording(
            interview_id="12345678-1234-5678-1234-567812345678",
            file_bytes=b"audio",
            filename="recording.webm",
            mime_type="audio/webm",
            user_id="user-1",
            consent_confirmed=False,
        )

    assert exc.value.code == "CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_upload_recording_rejects_invalid_mime(tmp_path):
    service = InterviewRecordingService(MagicMock(), storage_root=tmp_path)

    with pytest.raises(InterviewRecordingError) as exc:
        await service.upload_recording(
            interview_id="12345678-1234-5678-1234-567812345678",
            file_bytes=b"audio",
            filename="recording.txt",
            mime_type="text/plain",
            user_id="user-1",
            consent_confirmed=True,
        )

    assert exc.value.code == "UNSUPPORTED_MIME"


@pytest.mark.asyncio
async def test_upload_recording_success_writes_file_and_record(tmp_path):
    interview = MagicMock()
    interview.id = "12345678-1234-5678-1234-567812345678"
    result = MagicMock()
    result.scalar_one_or_none.return_value = interview
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    service = InterviewRecordingService(db, storage=LocalRecordingStorage(tmp_path))

    recording = await service.upload_recording(
        interview_id=interview.id,
        file_bytes=b"audio-bytes",
        filename="recording.webm",
        mime_type="audio/webm",
        user_id="user-1",
        consent_confirmed=True,
        duration_seconds=3.5,
    )

    assert recording.status == InterviewRecordingStatus.RECORDED
    assert recording.file_size_bytes == len(b"audio-bytes")
    assert recording.duration_seconds == 3.5
    assert recording.file_path
    assert tmp_path in __import__("pathlib").Path(recording.file_path).parents
    assert __import__("pathlib").Path(recording.file_path).read_bytes() == b"audio-bytes"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_recording_uses_injected_storage():
    interview = MagicMock()
    interview.id = "12345678-1234-5678-1234-567812345678"
    result = MagicMock()
    result.scalar_one_or_none.return_value = interview
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    storage = MagicMock()
    storage.save = AsyncMock(return_value=StoredRecordingFile(
        storage_backend=InterviewRecordingStorageBackend.MINIO,
        file_path=None,
        object_key="interview-recordings/test.webm",
    ))
    service = InterviewRecordingService(db, storage=storage)

    recording = await service.upload_recording(
        interview_id=interview.id,
        file_bytes=b"audio-bytes",
        filename="recording.webm",
        mime_type="audio/webm",
        user_id="user-1",
        consent_confirmed=True,
    )

    assert recording.storage_backend == InterviewRecordingStorageBackend.MINIO
    assert recording.object_key == "interview-recordings/test.webm"
    storage.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_recording_storage_writes_async(tmp_path):
    storage = LocalRecordingStorage(tmp_path)
    stored = await storage.save(b"audio", "recording.webm", "audio/webm", datetime.now(timezone.utc))

    assert stored.storage_backend == InterviewRecordingStorageBackend.LOCAL
    assert stored.file_path
    assert __import__("pathlib").Path(stored.file_path).read_bytes() == b"audio"


@pytest.mark.asyncio
async def test_transcribe_recording_is_idempotent():
    recording = MagicMock()
    recording.id = "rec-id"
    recording.file_path = "/tmp/recording.webm"
    recording.object_key = None
    recording.status = InterviewRecordingStatus.TRANSCRIBED
    recording.transcript_text = "已有 transcript"
    recording.transcript_json = None
    result = MagicMock()
    result.scalar_one_or_none.return_value = recording
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    service = InterviewRecordingService(db)

    provider = MagicMock()
    provider.transcribe = AsyncMock(side_effect=AssertionError("provider should not be called"))

    updated = await service.transcribe_recording(
        "12345678-1234-5678-1234-567812345678",
        "rec-id",
        provider=provider,
    )

    assert updated.status == InterviewRecordingStatus.TRANSCRIBED
    assert updated.transcript_text == "已有 transcript"
    provider.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_recording_success():
    recording = MagicMock()
    recording.id = "rec-id"
    recording.file_path = "/tmp/recording.webm"
    recording.object_key = None
    recording.status = InterviewRecordingStatus.RECORDED
    recording.transcript_text = None
    recording.transcript_json = None
    result = MagicMock()
    result.scalar_one_or_none.return_value = recording
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    service = InterviewRecordingService(db)

    updated = await service.transcribe_recording(
        "12345678-1234-5678-1234-567812345678",
        "rec-id",
        provider=MockASRProvider(),
    )

    assert updated.status == InterviewRecordingStatus.TRANSCRIBED
    assert "mock ASR" in updated.transcript_text
    assert updated.transcript_json["model_used"] == "mock-asr"
    assert db.commit.await_count == 2
