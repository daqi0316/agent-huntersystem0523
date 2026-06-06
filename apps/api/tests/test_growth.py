"""P6-3 + P6-4: self-serve trial + referral tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.growth import router
    _app.include_router(router)
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


class TestTrialConstants:
    def test_trial_14_days(self):
        from app.services.referral import TRIAL_DAYS
        assert TRIAL_DAYS == 14

    def test_remind_3_days_before(self):
        from app.services.referral import TRIAL_REMIND_DAYS_BEFORE
        assert TRIAL_REMIND_DAYS_BEFORE == 3


class TestReferralCodeGeneration:
    def test_length_8(self):
        from app.services.referral import _generate_referral_code
        code = _generate_referral_code()
        assert len(code) == 8

    def test_excludes_ambiguous_chars(self):
        from app.services.referral import _generate_referral_code
        for _ in range(20):
            code = _generate_referral_code()
            assert "0" not in code
            assert "O" not in code
            assert "I" not in code
            assert "1" not in code
            assert "L" not in code

    def test_only_uppercase_alphanumeric(self):
        from app.services.referral import _generate_referral_code
        import re
        for _ in range(20):
            code = _generate_referral_code()
            assert re.match(r"^[A-Z0-9]{8}$", code), f"invalid code: {code}"


class TestTrialStatusEndpoint:
    def test_no_subscription(self, client, override_db, mock_db):
        with patch("app.services.payment.get_active_subscription", new=AsyncMock(return_value=None)):
            resp = client.get("/trial/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trial_active"] is False
        assert data["days_remaining"] == 0

    def test_active_trial(self, client, override_db, mock_db):
        from app.models.payment import Subscription, PaymentPlan, SubscriptionStatus

        sub = MagicMock()
        sub.trial_end_at = datetime.now(timezone.utc) + timedelta(days=10)
        sub.plan = PaymentPlan.STARTER
        sub.status = SubscriptionStatus.ACTIVE

        with patch("app.services.payment.get_active_subscription", new=AsyncMock(return_value=sub)):
            resp = client.get("/trial/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trial_active"] is True
        assert 9 <= data["days_remaining"] <= 10

    def test_expired_trial(self, client, override_db, mock_db):
        from app.models.payment import Subscription, PaymentPlan, SubscriptionStatus

        sub = MagicMock()
        sub.trial_end_at = datetime.now(timezone.utc) - timedelta(days=1)
        sub.plan = PaymentPlan.STARTER
        sub.status = SubscriptionStatus.ACTIVE

        with patch("app.services.payment.get_active_subscription", new=AsyncMock(return_value=sub)):
            resp = client.get("/trial/status")
        data = resp.json()["data"]
        assert data["trial_active"] is False
        assert data["days_remaining"] == 0


class TestStartTrialEndpoint:
    def test_start_trial_creates(self, client, override_db, mock_db):
        from app.models.payment import Subscription, PaymentPlan, SubscriptionStatus

        sub = MagicMock()
        sub.trial_end_at = datetime.now(timezone.utc) + timedelta(days=14)
        sub.plan = PaymentPlan.STARTER
        sub.status = SubscriptionStatus.ACTIVE

        with patch("app.api.growth.start_trial_for_org", new=AsyncMock(return_value=sub)):
            resp = client.post("/trial/start")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trial_active"] is True
        assert data["plan"] == "starter"


class TestReferralCodeEndpoint:
    def test_create_new_code(self, client, override_db, mock_db):
        from app.models.referral import ReferralCode

        ref = MagicMock()
        ref.code = "ABC12345"
        ref.uses = 0
        ref.max_uses = 100
        ref.seat_reward = 1

        with patch("app.api.growth.get_referral_code_for_org", new=AsyncMock(return_value=None)), \
             patch("app.api.growth.create_referral_code", new=AsyncMock(return_value=ref)):
            resp = client.get("/referral/code")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["code"] == "ABC12345"
        assert "share_url" in data
        assert "ref=ABC12345" in data["share_url"]

    def test_existing_code_returned(self, client, override_db, mock_db):
        from app.models.referral import ReferralCode

        ref = MagicMock()
        ref.code = "EXISTING1"
        ref.uses = 5
        ref.max_uses = 100
        ref.seat_reward = 1

        with patch("app.api.growth.get_referral_code_for_org", new=AsyncMock(return_value=ref)):
            resp = client.get("/referral/code")
        data = resp.json()["data"]
        assert data["code"] == "EXISTING1"
        assert data["uses"] == 5


class TestRedeemReferralEndpoint:
    def test_short_code_rejected(self, client, override_db, mock_db):
        resp = client.post("/referral/redeem?user_id=u1&org_id=o1", json={"code": "AB"})
        assert resp.status_code == 422

    def test_invalid_code_returns_400(self, client, override_db, mock_db):
        with patch("app.api.growth.redeem_referral_code", new=AsyncMock(side_effect=ValueError("invalid referral code"))):
            resp = client.post("/referral/redeem?user_id=u1&org_id=o1", json={"code": "BADCODE"})
        assert resp.status_code == 400

    def test_self_referral_rejected(self, client, override_db, mock_db):
        with patch("app.api.growth.redeem_referral_code", new=AsyncMock(side_effect=ValueError("cannot self-refer"))):
            resp = client.post("/referral/redeem?user_id=u1&org_id=o1", json={"code": "SELFCODE"})
        assert resp.status_code == 400


class TestReferralUsesEndpoint:
    def test_list_uses(self, client, override_db, mock_db):
        from app.models.referral import ReferralUse

        uses = [
            MagicMock(
                new_org_id=f"o{i}", new_user_id=f"u{i}",
                ip_address="1.1.1.1", seat_rewarded=True,
                created_at=datetime.now(timezone.utc),
            )
            for i in range(3)
        ]
        with patch("app.api.growth.list_referral_uses_for_org", new=AsyncMock(return_value=uses)):
            resp = client.get("/referral/uses")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 3


class TestRedeemService:
    @pytest.mark.asyncio
    async def test_self_refer_rejected(self):
        from app.services.referral import redeem_referral_code

        db = AsyncMock()
        ref = MagicMock()
        ref.org_id = "same-org"
        ref.expires_at = None
        ref.max_uses = 100
        ref.uses = 0
        ref.id = "ref-1"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ref)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError, match="cannot self-refer"):
            await redeem_referral_code(db, "ABC12345", "same-org", "u1")

    @pytest.mark.asyncio
    async def test_max_uses_rejected(self):
        from app.services.referral import redeem_referral_code

        db = AsyncMock()
        ref = MagicMock()
        ref.org_id = "org-1"
        ref.expires_at = None
        ref.max_uses = 5
        ref.uses = 5
        ref.id = "ref-1"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=ref)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError, match="max uses"):
            await redeem_referral_code(db, "ABC12345", "org-2", "u1")


class TestGrantSeatReward:
    @pytest.mark.asyncio
    async def test_grant_seat_increments(self):
        from app.services.referral import grant_seat_reward

        db = AsyncMock()
        org = MagicMock()
        org.quota_max_users = 10
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=org)
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        new_quota = await grant_seat_reward(db, "org-1", seats=2)
        assert org.quota_max_users == 12
        assert new_quota == 12
