"""SummaryService unit tests — mock DB, LLM, and Qdrant at source level."""

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.services.summary_service import SummaryService as SUT


# ── Fixtures ──


@pytest.fixture
def mock_db():
    """Return an async-mock DB session with properly chained sync sub-methods.

    Each call to db.execute() returns a MagicMock that mimics SQLAlchemy's
    async Result, where .scalar_one_or_none() / .scalars() / .scalar() are
    all sync (not async) methods.
    """
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=Mock(return_value=None),
            scalars=Mock(return_value=Mock(all=Mock(return_value=[]))),
            scalar=Mock(return_value=0),
        )
    )
    db.commit = AsyncMock()
    db.add = Mock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def mock_llm():
    """Return a mock LLM client with embed + chat."""
    llm = AsyncMock()
    llm.embed = AsyncMock(return_value=[0.1] * 1024)
    llm.chat = AsyncMock(return_value="Mock summary text.")
    return llm


@pytest.fixture
def mock_qdrant():
    """Return a mock QdrantService."""
    qdrant = AsyncMock()
    qdrant.ensure_collection = AsyncMock()
    qdrant.upsert = AsyncMock()
    qdrant.search = AsyncMock(return_value=[
        {"id": "sess-1", "score": 0.85, "user_id": "user-1", "session_id": "sess-1", "summary": "Reviewed candidate A"},
        {"id": "sess-2", "score": 0.72, "user_id": "user-1", "session_id": "sess-2", "summary": "Scheduled interview for B"},
    ])
    qdrant.delete = AsyncMock()
    qdrant.scroll_by_filter = AsyncMock(return_value=[])
    return qdrant


@pytest.fixture
def service(mock_db, mock_llm, mock_qdrant):
    """Create SummaryService with mocked dependencies."""
    return SUT(db=mock_db, llm=mock_llm, qdrant=mock_qdrant)


# ── generate ──


async def test_generate_skips_few_messages(service):
    """generate returns None when fewer than MIN_MESSAGES_FOR_SUMMARY messages."""
    result = await service.generate("user-1", "sess-1", [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ])
    assert result is None


async def test_generate_success(service, mock_db, mock_llm, mock_qdrant):
    """generate stores summary in both PG and Qdrant."""
    mock_db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=Mock(return_value=None)
        )
    )
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await service.generate("user-1", "sess-1", messages)

    assert result == "Mock summary text."
    mock_llm.chat.assert_awaited_once()
    mock_llm.embed.assert_awaited_once_with("Mock summary text.")
    mock_qdrant.ensure_collection.assert_awaited_once_with(1024)
    mock_qdrant.upsert.assert_awaited_once()
    assert mock_db.add.called  # PG upsert


async def test_generate_llm_unavailable(service, mock_llm):
    """generate returns None when LLM returns unavailable."""
    mock_llm.chat = AsyncMock(return_value="[LLM unavailable]")
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await service.generate("user-1", "sess-1", messages)
    assert result is None


async def test_generate_embed_fallback(service, mock_llm, mock_qdrant, mock_db):
    """generate still saves to PG when embedding fails."""
    mock_llm.embed = AsyncMock(return_value=[])
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await service.generate("user-1", "sess-1", messages)
    assert result == "Mock summary text."
    mock_qdrant.upsert.assert_not_called()
    assert mock_db.add.called


# ── get_relevant ──


async def test_call_summary_llm_empty_content(service, mock_llm):
    """_call_summary_llm returns empty string when messages have no content."""
    messages = [{"role": "user", "content": None}, {"role": "assistant", "content": None}]
    result = await service._call_summary_llm(messages)
    assert result == ""


async def test_generate_updates_existing_record(service, mock_db, mock_llm, mock_qdrant):
    """generate with existing PG record hits the update path in _upsert_pg."""
    existing = Mock()
    existing.summary = "old"
    existing.updated_at = None
    mock_db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=Mock(return_value=existing)
        )
    )
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await service.generate("user-1", "sess-1", messages)
    assert result == "Mock summary text."
    assert existing.summary == "Mock summary text."
    assert existing.updated_at is not None
    mock_db.commit.assert_awaited()


