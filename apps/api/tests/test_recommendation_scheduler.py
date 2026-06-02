"""Tests for app/services/recommendation_scheduler.py."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.recommendation_scheduler import (
    RECOMMENDATION_SCAN_INTERVAL_MINUTES,
    recommendation_scheduler_loop,
    run_recommendation_scan,
)


def _mock_db_session(db):
    @asynccontextmanager
    async def fake_session():
        yield db

    return fake_session


def _patched_rec_svc(mock_svc):
    from app.services import recommendation_scheduler as mod

    class _Ctx:
        def __enter__(self):
            self._orig = mod.RecommendationService
            mod.RecommendationService = MagicMock(return_value=mock_svc)
            return mock_svc

        def __exit__(self, *a):
            mod.RecommendationService = self._orig

    return _Ctx()


class TestRunRecommendationScan:
    @pytest.mark.asyncio
    async def test_no_users_skips(self) -> None:
        """无用户时跳过扫描."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)
        with patch(
            "app.services.recommendation_scheduler.AsyncSessionLocal",
            _mock_db_session(db),
        ):
            await run_recommendation_scan()
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scan_users_success(self) -> None:
        """正常扫描所有用户，生成推荐."""
        db = AsyncMock()
        user1 = MagicMock()
        user1.id = "u1"
        user2 = MagicMock()
        user2.id = "u2"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[user1, user2])
        db.execute = AsyncMock(return_value=mock_result)
        mock_svc = MagicMock()
        mock_svc.generate_recommendations = AsyncMock(side_effect=[[{"id": "r1"}], []])
        with patch(
            "app.services.recommendation_scheduler.AsyncSessionLocal",
            _mock_db_session(db),
        ):
            with _patched_rec_svc(mock_svc):
                await run_recommendation_scan()
        assert mock_svc.generate_recommendations.await_count == 2
        mock_svc.generate_recommendations.assert_any_await(user_id="u1")
        mock_svc.generate_recommendations.assert_any_await(user_id="u2")

    @pytest.mark.asyncio
    async def test_per_user_exception_continues(self) -> None:
        """单个用户失败不影响其他用户."""
        db = AsyncMock()
        user1 = MagicMock()
        user1.id = "u1"
        user2 = MagicMock()
        user2.id = "u2"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[user1, user2])
        db.execute = AsyncMock(return_value=mock_result)
        mock_svc = MagicMock()
        mock_svc.generate_recommendations = AsyncMock(
            side_effect=[Exception("u1 fail"), [{"id": "r2"}]]
        )
        with patch(
            "app.services.recommendation_scheduler.AsyncSessionLocal",
            _mock_db_session(db),
        ):
            with _patched_rec_svc(mock_svc):
                await run_recommendation_scan()
        assert mock_svc.generate_recommendations.await_count == 2

    @pytest.mark.asyncio
    async def test_outer_exception_swallowed(self) -> None:
        """外层异常被吞掉，不传播."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=ConnectionError("db down"))
        with patch(
            "app.services.recommendation_scheduler.AsyncSessionLocal",
            _mock_db_session(db),
        ):
            await run_recommendation_scan()
        # 静默成功


class TestSchedulerLoop:
    @pytest.mark.asyncio
    async def test_loop_runs_scan_once_then_sleep(self) -> None:
        """loop 执行一次 scan 后 sleep（用极短间隔验证流程）."""
        scan_calls = 0
        sleep_calls = 0

        async def fake_scan():
            nonlocal scan_calls
            scan_calls += 1
            raise asyncio.CancelledError("test stop")

        async def fake_sleep(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            raise asyncio.CancelledError("test stop")

        with patch(
            "app.services.recommendation_scheduler.run_recommendation_scan",
            fake_scan,
        ):
            with patch(
                "app.services.recommendation_scheduler.asyncio.sleep", fake_sleep
            ):
                with pytest.raises(asyncio.CancelledError):
                    await recommendation_scheduler_loop()
        assert scan_calls == 1

    @pytest.mark.asyncio
    async def test_loop_continues_after_scan_error(self) -> None:
        """scan 抛异常时 loop 不退出，继续 sleep 后再次 scan."""
        scan_calls = 0
        sleep_count = 0

        async def fake_scan():
            nonlocal scan_calls
            scan_calls += 1

        async def fake_sleep(_):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError("stop after 2nd sleep")

        with patch(
            "app.services.recommendation_scheduler.run_recommendation_scan",
            fake_scan,
        ):
            with patch(
                "app.services.recommendation_scheduler.asyncio.sleep", fake_sleep
            ):
                with pytest.raises(asyncio.CancelledError):
                    await recommendation_scheduler_loop()
        assert scan_calls == 2
        assert sleep_count == 2


class TestConstants:
    def test_interval_constant(self) -> None:
        """默认扫描间隔 60 分钟."""
        assert RECOMMENDATION_SCAN_INTERVAL_MINUTES == 60
