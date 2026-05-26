from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.knowledge import KnowledgeService


class TestKnowledge:
    def test_llm_lazy_init(self):
        svc = KnowledgeService()
        assert svc._llm is None
        _ = svc.llm
        assert svc._llm is not None

    def test_chunk_text_at_end_when_no_boundary(self):
        text = "abcde12345" * 60  # 600 chars
        chunks = KnowledgeService._chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1
        assert all(isinstance(c, str) and len(c) > 0 for c in chunks)
        assert len(chunks[0]) == 100

    def test_chunk_text_with_paragraph_boundary(self):
        text = "Short paragraph.\n\nAnother paragraph.\n\nYet another.\n\n" * 10
        chunks = KnowledgeService._chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) >= 1
        assert all(len(c) > 0 for c in chunks)
        assert len(chunks[0]) <= 100 + 10  # chunk_size + overlap max

    def test_chunk_text_smaller_than_chunk_size(self):
        text = "Short text that fits in one chunk."
        chunks = KnowledgeService._chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_zero_overlap(self):
        text = "word " * 200
        chunks = KnowledgeService._chunk_text(text.strip(), chunk_size=50, overlap=0)
        assert len(chunks) > 1
        assert all(len(c) > 0 for c in chunks)


@pytest.mark.asyncio
async def test_ingest_document_success():
    from unittest.mock import MagicMock

    svc = KnowledgeService()
    mock_llm = AsyncMock()
    mock_llm.embed.return_value = [0.1] * 1024
    svc._llm = mock_llm

    collections_resp = MagicMock()
    collections_resp.collections = []
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = collections_resp

    with patch("app.services.knowledge.get_qdrant", return_value=mock_qdrant):
        result = await svc.ingest_document("Test Doc", "Hello world. " * 50)

    assert result["title"] == "Test Doc"
    assert result["chunks_count"] > 0


@pytest.mark.asyncio
async def test_ingest_document_qdrant_unavailable():
    from unittest.mock import MagicMock

    svc = KnowledgeService()
    mock_llm = AsyncMock()
    svc._llm = mock_llm

    with patch("app.services.knowledge.get_qdrant", side_effect=ConnectionError("No Qdrant")):
        result = await svc.ingest_document("Test Doc", "Hello world.")

    assert "warning" in result
    assert "Qdrant unavailable" in result["warning"]


@pytest.mark.asyncio
async def test_ensure_collection_exception():
    svc = KnowledgeService()
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.side_effect = Exception("Qdrant down")

    with patch("app.services.knowledge.get_qdrant", return_value=mock_qdrant):
        await svc.ensure_collection()  # should not raise


@pytest.mark.asyncio
async def test_search_qdrant_unavailable():
    svc = KnowledgeService()
    with patch("app.services.knowledge.get_qdrant", side_effect=ConnectionError("No Qdrant")):
        results = await svc.search("test query")
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_search_llm_embed_failure():
    from unittest.mock import MagicMock

    svc = KnowledgeService()
    mock_llm = AsyncMock()
    mock_llm.embed.side_effect = Exception("LLM down")
    svc._llm = mock_llm

    with patch("app.services.knowledge.get_qdrant") as mock_get:
        mock_qdrant = AsyncMock()
        collections_resp = MagicMock()
        collections_resp.collections = []
        mock_qdrant.get_collections.return_value = collections_resp
        mock_get.return_value = mock_qdrant

        results = await svc.search("test")
    assert results == []


@pytest.mark.asyncio
async def test_query_search_failure():
    svc = KnowledgeService()
    with patch.object(svc, "search", return_value=[]):
        result = await svc.query("something random")
    assert "失败" in result["answer"]
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_query_llm_chat_failure():
    svc = KnowledgeService()
    mock_search_result = [
        {"id": "doc-1", "title": "Doc", "content": "content", "score": 0.95},
    ]
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = Exception("LLM chat down")
    svc._llm = mock_llm

    with patch.object(svc, "search", return_value=mock_search_result):
        result = await svc.query("test")
    assert "不可用" in result["answer"]
    assert len(result["sources"]) == 1


@pytest.mark.asyncio
async def test_ingest_embed_failure_partial():
    from unittest.mock import MagicMock

    svc = KnowledgeService()
    mock_llm = AsyncMock()
    mock_llm.embed.side_effect = [Exception("LLM fail"), [0.1] * 1024]
    svc._llm = mock_llm

    collections_resp = MagicMock()
    collections_resp.collections = []
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = collections_resp

    with patch("app.services.knowledge.get_qdrant", return_value=mock_qdrant):
        result = await svc.ingest_document("Partial Fail", "AAA BBB CCC DDD" * 200)
    assert result["chunks_count"] > 0


@pytest.mark.asyncio
async def test_query_success():
    svc = KnowledgeService()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "This is the answer from LLM."
    svc._llm = mock_llm

    sources = [
        {"id": "doc-1", "title": "Doc 1", "content": "content here", "score": 0.95},
    ]
    with patch.object(svc, "search", return_value=sources):
        result = await svc.query("test question")
    assert result["answer"] == "This is the answer from LLM."
    assert len(result["sources"]) == 1
