from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools import interview_recording
from app.tools.interview_recording import (
    _handle_get_recording_status,
    _handle_transcribe_recording,
    handlers,
    tools,
)


def test_interview_recording_tools_defined():
    names = [t["function"]["name"] for t in tools]
    assert "get_recording_status" in names
    assert "transcribe_recording" in names


def test_interview_recording_handlers_registered():
    assert "get_recording_status" in handlers
    assert "transcribe_recording" in handlers


@pytest.mark.asyncio
async def test_get_recording_status_validation_error():
    result = await _handle_get_recording_status(interview_id="", recording_id="rec")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_transcribe_recording_success():
    db = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield db

    mock_recording = MagicMock()
    mock_svc = MagicMock()
    mock_svc.transcribe_recording = AsyncMock(return_value=mock_recording)
    mock_svc.to_dict.return_value = {"id": "rec", "status": "transcribed"}

    with (
        patch.object(interview_recording, "AsyncSessionLocal", fake_session),
        patch.object(interview_recording, "InterviewRecordingService", MagicMock(return_value=mock_svc)),
    ):
        result = await _handle_transcribe_recording(interview_id="iv", recording_id="rec")

    assert result["status"] == "success"
    assert result["data"]["status"] == "transcribed"


def test_mcp_interview_server_includes_recording_tools():
    from app.mcp_servers.builtin.interview_server import ALL_HANDLERS, ALL_TOOLS

    names = [t["function"]["name"] for t in ALL_TOOLS]
    assert "get_recording_status" in names
    assert "transcribe_recording" in names
    assert "create_recording_evaluation" in names
    assert "get_recording_status" in ALL_HANDLERS
    assert "transcribe_recording" in ALL_HANDLERS
    assert "create_recording_evaluation" in ALL_HANDLERS


def test_recording_tools_register_explicit_pydantic_input_models():
    from app.tools.metadata import get_input_model

    assert get_input_model("get_recording_status") is not None
    assert get_input_model("transcribe_recording") is not None
    assert get_input_model("create_recording_evaluation") is not None


@pytest.mark.asyncio
async def test_create_recording_evaluation_requires_transcript():
    db = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield db

    mock_recording = MagicMock()
    mock_recording.id = "rec-1"
    mock_recording.transcript_text = ""
    mock_svc = MagicMock()
    mock_svc.get_recording = AsyncMock(return_value=mock_recording)

    with (
        patch.object(interview_recording, "AsyncSessionLocal", fake_session),
        patch.object(interview_recording, "InterviewRecordingService", MagicMock(return_value=mock_svc)),
    ):
        result = await interview_recording._handle_create_recording_evaluation(
            interview_id="iv",
            recording_id="rec-1",
        )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "NO_TRANSCRIPT"


def test_mcp_interview_entrypoint_wrapper_exposes_all_tools():
    from app.mcp_servers.builtin import interview_server

    entries = interview_server.ALL_TOOLS
    entries_handlers = interview_server.ALL_HANDLERS
    expected = {
        "schedule_interview",
        "record_feedback",
        "cancel_interview",
        "reschedule_interview",
        "complete_interview",
        "get_interview_detail",
        "get_recording_status",
        "transcribe_recording",
        "create_recording_evaluation",
        "get_evaluations",
    }
    assert set(t["function"]["name"] for t in entries) == expected
    assert set(entries_handlers) == expected
    for tool in entries:
        fn = tool["function"]
        assert tool["type"] == "function"
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]


def test_mcp_interview_recording_input_models_validate():
    from app.tools.interview_recording import (
        CreateRecordingEvaluationInput,
        RecordingToolInput,
    )

    base = RecordingToolInput(interview_id="iv-1", recording_id="rec-1")
    assert base.interview_id == "iv-1"

    with pytest.raises(Exception):
        RecordingToolInput(interview_id="", recording_id="rec-1")
    with pytest.raises(Exception):
        RecordingToolInput(interview_id="iv-1", recording_id="")

    full = CreateRecordingEvaluationInput(
        interview_id="iv-1",
        recording_id="rec-1",
        candidate_name="张三",
        job_title="后端",
        round="R2",
    )
    assert full.round == "R2"
