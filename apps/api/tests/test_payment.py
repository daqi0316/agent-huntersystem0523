"""P5-3: 国内支付 service + endpoint tests (mock 模式)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.payment import router
    _app.include_router(router, prefix="/api/v1/payment")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_db(app, mock_db):
    from app.core.database import get_db
    from app.core.org_context import OrgContext, org_scoped_db

    async def _mock_get_db():
        yield mock_db

    async def _mock_org_scoped_db():
        org_ctx = OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr")
        yield org_ctx, mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


class TestConfig:
    def test_payment_mock_mode_default_true(self):
        from app.core.config import settings
        assert settings.payment_mock_mode is True

    def test_payment_wechat_merchant_default_empty(self):
        from app.core.config import settings
        assert settings.wechat_pay_merchant_id == ""

    def test_payment_alipay_app_default_empty(self):
        from app.core.config import settings
        assert settings.alipay_app_id == ""

    def test_order_expire_default_30min(self):
        from app.core.config import settings
        assert settings.payment_order_expire_minutes == 30


class TestPricingModel:
    def test_plan_pricing_starter_free(self):
        from app.models.payment import PaymentPlan, PLAN_PRICING_CENTS
        assert PLAN_PRICING_CENTS[PaymentPlan.STARTER] == 0

    def test_plan_pricing_pro(self):
        from app.models.payment import PaymentPlan, PLAN_PRICING_CENTS
        assert PLAN_PRICING_CENTS[PaymentPlan.PRO] == 29900

    def test_plan_pricing_enterprise(self):
        from app.models.payment import PaymentPlan, PLAN_PRICING_CENTS
        assert PLAN_PRICING_CENTS[PaymentPlan.ENTERPRISE] == 99900

    def test_plan_quotas_pro(self):
        from app.models.payment import PaymentPlan, PLAN_QUOTAS
        q = PLAN_QUOTAS[PaymentPlan.PRO]
        assert q["max_users"] == 50
        assert q["max_candidates"] == 10000
        assert q["llm_tokens_per_month"] == 2_000_000


class TestAuditLogEnum:
    def test_payment_paid_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.PAYMENT_PAID.value == "payment_paid"

    def test_payment_refund_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.PAYMENT_REFUND.value == "payment_refund"

    def test_payment_upgrade_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.PAYMENT_UPGRADE.value == "payment_upgrade"

    def test_payment_downgrade_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.PAYMENT_DOWNGRADE.value == "payment_downgrade"


class TestUpgradeProrate:
    def test_starter_to_pro_30d(self):
        from app.services.payment import compute_upgrade_prorate
        from app.models.payment import PaymentPlan
        assert compute_upgrade_prorate(PaymentPlan.STARTER, PaymentPlan.PRO, 30) == 29900

    def test_pro_to_enterprise_15d(self):
        from app.services.payment import compute_upgrade_prorate
        from app.models.payment import PaymentPlan
        assert compute_upgrade_prorate(PaymentPlan.PRO, PaymentPlan.ENTERPRISE, 15) == 35000

    def test_downgrade_returns_zero(self):
        from app.services.payment import compute_upgrade_prorate
        from app.models.payment import PaymentPlan
        assert compute_upgrade_prorate(PaymentPlan.PRO, PaymentPlan.STARTER, 15) == 0

    def test_same_plan_returns_zero(self):
        from app.services.payment import compute_upgrade_prorate
        from app.models.payment import PaymentPlan
        assert compute_upgrade_prorate(PaymentPlan.PRO, PaymentPlan.PRO, 15) == 0


class TestCreateOrderEndpoint:
    ROUTE = "/api/v1/payment/orders"

    def test_starter_plan_rejected(self, client, override_db, mock_db):
        resp = client.post(self.ROUTE, json={"plan": "starter", "channel": "wechat"})
        assert resp.status_code == 400

    def test_invalid_plan_rejected(self, client, override_db, mock_db):
        resp = client.post(self.ROUTE, json={"plan": "diamond", "channel": "wechat"})
        assert resp.status_code == 400

    def test_create_pro_order(self, client, override_db, mock_db):
        from app.services.payment import create_order, OrderResult
        from app.models.payment import PaymentPlan

        result = OrderResult(
            order_id="order-1", out_trade_no="ot-001",
            amount_cents=29900, prepay_id="mock_prepay_xyz",
            qr_code="weixin://mock", expired_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            mock=True,
        )
        with patch("app.api.payment.create_order", new=AsyncMock(return_value=result)):
            resp = client.post(self.ROUTE, json={"plan": "pro", "channel": "wechat"})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["plan"] == "pro"
        assert data["amount_cents"] == 29900
        assert data["mock"] is True
        assert data["qr_code"]


class TestMockPayEndpoint:
    ROUTE = "/api/v1/payment/mock-pay"

    def test_disabled_in_production(self, client, override_db, mock_db):
        with patch("app.core.config.settings.payment_mock_mode", False):
            resp = client.post(self.ROUTE, json={"out_trade_no": "ot-001"})
        assert resp.status_code == 403


class TestSubscriptionEndpoint:
    ROUTE = "/api/v1/payment/subscription"


class TestChangePlanEndpoint:
    ROUTE = "/api/v1/payment/subscription/change-plan"
