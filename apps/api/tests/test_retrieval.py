"""Retrieval API tests with mocked dependencies — no real DB needed."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.retrieval import router
    _app.include_router(router, prefix="/api/v1/retrieval")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def override_auth(app):
    from app.core.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


class TestVectorSearch:
    ROUTE = "/api/v1/retrieval/search"

    def test_returns_results(self, client, override_auth):
        mock_svc = AsyncMock()
        mock_svc.search.return_value = [
            {"id": "doc-1", "title": "Interview Guide", "content": "Tips for interviewing...", "score": 0.95},
        ]
        with patch("app.api.retrieval.KnowledgeService", return_value=mock_svc):
            resp = client.post(self.ROUTE, json={"query": "interview guide", "top_k": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Interview Guide"

    def test_empty_results(self, client, override_auth):
        mock_svc = AsyncMock()
        mock_svc.search.return_value = []
        with patch("app.api.retrieval.KnowledgeService", return_value=mock_svc):
            resp = client.post(self.ROUTE, json={"query": "nothing", "top_k": 5})
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_skips_error_items(self, client, override_auth):
        """Items containing an 'error' key are filtered out."""
        mock_svc = AsyncMock()
        mock_svc.search.return_value = [
            {"id": "doc-1", "title": "Good Doc", "content": "Ok", "score": 0.9},
            {"error": "rate limit", "content": "failed"},
        ]
        with patch("app.api.retrieval.KnowledgeService", return_value=mock_svc):
            resp = client.post(self.ROUTE, json={"query": "test", "top_k": 5})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1
        assert resp.json()["results"][0]["title"] == "Good Doc"

    def test_invalid_query_returns_422(self, client, override_auth):
        resp = client.post(self.ROUTE, json={"query": ""})
        assert resp.status_code == 422

    def test_missing_query_returns_422(self, client, override_auth):
        resp = client.post(self.ROUTE, json={})
        assert resp.status_code == 422


class TestEmbedText:
    ROUTE = "/api/v1/retrieval/embed"

    def test_returns_embedding(self, client, override_auth):
        mock_llm = AsyncMock()
        mock_llm.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
        with patch("app.api.retrieval.get_llm_client", return_value=mock_llm):
            resp = client.post(self.ROUTE, json={"text": "Embed this text"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["embedding"]) == 5
        assert data["dimension"] == 5

    def test_empty_text_returns_422(self, client, override_auth):
        resp = client.post(self.ROUTE, json={"text": ""})
        assert resp.status_code == 422
