"""Knowledge Base API tests: document ingest, RAG query, search."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ingest_document_success(client):
    """Mock ingest_document returns document ID and chunk count."""
    mock_service = AsyncMock()
    mock_service.ingest_document.return_value = {
        "document_id": "doc-abc-123",
        "title": "Onboarding Guide",
        "chunks_count": 3,
    }

    with patch("app.api.knowledge.service", mock_service):
        resp = await client.post("/api/v1/knowledge/documents/ingest", json={
            "title": "Onboarding Guide",
            "content": "Welcome to the company. Here are the steps...",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["document_id"] == "doc-abc-123"
    assert data["chunks_count"] == 3


@pytest.mark.asyncio
async def test_ingest_no_title_returns_422(client):
    """Document upload without title returns 422."""
    resp = await client.post("/api/v1/knowledge/documents/ingest", json={
        "content": "Some content without a title",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_knowledge_query_success(client):
    """Mock knowledge query returns answer with sources."""
    mock_service = AsyncMock()
    mock_service.query.return_value = {
        "answer": "The onboarding process takes 3 days.",
        "sources": [
            {"id": "doc-1", "title": "Onboarding Guide", "content": "...", "score": 0.92},
        ],
    }

    with patch("app.api.knowledge.service", mock_service):
        resp = await client.post("/api/v1/knowledge/query", json={
            "query": "How long does onboarding take?",
            "top_k": 3,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "3 days" in data["answer"]
    assert len(data["sources"]) == 1


@pytest.mark.asyncio
async def test_knowledge_search_success(client):
    """Mock knowledge search returns relevant sources."""
    mock_service = AsyncMock()
    mock_service.search.return_value = [
        {"id": "doc-2", "title": "Interview Tips", "content": "Prepare well...", "score": 0.88},
    ]

    with patch("app.api.knowledge.service", mock_service):
        resp = await client.post("/api/v1/knowledge/search", json={
            "query": "interview tips",
            "top_k": 5,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["sources"]) == 1
    assert data["sources"][0]["title"] == "Interview Tips"
