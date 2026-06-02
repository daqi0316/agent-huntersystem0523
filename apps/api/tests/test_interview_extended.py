"""Tests for app/tools/interview_extended.py — reschedule/complete/get_detail handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.interview_extended import (
    _handle_complete_interview,
    _handle_get_interview_detail,
    _handle_reschedule_interview,
    handlers,
    tools,
)


def _mock_db_session():
    """构建一个 AsyncMock 模拟 AsyncSessionLocal() 上下文管理器."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield db

    return db, fake_session


def _patched_svc(mock_svc: MagicMock):
    """返回 context manager: patch interview_extended.InterviewService → mock_svc."""
    from app.tools import interview_extended

    class _Ctx:
        def __enter__(self):
            self._orig = interview_extended.InterviewService
            interview_extended.InterviewService = MagicMock(return_value=mock_svc)
            return mock_svc

        def __exit__(self, *a):
            interview_extended.InterviewService = self._orig

    return _Ctx()


class TestRescheduleInterview:
    @pytest.mark.asyncio
    async def test_empty_interview_id_validation_error(self) -> None:
        """interview_id 为空 → VALIDATION_ERROR."""
        result = await _handle_reschedule_interview(interview_id="", new_time="2025-06-15T10:00:00")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """interview_id 不存在 → NOT_FOUND."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=None)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_reschedule_interview(
                    interview_id="i1", new_time="2025-06-15T10:00:00"
                )
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_success_with_new_time_and_reason(self) -> None:
        """正常改期（带新时间和原因）."""
        db, fake_session = _mock_db_session()
        interview = MagicMock()
        interview.id = "i1"
        interview.scheduled_at = None
        interview.notes = None
        interview.status = MagicMock()
        interview.status.value = "scheduled"
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=interview)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_reschedule_interview(
                    interview_id="i1",
                    new_time="2025-06-15T10:00:00+00:00",
                    reason="candidate unavailable",
                )
        assert result["status"] == "success"
        assert result["data"]["interview_id"] == "i1"
        assert interview.scheduled_at is not None
        assert "[改期原因] candidate unavailable" in interview.notes
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_time_returns_error(self) -> None:
        """new_time 格式无效 → INVALID_TIME."""
        db, fake_session = _mock_db_session()
        interview = MagicMock()
        interview.notes = None
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=interview)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_reschedule_interview(
                    interview_id="i1", new_time="not-a-date"
                )
        assert result["status"] == "failed"
        assert result["error"]["code"] == "INVALID_TIME"

    @pytest.mark.asyncio
    async def test_z_suffix_time_format(self) -> None:
        """new_time 带 'Z' 后缀被正确解析."""
        db, fake_session = _mock_db_session()
        interview = MagicMock()
        interview.id = "i1"
        interview.scheduled_at = None
        interview.notes = ""
        interview.status = "completed"
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=interview)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_reschedule_interview(
                    interview_id="i1", new_time="2025-06-15T10:00:00Z"
                )
        assert result["status"] == "success"
        assert interview.scheduled_at.tzinfo is not None


class TestCompleteInterview:
    @pytest.mark.asyncio
    async def test_empty_interview_id(self) -> None:
        """interview_id 为空 → VALIDATION_ERROR."""
        result = await _handle_complete_interview(interview_id="", feedback="good")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """complete 返回 None → NOT_FOUND."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.complete = AsyncMock(return_value=None)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_complete_interview(interview_id="missing", feedback="x")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """complete 成功 → 返回 data."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.complete = AsyncMock(return_value={"id": "i1", "status": "completed"})
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_complete_interview(interview_id="i1", feedback="ok")
        assert result["status"] == "success"
        assert result["data"]["id"] == "i1"


class TestGetInterviewDetail:
    @pytest.mark.asyncio
    async def test_empty_interview_id(self) -> None:
        """interview_id 为空 → VALIDATION_ERROR."""
        result = await _handle_get_interview_detail(interview_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """interview 不存在 → NOT_FOUND."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=None)
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_get_interview_detail(interview_id="missing")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """interview 存在 → 返回 _to_dict 结果."""
        db, fake_session = _mock_db_session()
        interview = MagicMock()
        mock_svc = MagicMock()
        mock_svc._get_by_id = AsyncMock(return_value=interview)
        mock_svc._to_dict = MagicMock(return_value={"id": "i1", "status": "scheduled"})
        with patch("app.tools.interview_extended.AsyncSessionLocal", fake_session):
            with _patched_svc(mock_svc):
                result = await _handle_get_interview_detail(interview_id="i1")
        assert result["status"] == "success"
        assert result["data"]["id"] == "i1"


class TestToolRegistry:
    def test_tools_count_and_names(self) -> None:
        """tools 列表包含 3 个工具定义."""
        assert len(tools) == 3
        names = {t["function"]["name"] for t in tools}
        assert names == {"reschedule_interview", "complete_interview", "get_interview_detail"}

    def test_handlers_map(self) -> None:
        """handlers 字典映射 3 个 handler 函数."""
        assert set(handlers.keys()) == {
            "reschedule_interview",
            "complete_interview",
            "get_interview_detail",
        }
        for h in handlers.values():
            assert callable(h)
