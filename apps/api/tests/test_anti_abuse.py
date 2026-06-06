"""P5-11: 反垃圾/反滥用 tests (手机验证 + 设备指纹 + 邀请防刷 + LLM 熔断)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.anti_abuse import router
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


class TestPhoneValidation:
    def test_valid_chinese_phone(self):
        from app.services.anti_abuse import validate_phone
        assert validate_phone("13800138000") is True
        assert validate_phone("17612345678") is True

    def test_invalid_phone(self):
        from app.services.anti_abuse import validate_phone
        assert validate_phone("12345") is False
        assert validate_phone("23800138000") is False
        assert validate_phone("1380013800") is False
        assert validate_phone("138001380000") is False
        assert validate_phone("") is False
        assert validate_phone("abc") is False


class TestDeviceFingerprint:
    def test_same_ua_ip_same_hash(self):
        from app.services.anti_abuse import compute_device_fingerprint
        h1 = compute_device_fingerprint("Mozilla/5.0", "1.1.1.1")
        h2 = compute_device_fingerprint("Mozilla/5.0", "1.1.1.1")
        assert h1 == h2

    def test_different_ip_different_hash(self):
        from app.services.anti_abuse import compute_device_fingerprint
        h1 = compute_device_fingerprint("Mozilla/5.0", "1.1.1.1")
        h2 = compute_device_fingerprint("Mozilla/5.0", "2.2.2.2")
        assert h1 != h2

    def test_hash_length_64(self):
        from app.services.anti_abuse import compute_device_fingerprint
        h = compute_device_fingerprint("Mozilla/5.0", "1.1.1.1")
        assert len(h) == 64


class TestAntiAbuseConfig:
    def test_invite_limit_default_3(self):
        from app.core.config import settings
        assert settings.invite_max_per_ip_24h == 3

    def test_sms_mock_mode_default_true(self):
        from app.core.config import settings
        assert settings.sms_mock_mode is True

    def test_circuit_breaker_enabled_default(self):
        from app.core.config import settings
        assert settings.llm_circuit_breaker_enabled is True


class TestSmsCodeConstants:
    def test_length_6(self):
        from app.models.anti_abuse import SMS_CODE_LENGTH
        assert SMS_CODE_LENGTH == 6

    def test_ttl_5_minutes(self):
        from app.models.anti_abuse import SMS_CODE_TTL_MINUTES
        assert SMS_CODE_TTL_MINUTES == 5

    def test_max_attempts_5(self):
        from app.models.anti_abuse import SMS_MAX_ATTEMPTS
        assert SMS_MAX_ATTEMPTS == 5


class TestSmsCodeSend:
    def test_invalid_phone_rejected(self, client, override_db, mock_db):
        resp = client.post("/auth/send-sms-code", json={"phone": "123", "purpose": "register"})
        assert resp.status_code == 400

    def test_invalid_purpose_rejected(self, client, override_db, mock_db):
        resp = client.post("/auth/send-sms-code", json={"phone": "13800138000", "purpose": "hack"})
        assert resp.status_code == 400

    def test_rate_limit_per_minute(self, client, override_db, mock_db):
        from app.models.anti_abuse import SmsVerification

        existing = [MagicMock() for _ in range(3)]
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=existing)))
        mock_db.execute = AsyncMock(return_value=result_mock)

        resp = client.post("/auth/send-sms-code", json={"phone": "13800138000", "purpose": "register"})
        assert resp.status_code == 429


class TestSmsCodeVerify:
    def test_invalid_phone_rejected(self, client, override_db, mock_db):
        resp = client.post("/auth/verify-sms-code", json={"phone": "123", "code": "123456", "purpose": "register"})
        assert resp.status_code == 400

    def test_code_too_short_rejected(self, client, override_db, mock_db):
        resp = client.post("/auth/verify-sms-code", json={"phone": "13800138000", "code": "12345", "purpose": "register"})
        assert resp.status_code == 422


class TestBindPhone:
    def test_invalid_phone_rejected(self, client, override_db, mock_db):
        resp = client.post("/auth/bind-phone", json={"phone": "123", "code": "123456"})
        assert resp.status_code == 400


class TestAuditEnum:
    def test_phone_bound_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.PHONE_BOUND.value == "phone_bound"

    def test_llm_circuit_breaker_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.LLM_CIRCUIT_BREAKER.value == "llm_circuit_breaker"


class TestDeviceFingerprintStatusEndpoint:
    def test_returns_status(self, client, override_db, mock_db):
        from app.models.anti_abuse import DeviceFingerprint

        fp = MagicMock()
        fp.user_id = "u-1"
        fp.invite_count = 1
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=result_mock)

        resp = client.get("/auth/device-fingerprint-status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "fingerprint_hash" in data
        assert "invite_allowed" in data


class TestLLMCircuitBreaker:
    def test_429_when_exceeded(self, client, override_db, mock_db):
        with patch("app.services.anti_abuse.check_llm_circuit_breaker", new=AsyncMock(return_value=(False, 0, 500_000))):
            resp = client.post("/auth/llm-circuit-breaker-check", json={"plan": "starter"})
        assert resp.status_code == 429

    def test_200_when_under_limit(self, client, override_db, mock_db):
        with patch("app.services.anti_abuse.check_llm_circuit_breaker", new=AsyncMock(return_value=(True, 100_000, 500_000))):
            resp = client.post("/auth/llm-circuit-breaker-check", json={"plan": "starter"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["allowed"] is True
        assert data["remaining"] == 100_000
