"""Retrieval API tests: vector search & text embedding."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_vector_search_success(client):
    """Mock KnowledgeService returns search results."""
    mock_service = AsyncMock()
    mock_service.search.return_value = [
        {"id": "doc-1", "title": "Interview Guide", "content": "Tips for interviewing...", "score": 0.95},
    ]

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Retrieval User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.retrieval.KnowledgeService", return_value=mock_service):
        resp = await client.post("/api/v1/retrieval/search", json={
            "query": "interview guide",
            "top_k": 5,
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Interview Guide"


@pytest.mark.asyncio
async def test_vector_search_no_query_returns_422(client):
    """Empty search query returns 422."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Retrieval User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/retrieval/search", json={
        "query": "",
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_embed_success(client):
    """Mock LLM client returns a fixed embedding vector."""
    mock_llm = AsyncMock()
    mock_llm.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Embed User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.retrieval.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/retrieval/embed", json={
            "text": "Embed this text",
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["embedding"]) == 5
    assert data["dimension"] == 5


@pytest.mark.asyncio
async def test_vector_search_no_results(client):
    mock_service = AsyncMock()
    mock_service.search.return_value = []

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Retrieval User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.retrieval.KnowledgeService", return_value=mock_service):
        resp = await client.post("/api/v1/retrieval/search", json={
            "query": "nothing matches this",
            "top_k": 5,
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_embed_empty_text_returns_422(client):
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Embed User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/retrieval/embed", json={
        "text": "",
    }, headers=_auth_headers(token))
    assert resp.status_code == 422
