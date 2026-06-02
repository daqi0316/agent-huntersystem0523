"""Tests for app/services/aggregation_service.py.

覆盖 67 条 missed statements (19% → 90%+):
- run_aggregation: 空 ops 早期返回、bucket 计算、by_agent 聚合、upsert 逻辑
- _fetch_ops_in_range: 查询构建
- _percentile: 各种分位数边界条件
- aggregation_loop: 后台循环
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.operation_log import OperationLog, OperationStatus, ErrorCategory
from app.models.operation_stats import OperationStatsHourly
from app.services.aggregation_service import (
    _percentile,
    _fetch_ops_in_range,
    run_aggregation,
    aggregation_loop,
    AGGREGATION_INTERVAL_MINUTES,
)


def _make_op_log(
    agent_name: str = "screening",
    action: str = "screen",
    status: OperationStatus = OperationStatus.COMPLETED,
    duration_ms: float | None = 100.0,
    error_category: str | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    op = MagicMock(spec=OperationLog)
    op.agent_name = agent_name
    op.action = action
    op.status = status
    op.duration_ms = duration_ms
    op.error_category = error_category
    op.created_at = created_at or datetime(2026, 6, 1, 10, 30, 0, tzinfo=timezone.utc)
    return op


def _make_stats_row(**kwargs) -> MagicMock:
    row = MagicMock(spec=OperationStatsHourly)
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


class FakeAsyncSessionLocal:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _patch_session_local(db):
    return patch(
        "app.services.aggregation_service.AsyncSessionLocal",
        return_value=FakeAsyncSessionLocal(db),
    )


# ─── _percentile ──────────────────────────────────────────────────────


class TestPercentile:
    def test_empty_list_returns_zero(self):
        assert _percentile([], 50) == 0.0

    def test_single_element(self):
        assert _percentile([42.0], 50) == 42.0
        assert _percentile([42.0], 95) == 42.0

    def test_median_exact(self):
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_median_interpolated(self):
        result = _percentile([1.0, 2.0, 3.0, 4.0], 50)
        assert 2.0 <= result <= 3.0

    def test_p95(self):
        vals = list(range(1, 101))
        result = _percentile(vals, 95)
        assert result >= 90

    def test_p0(self):
        assert _percentile([10.0, 20.0, 30.0], 0) == 10.0

    def test_p100(self):
        assert _percentile([10.0, 20.0, 30.0], 100) == 30.0


# ─── _fetch_ops_in_range ──────────────────────────────────────────────


class TestFetchOpsInRange:
    async def test_queries_with_time_range(self):
        db = MagicMock()
        start = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        ops = [_make_op_log(), _make_op_log()]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ops
        db.execute = AsyncMock(return_value=result_mock)

        fetched = await _fetch_ops_in_range(db, start, end)

        db.execute.assert_called_once()
        assert len(fetched) == 2


# ─── run_aggregation ─────────────────────────────────────────────────


class TestRunAggregation:
    async def test_empty_ops_returns_zero(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        with _patch_session_local(db):
            result = await run_aggregation()

        assert result == 0
        db.add.assert_not_called()

    async def test_single_op_creates_new_row(self):
        op = _make_op_log(
            agent_name="screen", action="screen_resume",
            status=OperationStatus.COMPLETED, duration_ms=150.0,
        )
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = [op]
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.add = MagicMock()
        db.commit = AsyncMock()

        with _patch_session_local(db):
            count = await run_aggregation()

        assert count == 1
        db.add.assert_called_once()
        call_args = db.add.call_args[0][0]
        assert call_args.total_ops == 1
        assert call_args.success_count == 1
        assert call_args.fail_count == 0

    async def test_multiple_ops_same_agent_action(self):
        ops = [
            _make_op_log(agent_name="s", action="a", status=OperationStatus.COMPLETED, duration_ms=100.0),
            _make_op_log(agent_name="s", action="a", status=OperationStatus.COMPLETED, duration_ms=200.0),
            _make_op_log(agent_name="s", action="a", status=OperationStatus.FAILED, duration_ms=None),
        ]
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = ops
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.add = MagicMock()
        db.commit = AsyncMock()

        with _patch_session_local(db):
            count = await run_aggregation()

        assert count == 1
        call_args = db.add.call_args[0][0]
        assert call_args.total_ops == 3
        assert call_args.success_count == 2
        assert call_args.fail_count == 1

    async def test_failed_op_system_error_counts(self):
        op = _make_op_log(
            agent_name="s", action="a",
            status=OperationStatus.FAILED,
            error_category=ErrorCategory.SYSTEM.value,
            duration_ms=50.0,
        )
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = [op]
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.add = MagicMock()
        db.commit = AsyncMock()

        with _patch_session_local(db):
            await run_aggregation()

        call_args = db.add.call_args[0][0]
        assert call_args.fail_count == 1
        assert call_args.system_error_count == 1

    async def test_existing_row_gets_updated(self):
        op = _make_op_log(agent_name="s", action="a", status=OperationStatus.COMPLETED)
        existing = _make_stats_row(
            total_ops=5, success_count=3, fail_count=2,
            system_error_count=1, avg_duration_ms=100.0,
            p50_duration_ms=90.0, p95_duration_ms=150.0,
        )
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = [op]
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=existing)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.commit = AsyncMock()

        with _patch_session_local(db):
            count = await run_aggregation()

        assert count == 1
        db.add.assert_not_called()
        assert existing.total_ops == 1
        assert existing.success_count == 1

    async def test_null_duration_excluded_from_avg(self):
        ops = [
            _make_op_log(agent_name="s", action="a", status=OperationStatus.COMPLETED, duration_ms=None),
            _make_op_log(agent_name="s", action="a", status=OperationStatus.COMPLETED, duration_ms=200.0),
        ]
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = ops
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.add = MagicMock()
        db.commit = AsyncMock()

        with _patch_session_local(db):
            await run_aggregation()

        call_args = db.add.call_args[0][0]
        assert call_args.avg_duration_ms == 200.0

    async def test_null_action_becomes_empty_string(self):
        op = _make_op_log(agent_name="s", action=None)
        result_mock_ops = MagicMock()
        result_mock_ops.scalars.return_value.all.return_value = [op]
        result_mock_existing = MagicMock()
        result_mock_existing.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_mock_ops, result_mock_existing])
        db.add = MagicMock()
        db.commit = AsyncMock()

        with _patch_session_local(db):
            await run_aggregation()

        call_args = db.add.call_args[0][0]
        assert call_args.action == ""


# ─── aggregation_loop ─────────────────────────────────────────────────


class TestAggregationLoop:
    async def test_loop_stops_on_exception(self):
        with patch("app.services.aggregation_service.run_aggregation", side_effect=RuntimeError("stop")), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = RuntimeError("stop loop")
            with pytest.raises(RuntimeError, match="stop loop"):
                await aggregation_loop()

    async def test_interval_constant(self):
        assert AGGREGATION_INTERVAL_MINUTES == 5
