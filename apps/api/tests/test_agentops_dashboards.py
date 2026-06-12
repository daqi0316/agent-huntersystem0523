"""Tests for AgentOps Dashboards module (P2-C Stage 14)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agentops.dashboards.metrics import DashboardMetrics


class TestDashboardMetrics:
    """DashboardMetrics 单元测试（mock DB 层）。"""

    @patch("app.agentops.dataset.experiment_models.ExperimentStore")
    @patch("app.agentops.dataset.models.DatasetStore")
    @patch("app.agentops.feedback.service.FeedbackService")
    async def test_overview(self, mock_fb, mock_ds, mock_exp_store) -> None:
        from types import SimpleNamespace

        mock_exp = SimpleNamespace(id="exp-1")
        inst = mock_exp_store.return_value
        # overview() 调两次 list_experiments (limit=1 + limit=10000)
        inst.list_experiments = AsyncMock(return_value=([mock_exp], 5))
        inst.list_runs_by_experiment = AsyncMock(return_value=([], 12))

        mock_ds_inst = mock_ds.return_value
        mock_ds_inst.list = AsyncMock(return_value=([], 20))

        mock_fb_inst = mock_fb.return_value
        mock_fb_inst.list_feedback = AsyncMock(return_value=([], 8))

        result = await DashboardMetrics.overview()
        assert result["total_experiments"] == 5
        assert result["total_runs"] == 12
        assert result["total_dataset_items"] == 20
        assert result["total_feedback"] == 8

    @patch("app.agentops.dataset.experiment_models.ExperimentStore")
    async def test_quality_summary_empty(self, mock_store) -> None:
        inst = mock_store.return_value
        inst.list_experiments = AsyncMock(return_value=([], 0))

        result = await DashboardMetrics.quality_summary()
        assert result["avg_score"] == 0.0
        assert result["total_runs"] == 0
        assert result["completed_experiments"] == 0

    @patch("app.agentops.dataset.experiment_models.ExperimentStore")
    async def test_recent_runs_empty(self, mock_store) -> None:
        inst = mock_store.return_value
        inst.list_experiments = AsyncMock(return_value=([], 0))

        result = await DashboardMetrics.recent_runs(limit=10)
        assert result == []

    @patch("app.agentops.dataset.experiment_models.ExperimentStore")
    async def test_evaluator_performance_empty(self, mock_store) -> None:
        inst = mock_store.return_value
        inst.list_experiments = AsyncMock(return_value=([], 0))

        result = await DashboardMetrics.evaluator_performance()
        assert result == {}

    @patch("app.agentops.feedback.service.FeedbackService")
    async def test_feedback_summary_empty(self, mock_fb) -> None:
        inst = mock_fb.return_value
        inst.list_feedback = AsyncMock(return_value=([], 0))
        inst.get_stats = AsyncMock(return_value=type("Stats", (), {"category_stats": {}})())

        result = await DashboardMetrics.feedback_summary()
        assert result["total"] == 0

    @patch("app.agentops.dataset.experiment_models.ExperimentStore")
    async def test_quality_summary_with_data(self, mock_store) -> None:
        """模拟有实验运行数据的情况。"""
        from types import SimpleNamespace

        # 模拟一个 completed 的实验
        mock_exp = SimpleNamespace(
            id="exp-1",
            name="Test",
            status="completed",
            dataset_item_ids="[]",
            evaluator_type="rule_based",
            created_by="",
            created_at=None,
            updated_at=None,
        )
        # 模拟一个运行记录
        mock_run = SimpleNamespace(
            id="run-1",
            avg_score=0.85,
            passed_items=8,
            total_items=10,
            status="completed",
            started_at=None,
            completed_at=None,
            duration_ms=100,
            results=[{"category": "screening", "score": 0.9}, {"category": "screening", "score": 0.8}],
        )

        inst = mock_store.return_value
        inst.list_experiments = AsyncMock(return_value=([mock_exp], 1))
        inst.list_runs_by_experiment = AsyncMock(return_value=([mock_run], 1))

        result = await DashboardMetrics.quality_summary()
        assert result["completed_experiments"] == 1
        assert result["total_runs"] == 1
        # avg = 0.85 / 1
        assert result["avg_score"] == 0.85
        # pass rate = 8 / 10
        assert result["pass_rate"] == 0.8
        assert result["category_scores"]["screening"] == 0.85  # (0.9 + 0.8) / 2


class TestDashboardRouter:
    """Dashboard router 基础测试。"""

    def test_router_has_endpoints(self) -> None:
        from app.agentops.dashboards.router import router

        routes = [r.path for r in router.routes]
        assert "/dashboard/agentops/overview" in routes
        assert "/dashboard/agentops/quality" in routes
        assert "/dashboard/agentops/recent-runs" in routes
        assert "/dashboard/agentops/evaluators" in routes
        assert "/dashboard/agentops/feedback" in routes
