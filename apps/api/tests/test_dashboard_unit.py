"""Unit tests for dashboard API — mock-based, no Docker dependency."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.dashboard import (
    _candidate_trend,
    _count,
    _count_this_month,
    _count_with_condition,
    _recent_activities,
    router,
)
from app.api.dashboard_reports import _stage_label, router as reports_router


class TestRouterRegistration:
    def test_dashboard_router_has_stats_endpoint(self):
        paths = [r.path for r in router.routes]
        assert "/stats" in paths

    def test_reports_router_has_reports_endpoint(self):
        paths = [r.path for r in reports_router.routes]
        assert "/reports" in paths


class TestCount:
    @pytest.mark.asyncio
    async def test_count_returns_result(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _count(mock_db, "candidates")
        assert result == 42

    @pytest.mark.asyncio
    async def test_count_returns_zero_on_none(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _count(mock_db, "candidates")
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_returns_zero_on_error(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB error")

        result = await _count(mock_db, "candidates")
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_generates_correct_sql(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        await _count(mock_db, "jobs")
        text_obj = mock_db.execute.await_args[0][0]
        assert "COUNT(*)" in str(text_obj) and "jobs" in str(text_obj)


class TestCountWithCondition:
    @pytest.mark.asyncio
    async def test_count_with_condition(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _count_with_condition(mock_db, "interviews", "status", "scheduled")
        assert result == 3

    @pytest.mark.asyncio
    async def test_condition_uses_parameterized_query(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

        await _count_with_condition(mock_db, "t", "col", "val")
        text_obj = mock_db.execute.await_args[0][0]
        assert ":val" in str(text_obj)

    @pytest.mark.asyncio
    async def test_error_returns_zero(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("err")
        assert await _count_with_condition(mock_db, "t", "c", "v") == 0


class TestCountThisMonth:
    @pytest.mark.asyncio
    async def test_this_month_count(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=7)))

        result = await _count_this_month(mock_db, "candidates", "hired")
        assert result == 7

    @pytest.mark.asyncio
    async def test_error_returns_zero(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("err")
        assert await _count_this_month(mock_db, "candidates", "hired") == 0


class TestRecentActivities:
    @pytest.mark.asyncio
    async def test_returns_activities(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        # First query: candidates (returns rows)
        # Second query: jobs (returns rows)
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(__iter__=lambda self: iter([
                ("candidate", "Alice", datetime.now(timezone.utc)),
                ("candidate", "Bob", datetime.now(timezone.utc)),
            ])),
            MagicMock(__iter__=lambda self: iter([
                ("job", "Engineer", datetime.now(timezone.utc)),
            ])),
        ]

        activities = await _recent_activities(mock_db, limit=6)

        assert len(activities) >= 2
        texts = [a["text"] for a in activities]
        assert any("Alice" in t for t in texts)
        assert any("Engineer" in t for t in texts)

    @pytest.mark.asyncio
    async def test_both_queries_fail_returns_empty(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB down")

        activities = await _recent_activities(mock_db)
        assert activities == []

    @pytest.mark.asyncio
    async def test_limited_to_specified_count(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(__iter__=lambda self: iter([
                ("candidate", f"User{i}", datetime.now(timezone.utc)) for i in range(20)
            ])),
            MagicMock(__iter__=lambda self: iter([])),
        ]

        activities = await _recent_activities(mock_db, limit=5)
        assert len(activities) <= 5


class TestCandidateTrend:
    @pytest.mark.asyncio
    async def test_returns_trend_points(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=3)))

        points = await _candidate_trend(mock_db, days=10)
        assert len(points) > 0
        assert all("date" in p and "count" in p for p in points)

    @pytest.mark.asyncio
    async def test_error_falls_back_to_today(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Trend failed")

        points = await _candidate_trend(mock_db)
        assert len(points) == 1
        assert points[0]["count"] == 0


class TestStageLabel:
    def test_returns_chinese_label(self):
        from app.models.application import ApplicationStatus

        assert _stage_label(ApplicationStatus.PENDING) == "待处理"
        assert _stage_label(ApplicationStatus.SCREENING) == "初筛中"
        assert _stage_label(ApplicationStatus.INTERVIEW) == "面试中"
        assert _stage_label(ApplicationStatus.OFFER) == "已发 Offer"
        assert _stage_label(ApplicationStatus.REJECTED) == "已淘汰"
        assert _stage_label(ApplicationStatus.WITHDRAWN) == "已撤回"

    def test_fallback_to_value(self):
        from app.models.application import ApplicationStatus

        assert _stage_label(ApplicationStatus.PENDING) is not None
