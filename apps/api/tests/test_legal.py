"""P5-9: 法务协议测试 — 4 endpoint (清单/接受/状态/历史)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.legal import router
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


def _mock_acc(agreement_type: str, version: str = "v1.0", acc_id: str = "acc-1"):
    acc = MagicMock()
    acc.id = acc_id
    acc.agreement_type = MagicMock()
    acc.agreement_type.value = agreement_type
    acc.version = version
    acc.accepted_at = MagicMock()
    acc.accepted_at.isoformat.return_value = "2026-06-06T00:00:00+00:00"
    acc.ip_address = "192.168.1.1"
    return acc


class TestRequiredAgreements:
    def test_default_returns_tos_and_pp(self, client):
        r = client.get("/agreements")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        types = {a["type"] for a in data}
        assert "terms_of_service" in types
        assert "privacy_policy" in types
        assert "data_processing_agreement" not in types

    def test_cross_border_includes_dpa(self, client):
        r = client.get("/agreements?cross_border=true&enterprise=true")
        assert r.status_code == 200
        types = {a["type"] for a in r.json()["data"]}
        assert "data_processing_agreement" in types


class TestAcceptFlow:
    def test_accept_tos(self, client, override_db, mock_db):
        acc = _mock_acc("terms_of_service")
        with patch("app.api.legal.record_acceptance", new=AsyncMock(return_value=acc)):
            r = client.post(
                "/accept",
                headers={"X-Forwarded-For": "192.168.1.1"},
                json={"agreement_type": "terms_of_service", "confirm": True},
            )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["agreement_type"] == "terms_of_service"
        assert body["version"] == "v1.0"

    def test_accept_without_confirm_400(self, client, override_db):
        r = client.post(
            "/accept",
            json={"agreement_type": "privacy_policy", "confirm": False},
        )
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower()

    def test_accept_idempotent(self, client, override_db):
        acc1 = _mock_acc("privacy_policy", acc_id="acc-1")
        acc2 = _mock_acc("privacy_policy", acc_id="acc-1")
        with patch("app.api.legal.record_acceptance", new=AsyncMock(side_effect=[acc1, acc2])):
            r1 = client.post("/accept", json={"agreement_type": "privacy_policy", "confirm": True})
            r2 = client.post("/accept", json={"agreement_type": "privacy_policy", "confirm": True})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["data"]["id"] == r2.json()["data"]["id"]


class TestStatus:
    def test_status_all_accepted(self, client, override_db):
        with patch(
            "app.api.legal.has_required_acceptances",
            new=AsyncMock(return_value={
                "all_accepted": True,
                "accepted": ["terms_of_service", "privacy_policy"],
                "missing": [],
                "required": ["terms_of_service", "privacy_policy"],
            }),
        ):
            r = client.get("/status")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["all_accepted"] is True
        assert body["missing"] == []

    def test_status_missing_one(self, client, override_db):
        with patch(
            "app.api.legal.has_required_acceptances",
            new=AsyncMock(return_value={
                "all_accepted": False,
                "accepted": ["terms_of_service"],
                "missing": ["privacy_policy"],
                "required": ["terms_of_service", "privacy_policy"],
            }),
        ):
            r = client.get("/status")
        body = r.json()["data"]
        assert body["all_accepted"] is False
        assert "privacy_policy" in body["missing"]


class TestAcceptanceHistory:
    def test_list_returns_records(self, client, override_db):
        acc = _mock_acc("terms_of_service")
        with patch("app.api.legal.get_user_acceptances", new=AsyncMock(return_value=[acc])):
            r = client.get("/acceptances")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["agreement_type"] == "terms_of_service"
