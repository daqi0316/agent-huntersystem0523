"""Tests for app/api/dashboard.py — KPI aggregation + operations summary/trend.

覆盖 dashboard_stats (/stats) 的 4 个 KPI + 动态 + 趋势
以及 operation_summary 和 operation_trend 的聚合逻辑。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dashboard import router as dashboard_router
from app.core.database import get_db
from app.core.dependencies import get_current_user_id


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_user_id() -> str:
    return "user-1"


@pytest.fixture
def app(fake_user_id: str) -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router, prefix="/dashboard")
    app.dependency_overrides[get_current_user_id] = lambda: fake_user_id
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _patch_db(app: FastAPI, db_mock):
    async def fake_get_db():
        yield db_mock

    app.dependency_overrides[get_db] = fake_get_db


def _count_result(value: int) -> MagicMock:
    r = MagicMock()
    r.scalar = MagicMock(return_value=value)
    return r


def _rows_result(rows: list) -> MagicMock:
    r = MagicMock()
    r.__iter__ = MagicMock(return_value=iter(rows))
    return r


def _scalars_result(items: list) -> MagicMock:
    """Mock for result.scalars().all() pattern."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=scalars)
    return result


# ─── dashboard_stats (GET /dashboard/stats) ───────────────────────────


class TestDashboardStats:
    def test_success_all_kpis(self, app: FastAPI) -> None:
        """正常情况: 4 个 KPI + 趋势 + 动态."""
        # 6 个 db.execute 调用顺序:
        # 1. _count(candidates) → 100
        # 2. _count(job_positions) → 12
        # 3. _count_with_condition(interviews) → 5
        # 4. _count_this_month(candidates hired) → 3
        # 5. _recent_activities → candidates rows
        # 6. _recent_activities → jobs rows
        # 7-36. _candidate_trend → 30 天各 1 个 scalar
        now = datetime.now(timezone.utc)
        cand_row = ("candidate", "Alice", now)
        job_row = ("job", "Engineer", now)

        results = [
            _count_result(100),                    # total_candidates
            _count_result(12),                     # total_jobs
            _count_result(5),                      # active_interviews
            _count_result(3),                      # monthly_onboards
            _rows_result([cand_row]),              # recent_activities.candidates
            _rows_result([job_row]),               # recent_activities.jobs
        ]
        # 30 天趋势(每 2 天一个点, 共 15 个点,但实际循环 30 次)
        for _ in range(30):
            results.append(_count_result(2))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()["data"]
        kpis = {k["key"]: k for k in data["kpis"]}
        assert kpis["candidates"]["value"] == 100
        assert kpis["jobs"]["value"] == 12
        assert kpis["interviews"]["value"] == 5
        assert kpis["onboards"]["value"] == 3
        assert kpis["candidates"]["label"] == "候选人总数"
        assert kpis["jobs"]["label"] == "招聘职位"
        # 动态: 2 条
        assert len(data["recent_activities"]) == 2
        # 趋势: 30 天每 2 天一个点 = 15 个点
        assert len(data["trend"]) == 15

    def test_kpis_none_values_become_zero(self, app: FastAPI) -> None:
        """scalar() 返回 None → KPI value = 0."""
        results = [
            _count_result(None),                   # total_candidates → 0
            _count_result(None),                   # total_jobs → 0
            _count_result(None),                   # active_interviews → 0
            _count_result(None),                   # monthly_onboards → 0
            _rows_result([]),                      # candidates activities
            _rows_result([]),                      # jobs activities
        ]
        # 30 天趋势
        for _ in range(30):
            results.append(_count_result(None))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        kpis = resp.json()["data"]["kpis"]
        assert all(k["value"] == 0 for k in kpis)

    def test_count_exception_returns_zero(self, app: FastAPI) -> None:
        """_count 抛异常 → 返回 0 (容错)."""
        db = MagicMock()
        # 第一次 execute 抛异常
        db.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()["data"]
        kpis = {k["key"]: k for k in data["kpis"]}
        # 所有 count 都失败 → 全部为 0
        assert kpis["candidates"]["value"] == 0
        assert kpis["jobs"]["value"] == 0

    def test_recent_activities_null_timestamp(self, app: FastAPI) -> None:
        """created_at 为 None → time_str = '--:--'."""
        now = datetime.now(timezone.utc)
        cand_row = ("candidate", "Bob", None)  # timestamp 为 None
        job_row = ("job", "Dev", now)

        results = [
            _count_result(1),
            _count_result(1),
            _count_result(0),
            _count_result(0),
            _rows_result([cand_row]),
            _rows_result([job_row]),
        ]
        for _ in range(30):
            results.append(_count_result(0))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        activities = resp.json()["data"]["recent_activities"]
        # 找到 time 为 "--:--" 的
        none_ts = [a for a in activities if a["time"] == "--:--"]
        assert len(none_ts) == 1
        assert "新增候选人 Bob" in none_ts[0]["text"]
        assert none_ts[0]["type"] == "apply"

    def test_recent_activities_job_type(self, app: FastAPI) -> None:
        """职位活动的 type 字段是 'job'."""
        now = datetime.now(timezone.utc)
        job_row = ("job", "高级工程师", now)

        results = [
            _count_result(0),
            _count_result(0),
            _count_result(0),
            _count_result(0),
            _rows_result([]),
            _rows_result([job_row]),
        ]
        for _ in range(30):
            results.append(_count_result(0))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        activities = resp.json()["data"]["recent_activities"]
        job_act = [a for a in activities if a["type"] == "job"]
        assert len(job_act) == 1
        assert "新增职位「高级工程师」" in job_act[0]["text"]

    def test_recent_activities_sorted_by_time_desc(self, app: FastAPI) -> None:
        """活动按 time 倒序排列."""
        now = datetime.now(timezone.utc)
        cand_row1 = ("candidate", "Alice", now.replace(hour=10, minute=30))
        job_row = ("job", "PM", now.replace(hour=15, minute=0))

        results = [
            _count_result(0),
            _count_result(0),
            _count_result(0),
            _count_result(0),
            _rows_result([cand_row1]),
            _rows_result([job_row]),
        ]
        for _ in range(30):
            results.append(_count_result(0))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        activities = resp.json()["data"]["recent_activities"]
        # 15:00 应该在 10:30 之前(倒序)
        times = [a["time"] for a in activities]
        assert times.index("15:00") < times.index("10:30")

    def test_candidate_trend_empty_falls_back(self, app: FastAPI) -> None:
        """30 天都抛异常 → 趋势 fallback 到 [{date: now, count: 0}]."""
        db = MagicMock()
        # 前 6 个调用成功(但返回 0), 后面 30 个 trend 全部抛异常
        results = [
            _count_result(0),  # candidates
            _count_result(0),  # jobs
            _count_result(0),  # interviews
            _count_result(0),  # onboards
            _rows_result([]),  # candidates activities
            _rows_result([]),  # jobs activities
        ]
        for _ in range(30):
            results.append(RuntimeError("trend fail"))

        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        trend = resp.json()["data"]["trend"]
        assert len(trend) == 1
        assert trend[0]["count"] == 0
        assert "-" in trend[0]["date"]  # MM-DD format

    def test_candidate_trend_sparse_every_2_days(self, app: FastAPI) -> None:
        """趋势只取偶数天(i % 2 == 0)."""
        results = [
            _count_result(0), _count_result(0), _count_result(0), _count_result(0),
            _rows_result([]), _rows_result([]),
        ]
        # 30 天 trend, 都返回 1
        for _ in range(30):
            results.append(_count_result(1))

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/stats")
        trend = resp.json()["data"]["trend"]
        # 30 天里 i=28,26,24,...,0,2 = 15 个点
        assert len(trend) == 15
        # 所有点的 count 都应是 1
        assert all(p["count"] == 1 for p in trend)
        # 日期格式 MM-DD
        for p in trend:
            assert len(p["date"]) == 5
            assert p["date"][2] == "-"


