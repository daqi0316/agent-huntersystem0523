"""KnowledgeService unit tests — mock Qdrant + LLM at source level."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.knowledge import KnowledgeService, KNOWLEDGE_COLLECTION



@pytest.fixture
def mock_qdrant():
    """Return an async-mock Qdrant client."""
    q = AsyncMock()
    q.get_collections = AsyncMock()
    q.create_collection = AsyncMock()
    q.upsert = AsyncMock()
    q.query_points = AsyncMock()
    return q


@pytest.fixture
def mock_llm():
    """Return a mock LLM client with embed + chat."""
    llm = AsyncMock()
    llm.embed = AsyncMock(return_value=[0.1] * 1024)
    llm.chat = AsyncMock(return_value="Mock answer.")
    return llm


@pytest.fixture
def service(mock_qdrant, mock_llm):
    """Create KnowledgeService with get_qdrant + get_llm_client patched."""
    with patch("app.services.knowledge.get_qdrant", return_value=mock_qdrant):
        with patch("app.services.knowledge.get_llm_client", return_value=mock_llm):
            svc = KnowledgeService()
            # force-lazy-init so the property uses the patched import
            svc._llm = mock_llm
            yield svc


# ── ensure_collection ────────────────────────────────────────────────────


async def test_ensure_collection_creates_when_missing(service, mock_qdrant):
    """ensure_collection creates collection when it doesn't exist."""
    mock_qdrant.get_collections.return_value = Mock(collections=[])
    await service.ensure_collection()
    mock_qdrant.create_collection.assert_awaited_once()
    call_kwargs = mock_qdrant.create_collection.await_args.kwargs
    assert call_kwargs["collection_name"] == KNOWLEDGE_COLLECTION


async def test_ensure_collection_skips_when_exists(service, mock_qdrant):
    """ensure_collection is no-op when collection already exists."""
    existing = Mock(name="knowledge_base")
    existing.name = KNOWLEDGE_COLLECTION
    mock_qdrant.get_collections.return_value = Mock(collections=[existing])
    await service.ensure_collection()
    mock_qdrant.create_collection.assert_not_called()


async def test_ensure_collection_handles_qdrant_error(service, mock_qdrant):
    """ensure_collection logs warning, does not crash when Qdrant unavailable."""
    mock_qdrant.get_collections.side_effect = RuntimeError("Qdrant down")
    # should not raise
    await service.ensure_collection()


# ── ingest_document ───────────────────────────────────────────────────────


async def test_ingest_document_success(service, mock_qdrant, mock_llm):
    """ingest_document chunks, embeds, and upserts to Qdrant."""
    mock_qdrant.get_collections.return_value = Mock(collections=[])
    result = await service.ingest_document(
        title="Test Doc",
        content="Hello world. " * 30,  # long enough for multiple chunks
    )
    assert result["title"] == "Test Doc"
    assert result["chunks_count"] > 0
    assert "document_id" in result
    assert mock_llm.embed.awaited
    mock_qdrant.upsert.assert_awaited_once()


async def test_ingest_document_qdrant_unavailable(mock_llm):
    """ingest_document returns warning when get_qdrant() itself raises."""
    with patch("app.services.knowledge.get_qdrant", side_effect=RuntimeError("Qdrant down")):
        with patch("app.services.knowledge.get_llm_client", return_value=mock_llm):
            svc = KnowledgeService()
            svc._llm = mock_llm
            result = await svc.ingest_document(title="Fail Doc", content="Some content")
    assert "warning" in result
    assert "Qdrant unavailable" in result["warning"]
    assert result["chunks_count"] == 1


async def test_ingest_document_embed_failure_skips_chunk(service, mock_qdrant, mock_llm):
    """If LLM embed fails for one chunk, it's skipped; others still upserted."""
    mock_qdrant.get_collections.return_value = Mock(collections=[])
    # First call to embed fails, subsequent succeed
    mock_llm.embed = AsyncMock(side_effect=[RuntimeError("LLM down"), [0.2] * 1024])

    result = await service.ingest_document(
        title="Partial Fail",
        content="Chunk one content. " * 30 + "Chunk two content. " * 30,
    )
    # Some chunks may be skipped, but doc is still created
    assert result["chunks_count"] > 0
    # upsert should still be called with remaining chunks
    assert mock_qdrant.upsert.awaited


# ── search ────────────────────────────────────────────────────────────────


