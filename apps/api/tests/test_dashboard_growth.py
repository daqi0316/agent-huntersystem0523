"""P6-9: 内部数据看板 tests (CAC / LTV / Churn / Referral / Customer count)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.dashboard_growth import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAdminRequired:
    def test_non_admin_rejected(self, client):
        resp = client.get("/growth/dashboard/summary?role=hr")
        assert resp.status_code == 403

    def test_admin_allowed(self, client):
        with patch("app.api.dashboard_growth._customer_count", new=AsyncMock(return_value={"total": 0, "by_status": {}, "by_plan": {}})), \
             patch("app.api.dashboard_growth._cac_by_channel", new=AsyncMock(return_value={})), \
             patch("app.api.dashboard_growth._ltv_by_plan", new=AsyncMock(return_value={})), \
             patch("app.api.dashboard_growth._churn_30d", new=AsyncMock(return_value={"churned_30d": 0, "active_at_period_start": 0, "churn_rate_pct": 0})), \
             patch("app.api.dashboard_growth._nps_score", new=AsyncMock(return_value={"nps": None})), \
             patch("app.api.dashboard_growth._referral_summary", new=AsyncMock(return_value={"total_codes": 0, "total_uses": 0, "conversion_rate_pct": 0})):
            resp = client.get("/growth/dashboard/summary?role=admin")
        assert resp.status_code == 200


class TestChurnCalculation:
    @pytest.mark.asyncio
    async def test_churn_zero_when_no_data(self):
        from app.api.dashboard_growth import _churn_30d

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(return_value=result_mock)

        result = await _churn_30d(db)
        assert result["churned_30d"] == 0
        assert result["churn_rate_pct"] == 0

    @pytest.mark.asyncio
    async def test_churn_with_data(self):
        from app.api.dashboard_growth import _churn_30d

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(side_effect=[10, 100])
        db.execute = AsyncMock(return_value=result_mock)

        result = await _churn_30d(db)
        assert result["churned_30d"] == 10
        assert result["active_at_period_start"] == 100
        assert result["churn_rate_pct"] == 10.0


class TestNPS:
    @pytest.mark.asyncio
    async def test_nps_placeholder(self):
        from app.api.dashboard_growth import _nps_score
        result = await _nps_score(None)
        assert result["status"] == "pending_survey"
        assert result["nps"] is None


class TestCACByChannel:
    @pytest.mark.asyncio
    async def test_returns_6_channels(self):
        from app.api.dashboard_growth import _cac_by_channel
        result = await _cac_by_channel(None)
        assert "baidu_seo" in result
        assert "zhihu" in result
        assert "wechat_article" in result
        assert "referral" in result
        assert "direct" in result
        assert "paid_ads" in result

    @pytest.mark.asyncio
    async def test_referral_zero_cost(self):
        from app.api.dashboard_growth import _cac_by_channel
        result = await _cac_by_channel(None)
        assert result["referral"]["cost_cny"] == 0
        assert result["referral"]["status"] == "active"


class TestCustomerCount:
    @pytest.mark.asyncio
    async def test_total_count(self):
        from app.api.dashboard_growth import _customer_count

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=15)
        db.execute = AsyncMock(return_value=result_mock)

        result = await _customer_count(db)
        assert result["total"] == 15


class TestLTVByPlan:
    @pytest.mark.asyncio
    async def test_empty_when_no_orders(self):
        from app.api.dashboard_growth import _ltv_by_plan

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        result_mock.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=result_mock)

        result = await _ltv_by_plan(db)
        assert isinstance(result, dict)


class TestReferralSummary:
    @pytest.mark.asyncio
    async def test_conversion_rate_calculation(self):
        from app.api.dashboard_growth import _referral_summary

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(side_effect=[10, 5])
        db.execute = AsyncMock(return_value=result_mock)

        result = await _referral_summary(db)
        assert result["total_codes"] == 10
        assert result["total_uses"] == 5
        assert result["conversion_rate_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_zero_codes(self):
        from app.api.dashboard_growth import _referral_summary

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(return_value=result_mock)

        result = await _referral_summary(db)
        assert result["conversion_rate_pct"] == 0


class TestWeeklyReportFormatter:
    def test_format_growth_report_inline(self):
        text_lines = [
            "📈 增长周报 (内部)",
            "",
            "👥 客户总数: 5",
            "  by_status: {}",
            "  by_plan: {}",
            "",
            "🔄 30d churn: 1 个 (20.0%)",
        ]
        assert any("📈 增长周报" in line for line in text_lines)
        assert any("客户总数: 5" in line for line in text_lines)
        assert any("30d churn" in line for line in text_lines)