async def test_injection_context_drops_when_over_budget(service, mock_qdrant):
    """get_injection_context returns empty when all memories exceed token budget."""
    mock_qdrant.search.return_value = [
        {"session_id": "sess-1", "summary": "x" * 500, "score": 0.7, "user_id": "user-1"},
    ]
    context = await service.get_injection_context("user-1", "query", max_tokens=1)
    assert context == ""


async def test_get_relevant_empty_query(service):
    """get_relevant returns empty list for empty query."""
    result = await service.get_relevant("user-1", "")
    assert result == []


async def test_get_relevant_success(service, mock_llm):
    """get_relevant returns filtered results for a valid query."""
    mock_llm.embed = AsyncMock(return_value=[0.2] * 1024)
    result = await service.get_relevant("user-1", "Tell me about candidates", top_k=3)
    assert len(result) == 2
    assert result[0]["user_id"] == "user-1"


async def test_get_relevant_embed_failure(service, mock_llm):
    """get_relevant returns empty list when embedding fails."""
    mock_llm.embed = AsyncMock(return_value=[])
    result = await service.get_relevant("user-1", "some query")
    assert result == []


# ── get_injection_context ──


async def test_injection_context_produces_snippet(service):
    """get_injection_context returns non-empty string with memories."""
    context = await service.get_injection_context("user-1", "candidates")
    assert "【历史记忆】" in context
    assert "Reviewed candidate A" in context


async def test_injection_context_empty_when_no_memories(service, mock_qdrant):
    """get_injection_context returns empty string when no memories found."""
    mock_qdrant.search.return_value = []
    context = await service.get_injection_context("user-1", "nothing")
    assert context == ""


async def test_injection_context_skips_duplicate(service, mock_qdrant):
    """get_injection_context skips when top-1 score > 0.95 (current session dedup)."""
    mock_qdrant.search.return_value = [
        {"id": "sess-current", "score": 0.97, "user_id": "user-1", "summary": "same session"},
    ]
    context = await service.get_injection_context("user-1", "same")
    assert context == ""


# ── CRUD ──


async def test_list_by_user(service, mock_db):
    """list_by_user returns paginated summaries."""
    mock_rec = MagicMock()
    mock_rec.id = "sum-1"
    mock_rec.session_id = "sess-1"
    mock_rec.summary = "test"
    mock_rec.created_at = None
    mock_rec.updated_at = None

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar=Mock(return_value=1)),
        MagicMock(scalars=Mock(return_value=Mock(all=Mock(return_value=[mock_rec])))),
    ])

    items, total = await service.list_by_user("user-1", skip=0, limit=20)
    assert total == 1
    assert items[0]["id"] == "sum-1"


async def test_update_summary_not_found(service, mock_db):
    """update_summary returns False when record does not exist."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    ok = await service.update_summary("bad-id", "new text", "user-1")
    assert ok is False


async def test_update_summary_success(service, mock_db, mock_llm, mock_qdrant):
    """update_summary updates PG and re-embeds in Qdrant."""
    mock_rec = Mock()
    mock_rec.id = "sum-1"
    mock_rec.session_id = "sess-1"
    mock_rec.summary = "old"
    mock_rec.created_at = None
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_rec

    ok = await service.update_summary("sum-1", "new text", "user-1")
    assert ok is True
    mock_qdrant.upsert.assert_awaited_once()
    assert mock_rec.summary == "new text"


async def test_delete_summary_not_found(service, mock_db):
    """delete_summary returns False when record does not exist."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    ok = await service.delete_summary("bad-id", "user-1")
    assert ok is False


async def test_delete_summary_success(service, mock_db, mock_qdrant):
    """delete_summary removes from PG and Qdrant."""
    mock_rec = Mock()
    mock_rec.id = "sum-1"
    mock_rec.session_id = "sess-1"
    mock_rec.summary = "test"
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_rec

    ok = await service.delete_summary("sum-1", "user-1")
    assert ok is True
    mock_db.delete.assert_called_once_with(mock_rec)
    mock_qdrant.delete.assert_awaited_once_with("sess-1")