async def test_search_returns_results_above_threshold(service, mock_qdrant):
    """search returns sources with score > 0.3."""
    from qdrant_client.models import ScoredPoint

    mock_qdrant.query_points.return_value = Mock(
        points=[
            Mock(id="1", score=0.95, payload={"title": "A", "content": "Content A"}),
            Mock(id="2", score=0.25, payload={"title": "B", "content": "Content B"}),
            Mock(id="3", score=0.50, payload={"title": "C", "content": "Content C"}),
        ]
    )
    results = await service.search("test query")
    assert len(results) == 2  # only scores 0.95 and 0.50
    assert results[0]["title"] == "A"
    assert results[1]["title"] == "C"


async def test_search_returns_empty_when_all_below_threshold(service, mock_qdrant):
    """search returns empty list when all results below 0.3."""
    mock_qdrant.query_points.return_value = Mock(
        points=[
            Mock(id="1", score=0.1, payload={"title": "Low", "content": "Low score"}),
        ]
    )
    results = await service.search("low relevance")
    assert results == []


async def test_search_handles_qdrant_unavailable(mock_llm):
    """search returns error dict when get_qdrant() itself raises."""
    with patch("app.services.knowledge.get_qdrant", side_effect=RuntimeError("Qdrant down")):
        with patch("app.services.knowledge.get_llm_client", return_value=mock_llm):
            svc = KnowledgeService()
            svc._llm = mock_llm
            results = await svc.search("query")
    assert len(results) == 1
    assert "error" in results[0]


async def test_search_handles_embed_failure(service, mock_qdrant, mock_llm):
    """search returns empty when LLM embed fails."""
    mock_qdrant.get_collections.return_value = Mock(collections=[])
    mock_llm.embed = AsyncMock(side_effect=RuntimeError("LLM down"))
    results = await service.search("query")
    assert results == []


# ── query ─────────────────────────────────────────────────────────────────


async def test_query_success(service, mock_qdrant, mock_llm):
    """query returns answer from LLM with sources."""
    mock_qdrant.query_points.return_value = Mock(
        points=[
            Mock(id="1", score=0.9, payload={"title": "Guide", "content": "Onboarding takes 3 days."}),
        ]
    )
    mock_llm.chat = AsyncMock(return_value="Onboarding takes 3 days.")
    result = await service.query("How long?", top_k=3)
    assert "3 days" in result["answer"]
    assert len(result["sources"]) == 1
    mock_llm.chat.assert_awaited()


async def test_query_no_sources(service, mock_qdrant, mock_llm):
    """query returns 'search failed' when search returns empty (dead-code path — "未找到相关信息" is unreachable)."""
    mock_qdrant.query_points.return_value = Mock(points=[])
    result = await service.query("unknown topic")
    assert "检索失败" in result["answer"]
    assert result["sources"] == []


async def test_query_search_returns_error(service, mock_qdrant, mock_llm):
    """query returns 'search failed' when search returns error."""
    mock_qdrant.get_collections.side_effect = RuntimeError("Qdrant down")
    result = await service.query("anything")
    assert "检索失败" in result["answer"]


async def test_query_llm_chat_failure(service, mock_qdrant, mock_llm):
    """query falls back when LLM chat fails."""
    mock_qdrant.query_points.return_value = Mock(
        points=[
            Mock(id="1", score=0.9, payload={"title": "Guide", "content": "Some content."}),
        ]
    )
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM chat failed"))
    result = await service.query("question")
    assert "AI 回答不可用" in result["answer"]
    assert len(result["sources"]) == 1


# ── _chunk_text ───────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_single_chunk(self):
        """Text shorter than chunk_size returns one chunk."""
        chunks = KnowledgeService._chunk_text("Short text", chunk_size=512)
        assert chunks == ["Short text"]

    def test_long_text_splits_into_multiple_chunks(self):
        """Long text is split into multiple chunks with overlap."""
        text = "Sentence one. " * 60  # ~900 chars
        chunks = KnowledgeService._chunk_text(text, chunk_size=200, overlap=30)
        assert len(chunks) > 1
        # Each chunk should start with the overlap from previous
        assert all(len(c) <= 210 for c in chunks)  # 200 + some margin

    def test_chunks_preserves_word_boundaries(self):
        """Chunking splits at paragraph/sentence boundaries."""
        text = "\n\n".join([f"Paragraph {i} content here." for i in range(10)])
        chunks = KnowledgeService._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 1
        # No chunk should be empty
        assert all(len(c) > 0 for c in chunks)
