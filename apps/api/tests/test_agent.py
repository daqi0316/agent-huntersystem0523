"""Agent & Retrieval API tests: auth protection and handler logic."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.jd_generator import JDGenerateRequest
from app.schemas.knowledge import KnowledgeQueryRequest


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# Auth protection — all 5 endpoints
# ──────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("method, path", [
    ("POST", "/api/v1/agent/chat"),
    ("POST", "/api/v1/agent/generate-jd"),
    ("POST", "/api/v1/agent/knowledge-query"),
    ("POST", "/api/v1/retrieval/search"),
    ("POST", "/api/v1/retrieval/embed"),
])
async def test_no_token_returns_401(client, method, path):
    """All agent/retrieval endpoints require authentication."""
    if method == "POST":
        resp = await client.post(path, json={})
    else:
        resp = await client.get(path)
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path", [
    ("POST", "/api/v1/agent/chat"),
    ("POST", "/api/v1/agent/generate-jd"),
    ("POST", "/api/v1/agent/knowledge-query"),
    ("POST", "/api/v1/retrieval/search"),
    ("POST", "/api/v1/retrieval/embed"),
])
async def test_invalid_token_returns_401(client, method, path):
    headers = _auth_headers("totally-invalid-token")
    if method == "POST":
        resp = await client.post(path, json={}, headers=headers)
    else:
        resp = await client.get(path, headers=headers)
    assert resp.status_code == 401


# ──────────────────────────────────────────────
# /agent/chat
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_chat_no_message_returns_422(client):
    """Chat requires a message field."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Chat User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/agent/chat", json={}, headers=_auth_headers(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_agent_chat_success(client):
    """Mock LLM client returns a known reply."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "Hello, I am a mock LLM."
    mock_llm.model = "mock-model"

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Chat User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.agent.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/agent/chat", json={
            "message": "Hello!",
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["reply"] == "Hello, I am a mock LLM."
    assert data["model"] == "mock-model"


@pytest.mark.asyncio
async def test_agent_chat_with_system_prompt(client):
    """Custom system prompt is forwarded to the LLM."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "You are a helpful assistant."
    mock_llm.model = "mock-model"

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Chat User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.agent.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/agent/chat", json={
            "message": "Tell me a joke",
            "system_prompt": "Be concise and funny.",
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    # Verify the system prompt was passed to the LLM
    sent_messages = mock_llm.chat.call_args[0][0]
    assert any(m["role"] == "system" and "funny" in m["content"] for m in sent_messages)


# ──────────────────────────────────────────────
# /agent/generate-jd
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_jd_success(client):
    """Mock JDGeneratorService returns a completed JD."""
    mock_service = AsyncMock()
    mock_service.generate_jd.return_value = {
        "status": "completed",
        "final_output": "# Senior Engineer\n\n## Requirements\n- 5+ years",
        "iterations": [],
        "total_iterations": 1,
        "passed": True,
    }

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "JD User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.agent.JDGeneratorService", return_value=mock_service):
        resp = await client.post("/api/v1/agent/generate-jd", json={
            "title": "Senior Engineer",
            "requirements": "5+ years experience",
            "preferences": "Python preferred",
            "auto_improve": True,
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Senior Engineer" in data["data"]
    assert data["total_iterations"] == 1
    assert data["passed"] is True


@pytest.mark.asyncio
async def test_generate_jd_no_title_returns_422(client):
    """JD generation requires a title."""
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "JD User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/agent/generate-jd", json={
        "requirements": "some skills",
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# /agent/knowledge-query
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_knowledge_query_success(client):
    """Mock KnowledgeService returns an answer."""
    mock_service = AsyncMock()
    mock_service.query.return_value = {
        "answer": "Interview tips: be prepared.",
        "sources": [{"id": "doc-1", "title": "Guide", "content": "...", "score": 0.9}],
    }

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "K User",
    })
    token = reg.json()["access_token"]

    with patch("app.api.agent.KnowledgeService", return_value=mock_service):
        resp = await client.post("/api/v1/agent/knowledge-query", json={
            "query": "interview tips",
            "top_k": 3,
        }, headers=_auth_headers(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "prepared" in data["answer"]
    assert len(data["sources"]) == 1


# ──────────────────────────────────────────────
# /retrieval/search
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_search_success(client):
    """Mock KnowledgeService returns search results."""
    mock_service = AsyncMock()
    mock_service.search.return_value = [
        {"id": "doc-1", "title": "Interview Guide", "content": "Tips...", "score": 0.95},
    ]

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "R User",
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
async def test_retrieval_search_no_query_returns_422(client):
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "R User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/retrieval/search", json={
        "query": "",
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# /retrieval/embed
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_embed_success(client):
    """Mock LLM client returns a fixed embedding vector."""
    mock_llm = AsyncMock()
    mock_llm.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "E User",
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
async def test_retrieval_embed_no_text_returns_422(client):
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "E User",
    })
    token = reg.json()["access_token"]

    resp = await client.post("/api/v1/retrieval/embed", json={
        "text": "",
    }, headers=_auth_headers(token))
    assert resp.status_code == 422
