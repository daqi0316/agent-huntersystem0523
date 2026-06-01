"""Job CRUD API tests with mocked dependencies — no real DB needed."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.jobs import router
    _app.include_router(router, prefix="/api/v1/jobs")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_auth(app):
    from app.core.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def _fake_job(**kwargs):
    return {
        "id": kwargs.get("id", "job-1"),
        "title": kwargs.get("title", "后端工程师"),
        "department": kwargs.get("department", "技术部"),
        "description": kwargs.get("description", ""),
        "requirements": kwargs.get("requirements", ""),
        "location": kwargs.get("location", "北京"),
        "salary_range": kwargs.get("salary_range", "30k-50k"),
        "status": kwargs.get("status", "active"),
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


class TestListJobs:
    ROUTE = "/api/v1/jobs"

    def test_shows_items(self, client, override_auth):
        mock_job = _fake_job()
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.list.return_value = ([mock_job], 1)
            MockSvc.return_value = svc
            resp = client.get(self.ROUTE)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "后端工程师"

    def test_uses_query_params(self, client, override_auth):
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.list.return_value = ([], 0)
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}?skip=10&limit=5&search=Python&status=active")
        assert resp.status_code == 200
        svc.list.assert_called_once_with(skip=10, limit=5, search="Python", status="active")


class TestCreateJob:
    ROUTE = "/api/v1/jobs"

    def test_creates_job(self, client, override_auth):
        mock_job = _fake_job(title="高级后端工程师")
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.create.return_value = mock_job
            MockSvc.return_value = svc
            resp = client.post(self.ROUTE, json={
                "title": "高级后端工程师",
                "department": "技术部",
                "description": "后端开发",
                "requirements": "5年Python",
                "location": "北京",
                "salary_range": "30k-50k",
                "status": "active",
            })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "高级后端工程师"
        svc.create.assert_called_once()


class TestGetJob:
    ROUTE = "/api/v1/jobs"

    def test_found(self, client, override_auth):
        mock_job = _fake_job(id="job-42", title="前端工程师")
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.get_by_id.return_value = mock_job
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}/job-42")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "前端工程师"

    def test_not_found(self, client, override_auth):
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.get_by_id.return_value = None
            MockSvc.return_value = svc
            resp = client.get(f"{self.ROUTE}/nonexistent")
        assert resp.status_code == 404


class TestUpdateJob:
    ROUTE = "/api/v1/jobs"

    def test_updates(self, client, override_auth):
        mock_job = _fake_job(title="测试职位 Updated", salary_range="40k-60k")
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.update.return_value = mock_job
            MockSvc.return_value = svc
            resp = client.put(f"{self.ROUTE}/job-1", json={"title": "测试职位 Updated", "salary_range": "40k-60k"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "测试职位 Updated"

    def test_not_found(self, client, override_auth):
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.update.return_value = None
            MockSvc.return_value = svc
            resp = client.put(f"{self.ROUTE}/nonexistent", json={"title": "Ghost"})
        assert resp.status_code == 404


class TestDeleteJob:
    ROUTE = "/api/v1/jobs"

    def test_deletes(self, client, override_auth):
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.delete.return_value = True
            MockSvc.return_value = svc
            resp = client.delete(f"{self.ROUTE}/job-1")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_not_found(self, client, override_auth):
        with patch("app.api.jobs.JobService") as MockSvc:
            svc = AsyncMock()
            svc.delete.return_value = False
            MockSvc.return_value = svc
            resp = client.delete(f"{self.ROUTE}/nonexistent")
        assert resp.status_code == 404
