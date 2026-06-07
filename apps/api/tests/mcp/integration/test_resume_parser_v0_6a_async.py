"""v0.6a async parse task 测试 — submit (enqueue) + poll。

覆盖:
  1. submit 返 raw_resume_id + task_id, 不阻塞等 LLM
  2. submit 空 content 返 INVALID_INPUT
  3. submit enqueue 失败 (Redis down) 返 QUEUE_UNAVAILABLE + raw_resume 标 failed
  4. poll processing 状态
  5. poll parsed 状态
  6. poll failed 状态
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_submit_returns_raw_resume_id_and_task_id():
    """主路径：submit 落 raw_resume + enqueue RQ task, 立刻返 task_id。"""
    from app.tools.resume_parser import _handle_parse_resume_async

    with patch("app.services.parse_task.enqueue_parse_task", return_value="rq-job-abc123") as mock_enqueue:
        with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.get = AsyncMock(return_value=None)
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _handle_parse_resume_async(content="raw resume text")

    assert result["status"] == "accepted"
    assert "raw_resume_id" in result["data"]
    assert result["data"]["task_id"] == "rq-job-abc123"
    assert result["data"]["poll_url"] == f"/raw-resumes/{result['data']['raw_resume_id']}/status"
    mock_enqueue.assert_called_once()
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["content"] == "raw resume text"
    assert call_kwargs["auto_create"] is True


@pytest.mark.asyncio
async def test_submit_empty_content_returns_invalid_input():
    """submit content 和 file_url 都空返 INVALID_INPUT, 不落 raw_resume。"""
    from app.tools.resume_parser import _handle_parse_resume_async

    with patch("app.services.parse_task.enqueue_parse_task") as mock_enqueue:
        result = await _handle_parse_resume_async(content="", file_url="")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_INPUT"
    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_submit_enqueue_fails_returns_queue_unavailable():
    """Redis down 时 enqueue 抛 ConnectionError, raw_resume 标 failed + 返 QUEUE_UNAVAILABLE。"""
    from app.tools.resume_parser import _handle_parse_resume_async
    from app.models.raw_resume import RawResumeStatus

    stuck_rr = MagicMock()
    stuck_rr.status = None
    stuck_rr.error_message = None

    call_count = {"n": 0}

    def session_factory():
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        call_count["n"] += 1

        def get(model, id_):
            return stuck_rr if call_count["n"] == 2 else None

        db.get = AsyncMock(side_effect=get)
        return db

    with patch("app.services.parse_task.enqueue_parse_task", side_effect=ConnectionError("redis down")) as mock_enqueue:
        with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(side_effect=session_factory)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _handle_parse_resume_async(content="raw text")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "QUEUE_UNAVAILABLE"
    assert result["error"]["retryable"] is True
    assert "redis down" in result["error"]["message"]
    assert stuck_rr.status == RawResumeStatus.FAILED
    assert "enqueue_failed" in stuck_rr.error_message
    mock_enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_poll_status_processing():
    """poll processing 状态返 accepted + parse_status=processing。"""
    from app.tools.resume_parser import _handle_poll_parse

    poll_result = {
        "raw_resume_id": "rr-1",
        "status": "processing",
        "candidate_id": None,
        "error_message": None,
        "updated_at": "2026-06-07T09:00:00+00:00",
    }

    async def fake_poll(raw_resume_id: str):
        return poll_result

    with patch("app.services.parse_task.poll_parse_task", side_effect=fake_poll):
        result = await _handle_poll_parse(raw_resume_id="rr-1")

    assert result["status"] == "accepted"
    assert result["data"]["raw_resume_id"] == "rr-1"
    assert result["data"]["parse_status"] == "processing"


@pytest.mark.asyncio
async def test_poll_status_parsed():
    """poll parsed 状态返 success + candidate_id。"""
    from app.tools.resume_parser import _handle_poll_parse

    poll_result = {
        "raw_resume_id": "rr-2",
        "status": "parsed",
        "candidate_id": "cand-from-async",
        "error_message": None,
        "updated_at": "2026-06-07T09:00:05+00:00",
    }

    async def fake_poll(raw_resume_id: str):
        return poll_result

    with patch("app.services.parse_task.poll_parse_task", side_effect=fake_poll):
        result = await _handle_poll_parse(raw_resume_id="rr-2")

    assert result["status"] == "success"
    assert result["data"]["parse_status"] == "parsed"
    assert result["data"]["candidate_id"] == "cand-from-async"


@pytest.mark.asyncio
async def test_poll_status_failed():
    """poll failed 状态返 failed + parse_status=failed, error.retryable=True。"""
    from app.tools.resume_parser import _handle_poll_parse

    poll_result = {
        "raw_resume_id": "rr-3",
        "status": "failed",
        "candidate_id": None,
        "error_message": "low_confidence_or_extraction_error",
        "updated_at": "2026-06-07T09:00:03+00:00",
    }

    async def fake_poll(raw_resume_id: str):
        return poll_result

    with patch("app.services.parse_task.poll_parse_task", side_effect=fake_poll):
        result = await _handle_poll_parse(raw_resume_id="rr-3")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "PARSE_FAILED"
    assert result["error"]["retryable"] is True
    assert "low_confidence" in result["error"]["message"]
    assert result["data"]["parse_status"] == "failed"


@pytest.mark.asyncio
async def test_poll_not_found_returns_not_found():
    """poll 不存在的 raw_resume_id 返 NOT_FOUND。"""
    from app.tools.resume_parser import _handle_poll_parse

    async def fake_poll(raw_resume_id: str):
        return None

    with patch("app.services.parse_task.poll_parse_task", side_effect=fake_poll):
        result = await _handle_poll_parse(raw_resume_id="rr-not-exists")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "NOT_FOUND"
