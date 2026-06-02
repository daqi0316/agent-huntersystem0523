"""Tests for app/tools/candidate_search.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.candidate_search import (
    _handle_get_candidate_detail,
    _handle_search_candidates,
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


def _patched_in_mod(mod_path, attr, mock_value):
    import importlib

    mod = importlib.import_module(mod_path)

    class _Ctx:
        def __enter__(self):
            self._orig = getattr(mod, attr)
            setattr(mod, attr, mock_value)
            return mock_value

        def __exit__(self, *a):
            setattr(mod, attr, self._orig)

    return _Ctx()


class TestSearchCandidates:
    @pytest.mark.asyncio
    async def test_empty_query_returns_all(self) -> None:
        """空 query → 调用 svc.list 不过滤 search."""
        db, fake_session = _mock_db_session()
        c1 = MagicMock()
        c1.id = "c1"
        c1.name = "张三"
        c1.email = "z@x.com"
        c1.status.value = "active"
        c1.current_title = "工程师"
        c1.current_company = "Acme"
        c1.skills = ["python"]
        c1.experience_years = 5
        mock_svc = MagicMock()
        mock_svc.list = AsyncMock(return_value=([c1], 1))
        with patch("app.tools.candidate_search.AsyncSessionLocal", fake_session):
            with _patched_in_mod("app.tools.candidate_search", "CandidateService", MagicMock(return_value=mock_svc)):
                result = await _handle_search_candidates()
        assert result["total"] == 1
        assert result["skip"] == 0
        assert result["limit"] == 20
        assert result["items"][0]["candidate_id"] == "c1"
        mock_svc.list.assert_awaited_once_with(skip=0, limit=20, search=None, status=None)

    @pytest.mark.asyncio
    async def test_with_query_and_status(self) -> None:
        """带 query 和 status → 传递到 svc.list."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.list = AsyncMock(return_value=([], 0))
        with patch("app.tools.candidate_search.AsyncSessionLocal", fake_session):
            with _patched_in_mod("app.tools.candidate_search", "CandidateService", MagicMock(return_value=mock_svc)):
                result = await _handle_search_candidates(
                    query="python", status="active", skip=10, limit=5
                )
        assert result["total"] == 0
        assert result["skip"] == 10
        assert result["limit"] == 5
        mock_svc.list.assert_awaited_once_with(skip=10, limit=5, search="python", status="active")

    @pytest.mark.asyncio
    async def test_pii_masking_applied(self) -> None:
        """name/email 经过 mask_pii."""
        db, fake_session = _mock_db_session()
        c1 = MagicMock()
        c1.id = "c1"
        c1.name = "李四"
        c1.email = "l@x.com"
        c1.status = "active"
        c1.current_title = None
        c1.current_company = None
        c1.skills = None
        c1.experience_years = 0
        mock_svc = MagicMock()
        mock_svc.list = AsyncMock(return_value=([c1], 1))
        with patch("app.tools.candidate_search.AsyncSessionLocal", fake_session):
            with _patched_in_mod("app.tools.candidate_search", "CandidateService", MagicMock(return_value=mock_svc)):
                result = await _handle_search_candidates()
        item = result["items"][0]
        assert item["current_title"] == ""
        assert item["current_company"] == ""
        assert item["skills"] == []


class TestGetCandidateDetail:
    @pytest.mark.asyncio
    async def test_empty_id(self) -> None:
        """candidate_id 缺失 → VALIDATION_ERROR."""
        result = await _handle_get_candidate_detail(candidate_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """候选人不存在 → NOT_FOUND."""
        db, fake_session = _mock_db_session()
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)
        with patch("app.tools.candidate_search.AsyncSessionLocal", fake_session):
            with _patched_in_mod("app.tools.candidate_search", "CandidateService", MagicMock(return_value=mock_svc)):
                result = await _handle_get_candidate_detail(candidate_id="missing")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """候选人存在 → 返回完整详情（含 interviews/applications）."""
        db, fake_session = _mock_db_session()
        candidate = MagicMock()
        candidate.id = "c1"
        candidate.name = "Wang"
        candidate.email = "w@x.com"
        candidate.phone = "13800000000"
        candidate.status.value = "active"
        candidate.summary = "experienced"
        candidate.skills = ["python"]
        candidate.experience_years = 5
        candidate.education = "BS CS"
        candidate.current_company = "Acme"
        candidate.current_title = "Engineer"
        candidate.created_at = "2025-06-01T00:00:00"
        mock_cand_svc = MagicMock()
        mock_cand_svc.get_by_id = AsyncMock(return_value=candidate)
        mock_int_svc = MagicMock()
        mock_int_svc.list_by_candidate = AsyncMock(return_value=[{"id": "i1", "status": "scheduled"}])
        mock_app_svc = MagicMock()
        mock_app_svc.list = AsyncMock(return_value=([{"id": "a1", "job_id": "j1", "status": "passed", "match_score": 90}], 1))
        with patch("app.tools.candidate_search.AsyncSessionLocal", fake_session):
            with _patched_in_mod("app.tools.candidate_search", "CandidateService", MagicMock(return_value=mock_cand_svc)):
                with _patched_in_mod("app.services.interview", "InterviewService", MagicMock(return_value=mock_int_svc)):
                    with _patched_in_mod("app.services.application", "ApplicationService", MagicMock(return_value=mock_app_svc)):
                        result = await _handle_get_candidate_detail(candidate_id="c1")
        assert result["status"] == "success"
        data = result["data"]
        assert data["candidate_id"] == "c1"
        assert len(data["interviews"]) == 1
        assert len(data["applications"]) == 1
        assert data["applications"][0]["match_score"] == 90


class TestToolRegistry:
    def test_tools_count(self) -> None:
        assert len(tools) == 2
        names = {t["function"]["name"] for t in tools}
        assert names == {"search_candidates", "get_candidate_detail"}

    def test_handlers_map(self) -> None:
        assert set(handlers.keys()) == {"search_candidates", "get_candidate_detail"}
        for h in handlers.values():
            assert callable(h)
