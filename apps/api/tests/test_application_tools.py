"""Tests for app/tools/application.py — create/update handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.application import (
    _handle_create_application,
    _handle_update_application_status,
    handlers,
    tools,
)


def _mock_db_session():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield db

    return db, fake_session


def _patched_app_svc(mock_svc: MagicMock):
    """Patch app.tools.application.ApplicationService."""
    from app.tools import application as app_mod

    class _Ctx:
        def __enter__(self):
            self._orig = app_mod.ApplicationService
            app_mod.ApplicationService = MagicMock(return_value=mock_svc)
            return mock_svc

        def __exit__(self, *a):
            app_mod.ApplicationService = self._orig

    return _Ctx()


class TestCreateApplication:
    @pytest.mark.asyncio
    async def test_missing_candidate_id(self) -> None:
        """candidate_id 缺失 → VALIDATION_ERROR."""
        result = await _handle_create_application(candidate_id="", job_id="j1")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_missing_job_id(self) -> None:
        """job_id 缺失 → VALIDATION_ERROR."""
        result = await _handle_create_application(candidate_id="c1", job_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """创建成功 → 返回 application 数据."""
        db, fake_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.id = "a1"
        mock_app.candidate_id = "c1"
        mock_app.job_id = "j1"
        mock_app.status.value = "pending"
        mock_app.created_at = "2025-06-15T10:00:00"
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=mock_app)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_create_application(
                    candidate_id="c1", job_id="j1", resume_url="https://r.pdf"
                )
        assert result["status"] == "success"
        assert result["data"]["application_id"] == "a1"
        assert result["data"]["candidate_id"] == "c1"
        assert result["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_success_no_resume_url(self) -> None:
        """不带 resume_url → 正常创建（resume_url 传 None）."""
        db, fake_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.id = "a2"
        mock_app.candidate_id = "c1"
        mock_app.job_id = "j1"
        mock_app.status.value = "submitted"
        mock_app.created_at = "2025-06-15"
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=mock_app)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_create_application(candidate_id="c1", job_id="j1")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_exception_returns_failed(self) -> None:
        """create 抛异常 → CREATE_FAILED."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(side_effect=ValueError("duplicate"))
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_create_application(candidate_id="c1", job_id="j1")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "CREATE_FAILED"
        assert "duplicate" in result["error"]["message"]


class TestUpdateApplicationStatus:
    @pytest.mark.asyncio
    async def test_empty_application_id(self) -> None:
        """application_id 缺失 → VALIDATION_ERROR."""
        result = await _handle_update_application_status(application_id="", status="passed")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """申请不存在 → NOT_FOUND."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_update_application_status(
                    application_id="missing", status="passed"
                )
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_success_with_all_fields(self) -> None:
        """更新 status + match_score + ai_summary."""
        db, fake_session = _mock_db_session()
        existing = MagicMock()
        existing.id = "a1"
        mock_updated = MagicMock()
        mock_updated.id = "a1"
        mock_updated.status.value = "passed"
        mock_updated.match_score = 85.0
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=existing)
        mock_svc.update = AsyncMock(return_value=mock_updated)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_update_application_status(
                    application_id="a1",
                    status="passed",
                    match_score=85.0,
                    ai_summary="strong candidate",
                )
        assert result["status"] == "success"
        assert result["data"]["application_id"] == "a1"
        assert result["data"]["status"] == "passed"
        assert result["data"]["match_score"] == 85.0

    @pytest.mark.asyncio
    async def test_update_returns_none(self) -> None:
        """update 返回 None → UPDATE_FAILED."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=None)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_update_application_status(
                    application_id="a1", status="rejected"
                )
        assert result["status"] == "failed"
        assert result["error"]["code"] == "UPDATE_FAILED"

    @pytest.mark.asyncio
    async def test_status_only(self) -> None:
        """只传 status，不传 match_score/ai_summary → 只更新 status."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_updated = MagicMock()
        mock_updated.id = "a1"
        mock_updated.status.value = "interview"
        mock_updated.match_score = None
        mock_svc.update = AsyncMock(return_value=mock_updated)
        with patch("app.tools.application.AsyncSessionLocal", fake_session):
            with _patched_app_svc(mock_svc):
                result = await _handle_update_application_status(
                    application_id="a1", status="interview"
                )
        assert result["status"] == "success"


class TestToolRegistry:
    def test_tools_count_and_names(self) -> None:
        assert len(tools) == 2
        names = {t["function"]["name"] for t in tools}
        assert names == {"create_application", "update_application_status"}

    def test_handlers_map(self) -> None:
        assert set(handlers.keys()) == {"create_application", "update_application_status"}
        for h in handlers.values():
            assert callable(h)
