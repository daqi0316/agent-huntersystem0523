"""Candidate CRUD API tests with mocked dependencies — no real DB needed."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.candidates import router
    _app.include_router(router, prefix="/api/v1/candidates")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_auth(app):
    """Override auth + org_scoped_db to return fixed context and a mock db."""
    from app.core.dependencies import get_current_user_id
    from app.core.org_context import OrgContext, org_scoped_db
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    mock_db = AsyncMock()
    async def _fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="user-1", role="hr"), mock_db
    app.dependency_overrides[org_scoped_db] = _fake_org_scoped_db
    yield
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(org_scoped_db, None)


def _fake_candidate(**kwargs):
    """Return a dict that looks like a CandidateRead (Pydantic-friendly)."""
    return {
        "id": kwargs.get("id", "cand-1"),
        "name": kwargs.get("name", "张三"),
        "email": kwargs.get("email", "test@test.com"),
        "phone": kwargs.get("phone", "13800138001"),
        "skills": kwargs.get("skills", ["Python"]),
        "status": kwargs.get("status", "active"),
        "experience_years": kwargs.get("experience_years", 3),
        "summary": kwargs.get("summary", ""),
        "current_title": kwargs.get("current_title", ""),
        "current_company": kwargs.get("current_company", ""),
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


class TestListCandidates:
    ROUTE = "/api/v1/candidates"

    def test_shows_items(self, client, override_auth):
        mock_cand = _fake_candidate()
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.list.return_value = ([mock_cand], 1)
            MockSvc.return_value = svc
            resp = client.get(self.ROUTE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "张三"

    def test_uses_query_params(self, client, override_auth):
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.list.return_value = ([], 0)
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}?skip=10&limit=5&search=Python&status=active")
        assert resp.status_code == 200
        svc.list.assert_called_once_with(skip=10, limit=5, search="Python", status="active")


class TestCreateCandidate:
    ROUTE = "/api/v1/candidates"

    def test_creates_candidate(self, client, override_auth):
        mock_cand = _fake_candidate(name="New User")
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.create.return_value = mock_cand
            MockSvc.return_value = svc
            resp = client.post(self.ROUTE, json={
                "name": "New User",
                "email": "new@test.com",
                "status": "active",
                "skills": ["Go"],
                "experience_years": 5,
            })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "New User"
        svc.create.assert_called_once()


class TestGetCandidate:
    ROUTE = "/api/v1/candidates"

    def test_found(self, client, override_auth):
        mock_cand = _fake_candidate(id="cand-42", name="李四")
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.get_by_id.return_value = mock_cand
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}/cand-42")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "李四"

    def test_not_found(self, client, override_auth):
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.get_by_id.return_value = None
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}/nonexistent")
        assert resp.status_code == 404


class TestUpdateCandidate:
    ROUTE = "/api/v1/candidates"

    def test_updates(self, client, override_auth):
        mock_cand = _fake_candidate(name="Updated Name", status="archived")
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.update.return_value = mock_cand
            MockSvc.return_value = svc
            resp = client.put(f"{self.ROUTE}/cand-1", json={"name": "Updated Name", "status": "archived"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Updated Name"
        assert data["status"] == "archived"

    def test_not_found(self, client, override_auth):
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.update.return_value = None
            MockSvc.return_value = svc
            resp = client.put(f"{self.ROUTE}/nonexistent", json={"name": "Ghost"})
        assert resp.status_code == 404


class TestDeleteCandidate:
    ROUTE = "/api/v1/candidates"

    def test_deletes(self, client, override_auth):
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.delete.return_value = True
            MockSvc.return_value = svc
            resp = client.delete(f"{self.ROUTE}/cand-1")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_not_found(self, client, override_auth):
        with patch("app.api.candidates.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.delete.return_value = False
            MockSvc.return_value = svc
            resp = client.delete(f"{self.ROUTE}/nonexistent")
        assert resp.status_code == 404
