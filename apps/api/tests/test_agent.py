"""Agent API tests with mocked dependencies — no real DB needed."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.agent import router
    _app.include_router(router, prefix="/api/v1/agent")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def override_auth(app):
    """Override auth deps for /chat (uses get_current_user) and /generate-jd, /knowledge-query (use get_current_user_id)."""
    from app.core.dependencies import get_current_user_id, get_current_user
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1", "role": "user"}
    yield
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────
# Auth protection — all endpoints
# ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/v1/agent/chat",
    "/api/v1/agent/generate-jd",
    "/api/v1/agent/knowledge-query",
])
def test_no_token_returns_401(client, path):
    resp = client.post(path, json={})
    assert resp.status_code == 401


# ──────────────────────────────────────────────
# /agent/chat
# ──────────────────────────────────────────────

class TestAgentChat:
    ROUTE = "/api/v1/agent/chat"

    def test_missing_message_returns_422(self, client, override_auth):
        resp = client.post(self.ROUTE, json={})
        assert resp.status_code == 422

    def test_chat_success(self, client, override_auth):
        mock_result = {
            "reply": "Hello, I am a mock LLM.",
            "model": "mock-model",
            "tool_calls": [],
        }
        with patch("app.api.agent.chat_with_tools", new=AsyncMock(return_value=mock_result)):
            resp = client.post(self.ROUTE, json={"message": "Hello!"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["reply"] == "Hello, I am a mock LLM."
        assert data["model"] == "mock-model"

    def test_with_system_prompt(self, client, override_auth):
        mock_result = {
            "reply": "Why did the chicken...",
            "model": "mock-model",
            "tool_calls": [],
        }
        with patch("app.api.agent.chat_with_tools", new=AsyncMock(return_value=mock_result)):
            resp = client.post(self.ROUTE, json={
                "message": "Tell me a joke",
                "system_prompt": "Be concise and funny.",
            })
        assert resp.status_code == 200


# ──────────────────────────────────────────────
# /agent/generate-jd
# ──────────────────────────────────────────────

class TestGenerateJD:
    ROUTE = "/api/v1/agent/generate-jd"

    def test_success(self, client, override_auth):
        mock_service = AsyncMock()
        mock_service.generate_jd.return_value = {
            "status": "completed",
            "final_output": "# Senior Engineer\n\n## Requirements\n- 5+ years",
            "iterations": [],
            "total_iterations": 1,
            "passed": True,
        }
        with patch("app.api.agent.JDGeneratorService", return_value=mock_service):
            resp = client.post(self.ROUTE, json={
                "title": "Senior Engineer",
                "requirements": "5+ years experience",
                "preferences": "Python preferred",
                "auto_improve": True,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Senior Engineer" in data["data"]
        assert data["total_iterations"] == 1
        assert data["passed"] is True

    def test_no_title_returns_422(self, client, override_auth):
        resp = client.post(self.ROUTE, json={"requirements": "some skills"})
        assert resp.status_code == 422


# ──────────────────────────────────────────────
# /agent/knowledge-query
# ──────────────────────────────────────────────

class TestKnowledgeQuery:
    ROUTE = "/api/v1/agent/knowledge-query"

    def test_success(self, client, override_auth):
        mock_service = AsyncMock()
        mock_service.query.return_value = {
            "answer": "Interview tips: be prepared.",
            "sources": [{"id": "doc-1", "title": "Guide", "content": "...", "score": 0.9}],
        }
        with patch("app.api.agent.KnowledgeService", return_value=mock_service):
            resp = client.post(self.ROUTE, json={"query": "interview tips", "top_k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "prepared" in data["answer"]
        assert len(data["sources"]) == 1
