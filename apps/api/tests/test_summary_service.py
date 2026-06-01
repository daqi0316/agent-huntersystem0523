"""SummaryService unit tests — mock DB, LLM, and Qdrant at source level."""

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.services.summary_service import (
    SummaryService as SUT,
    SEARCH_MODE_VECTOR,
    SEARCH_MODE_FTS,
    SEARCH_MODE_HYBRID,
)


# ── Fixtures ──


@pytest.fixture
def mock_db():
    """Return an async-mock DB session with properly chained sync sub-methods.

    Each call to db.execute() returns a MagicMock that mimics SQLAlchemy's
    async Result, where .scalar_one_or_none() / .scalars() / .scalar() are
    all sync (not async) methods.

    Also supports db.execute() with a text() SQL (returns mappings via .mappings()).
    """
    db = AsyncMock()
    mappings_result = MagicMock()
    mappings_result.__iter__.return_value = iter([])
    mappings_result.all.return_value = []
    default_result = MagicMock(
        scalar_one_or_none=Mock(return_value=None),
        scalars=Mock(return_value=Mock(all=Mock(return_value=[]))),
        scalar=Mock(return_value=0),
    )
    # .mappings() used by raw SQL queries in search_fts — must be iterable
    default_result.mappings = Mock(return_value=mappings_result)
    db.execute = AsyncMock(return_value=default_result)
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
def mock_llm_json():
    """Return a mock LLM client that returns structured JSON (summary + key_insights)."""
    llm = AsyncMock()
    llm.embed = AsyncMock(return_value=[0.1] * 1024)
    llm.chat = AsyncMock(return_value=(
        '{\n'
        '  "summary": "Reviewed Python candidates and arranged tech interviews.",\n'
        '  "key_insights": {\n'
        '    "preferred_skills": ["Python", "FastAPI"],\n'
        '    "salary_range": "30k-40k",\n'
        '    "screening_patterns": ["tech lead background preferred"],\n'
        '    "rejected_reasons": []\n'
        '  }\n'
        '}'
    ))
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
    """_call_summary_llm returns None when messages have no content."""
    messages = [{"role": "user", "content": None}, {"role": "assistant", "content": None}]
    result = await service._call_summary_llm(messages)
    assert result is None


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
    """list_by_user returns paginated summaries with key_insights."""
    mock_rec = MagicMock()
    mock_rec.id = "sum-1"
    mock_rec.session_id = "sess-1"
    mock_rec.summary = "test"
    mock_rec.key_insights = {"preferred_skills": ["Python"]}
    mock_rec.created_at = None
    mock_rec.updated_at = None

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar=Mock(return_value=1)),
        MagicMock(scalars=Mock(return_value=Mock(all=Mock(return_value=[mock_rec])))),
    ])

    items, total = await service.list_by_user("user-1", skip=0, limit=20)
    assert total == 1
    assert items[0]["id"] == "sum-1"
    assert items[0]["key_insights"] == {"preferred_skills": ["Python"]}


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
    mock_rec.key_insights = None
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


# ── FTS search ──


async def test_search_fts_empty_query(service):
    """search_fts returns empty list for empty query string."""
    result = await service.search_fts("user-1", "")
    assert result == []


async def test_search_fts_empty_results(service, mock_db):
    """search_fts returns empty list when no rows match."""
    # mappings() already returns an empty iterable from fixture
    result = await service.search_fts("user-1", "nonexistent")
    assert result == []


async def test_search_fts_returns_results(service, mock_db):
    """search_fts returns ranked results from raw SQL."""
    row = {
        "id": "sum-1",
        "session_id": "sess-1",
        "summary": "Reviewed Python candidate",
        "key_insights": {"preferred_skills": ["Python"]},
        "created_at": None,
        "updated_at": None,
        "rank": 0.75,
    }
    iter_mock = MagicMock()
    iter_mock.__iter__.return_value = iter([row])
    mock_db.execute.return_value.mappings.return_value = iter_mock

    results = await service.search_fts("user-1", "Python", top_k=5)
    assert len(results) == 1
    assert results[0]["session_id"] == "sess-1"
    assert results[0]["rank"] == 0.75
    assert results[0]["key_insights"]["preferred_skills"] == ["Python"]


# ── get_relevant modes ──