# ─── operation_summary (GET /dashboard/operations/summary) ────────────


def _make_op_stat(
    agent_name: str = "router",
    total_ops: int = 10,
    success_count: int = 8,
    fail_count: int = 2,
    system_error_count: int = 1,
    avg_duration_ms: int | None = 120,
    bucket_hour: datetime | None = None,
) -> MagicMock:
    r = MagicMock()
    r.agent_name = agent_name
    r.total_ops = total_ops
    r.success_count = success_count
    r.fail_count = fail_count
    r.system_error_count = system_error_count
    r.avg_duration_ms = avg_duration_ms
    r.bucket_hour = bucket_hour or datetime.now(timezone.utc)
    return r


class TestOperationSummary:
    def test_aggregates_by_agent(self, app: FastAPI) -> None:
        """多个 hour 桶的数据聚合成 per-agent 摘要."""
        now = datetime.now(timezone.utc)
        rows = [
            _make_op_stat(agent_name="router", total_ops=5, success_count=5, fail_count=0,
                          system_error_count=0, avg_duration_ms=100, bucket_hour=now),
            _make_op_stat(agent_name="router", total_ops=3, success_count=2, fail_count=1,
                          system_error_count=1, avg_duration_ms=200, bucket_hour=now),
            _make_op_stat(agent_name="screener", total_ops=4, success_count=3, fail_count=1,
                          system_error_count=0, avg_duration_ms=300, bucket_hour=now),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result(rows))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/summary")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["overall"]["period_hours"] == 24
        # router: total=8, success=7, fail=1, sys_err=1
        # screener: total=4, success=3, fail=1, sys_err=0
        # 整体: total=12, success=10
        assert data["overall"]["total_ops"] == 12
        assert data["overall"]["success_rate"] == 83.3  # 10/12 * 100 = 83.33
        assert data["overall"]["system_errors"] == 1

        agents_by_name = {a["agent_name"]: a for a in data["agents"]}
        router = agents_by_name["router"]
        assert router["total_ops"] == 8
        assert router["success_count"] == 7
        assert router["fail_count"] == 1
        assert router["system_error_count"] == 1
        assert router["success_rate"] == 87.5  # 7/8 * 100
        # duration: (100 + 200) / 2 = 150.0
        assert router["avg_duration_ms"] == 150.0

        screener = agents_by_name["screener"]
        assert screener["total_ops"] == 4
        assert screener["success_rate"] == 75.0  # 3/4 * 100
        assert screener["avg_duration_ms"] == 300.0

    def test_empty_data_returns_zero_overall(self, app: FastAPI) -> None:
        """无数据 → 全部为 0."""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result([]))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/summary")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["overall"]["total_ops"] == 0
        assert data["overall"]["success_rate"] == 0
        assert data["overall"]["system_errors"] == 0
        assert data["agents"] == []

    def test_null_avg_duration_excluded(self, app: FastAPI) -> None:
        """avg_duration_ms 为 None → 不参与平均计算."""
        rows = [
            _make_op_stat(agent_name="x", total_ops=5, success_count=5, avg_duration_ms=None),
            _make_op_stat(agent_name="x", total_ops=3, success_count=3, avg_duration_ms=100),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result(rows))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/summary")
        agent = resp.json()["data"]["agents"][0]
        # 只有 100ms 参与平均 → 100.0
        assert agent["avg_duration_ms"] == 100.0

    def test_all_zero_ops_rates(self, app: FastAPI) -> None:
        """total_ops=0 → success_rate=0 (避免除零)."""
        rows = [_make_op_stat(agent_name="x", total_ops=0, success_count=0)]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result(rows))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/summary")
        agent = resp.json()["data"]["agents"][0]
        assert agent["success_rate"] == 0