async def test_get_relevant_fts_mode(service, mock_db):
    """get_relevant with mode=fts delegates to search_fts."""
    row = {
        "id": "sum-1",
        "session_id": "sess-1",
        "summary": "Python developer",
        "key_insights": None,
        "created_at": None,
        "updated_at": None,
        "rank": 0.85,
    }
    iter_mock = MagicMock()
    iter_mock.__iter__.return_value = iter([row])
    mock_db.execute.return_value.mappings.return_value = iter_mock

    results = await service.get_relevant("user-1", "Python", mode=SEARCH_MODE_FTS)
    assert len(results) == 1
    assert results[0]["rank"] == 0.85


async def test_get_relevant_empty_query_all_modes(service):
    """get_relevant returns empty list for empty query regardless of mode."""
    vector_result = await service.get_relevant("user-1", "", mode=SEARCH_MODE_VECTOR)
    fts_result = await service.get_relevant("user-1", "", mode=SEARCH_MODE_FTS)
    hybrid_result = await service.get_relevant("user-1", "", mode=SEARCH_MODE_HYBRID)
    assert vector_result == []
    assert fts_result == []
    assert hybrid_result == []


async def test_get_relevant_hybrid_mode(service, mock_db, mock_llm):
    """get_relevant in hybrid mode merges vector + FTS results."""
    fts_row = {
        "id": "sum-3",
        "session_id": "sess-3",
        "summary": "Screened frontend developers",
        "key_insights": None,
        "created_at": None,
        "updated_at": None,
        "rank": 0.90,
    }
    iter_mock = MagicMock()
    iter_mock.__iter__.return_value = iter([fts_row])
    mock_db.execute.return_value.mappings.return_value = iter_mock

    results = await service.get_relevant("user-1", "developer", mode=SEARCH_MODE_HYBRID)
    assert len(results) > 0
    session_ids = {r["session_id"] for r in results}
    assert "sess-1" in session_ids
    assert "sess-3" in session_ids


async def test_get_relevant_hybrid_fallback_fts(service, mock_db, mock_llm):
    """hybrid mode falls back to FTS-only when embedding fails."""
    mock_llm.embed = AsyncMock(return_value=[])
    fts_row = {
        "id": "sum-1",
        "session_id": "sess-1",
        "summary": "Fallback result",
        "key_insights": None,
        "created_at": None,
        "updated_at": None,
        "rank": 0.70,
    }
    iter_mock = MagicMock()
    iter_mock.__iter__.return_value = iter([fts_row])
    mock_db.execute.return_value.mappings.return_value = iter_mock

    results = await service.get_relevant("user-1", "anything", mode=SEARCH_MODE_HYBRID)
    assert len(results) == 1
    assert results[0]["session_id"] == "sess-1"


# ── JSON-structured key_insights extraction ──


async def test_generate_with_key_insights(mock_db, mock_llm_json, mock_qdrant):
    """generate extracts key_insights when LLM returns structured JSON."""
    svc = SUT(db=mock_db, llm=mock_llm_json, qdrant=mock_qdrant)
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await svc.generate("user-1", "sess-1", messages)

    assert result == "Reviewed Python candidates and arranged tech interviews."

    # Verify key_insights was passed to _upsert_pg — check db.add was called
    # with a SessionSummary that has key_insights
    added = mock_db.add.call_args[0][0]
    assert added.key_insights == {
        "preferred_skills": ["Python", "FastAPI"],
        "salary_range": "30k-40k",
        "screening_patterns": ["tech lead background preferred"],
        "rejected_reasons": [],
    }


async def test_call_summary_llm_json_parse(service, mock_llm_json):
    """_call_summary_llm parses structured JSON correctly."""
    service.llm = mock_llm_json  # replace default mock_llm with JSON-returning one
    message = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    summary_text, key_insights = await service._call_summary_llm(message)
    assert summary_text == "Reviewed Python candidates and arranged tech interviews."
    assert key_insights["preferred_skills"] == ["Python", "FastAPI"]
    assert key_insights["salary_range"] == "30k-40k"


async def test_generate_with_key_insights_update(mock_db, mock_llm_json, mock_qdrant):
    """generate updates key_insights on an existing record."""
    existing = Mock()
    existing.summary = "old"
    existing.key_insights = None
    existing.updated_at = None
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=Mock(return_value=existing))
    )

    svc = SUT(db=mock_db, llm=mock_llm_json, qdrant=mock_qdrant)
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(8)]
    result = await svc.generate("user-1", "sess-1", messages)

    assert result == "Reviewed Python candidates and arranged tech interviews."
    assert existing.key_insights == {
        "preferred_skills": ["Python", "FastAPI"],
        "salary_range": "30k-40k",
        "screening_patterns": ["tech lead background preferred"],
        "rejected_reasons": [],
    }