# ─── operation_trend (GET /dashboard/operations/trend) ────────────────


class TestOperationTrend:
    def test_success(self, app: FastAPI) -> None:
        """按 hour 桶聚合 + rolling avg duration."""
        now = datetime.now(timezone.utc)
        rows = [
            _make_op_stat(agent_name="router", total_ops=3, success_count=2, fail_count=1,
                          avg_duration_ms=100, bucket_hour=now.replace(hour=10, minute=0)),
            _make_op_stat(agent_name="router", total_ops=2, success_count=2, fail_count=0,
                          avg_duration_ms=200, bucket_hour=now.replace(hour=10, minute=0)),
            _make_op_stat(agent_name="screener", total_ops=5, success_count=4, fail_count=1,
                          avg_duration_ms=300, bucket_hour=now.replace(hour=10, minute=0)),
            _make_op_stat(agent_name="router", total_ops=1, success_count=1, fail_count=0,
                          avg_duration_ms=None, bucket_hour=now.replace(hour=11, minute=0)),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result(rows))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/trend")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "router" in data["agents"]
        assert "screener" in data["agents"]
        assert len(data["timeline"]) == 2  # 10:00, 11:00

        # 10:00 桶
        bucket_10 = [b for b in data["timeline"] if b["hour"] == "10:00"][0]
        assert bucket_10["router_total"] == 5  # 3 + 2
        assert bucket_10["router_success"] == 4  # 2 + 2
        assert bucket_10["router_fail"] == 1
        assert bucket_10["screener_total"] == 5
        # rolling avg: (100 + 200) / 2 = 150.0
        assert bucket_10["router_avg_dur"] == 150.0

        # 11:00 桶
        bucket_11 = [b for b in data["timeline"] if b["hour"] == "11:00"][0]
        assert bucket_11["router_total"] == 1
        # avg_duration 为 None → 不应有 avg_dur 字段被累加
        # 但由于初始值 0, ((0*0 + None)/(0+1)) 会出错
        # 检查实现是否安全(这里只测不抛异常)
        assert "router_total" in bucket_11

    def test_timeline_sorted_ascending(self, app: FastAPI) -> None:
        """timeline 按 hour 升序."""
        now = datetime.now(timezone.utc)
        rows = [
            _make_op_stat(agent_name="x", total_ops=1, bucket_hour=now.replace(hour=12)),
            _make_op_stat(agent_name="x", total_ops=1, bucket_hour=now.replace(hour=9)),
            _make_op_stat(agent_name="x", total_ops=1, bucket_hour=now.replace(hour=15)),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result(rows))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/trend")
        hours = [b["hour"] for b in resp.json()["data"]["timeline"]]
        assert hours == ["09:00", "12:00", "15:00"]

    def test_empty_returns_empty(self, app: FastAPI) -> None:
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result([]))
        _patch_db(app, db)

        resp = TestClient(app).get("/dashboard/operations/trend")
        data = resp.json()["data"]
        assert data["agents"] == []
        assert data["timeline"] == []

    def test_hours_param_passed_to_query(self, app: FastAPI) -> None:
        """hours 参数影响 since 计算."""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result([]))
        _patch_db(app, db)

        TestClient(app).get("/dashboard/operations/trend", params={"hours": 48})

        # 验证 db.execute 被调用(不报错即通过, hours 参数被接受)
        assert db.execute.await_count == 1
