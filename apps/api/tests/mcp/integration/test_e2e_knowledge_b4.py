"""Phase B · B4 Knowledge/RAG E2E — Qdrant upload→query→cite 端到端.

Momus §5.2: B4 = Knowledge/RAG E2E (Qdrant upload→query→cite, 2d)
修正: 真 Qdrant (compose dev 已跑) + mock LLM (embed + chat, B1/B2 教训)

覆盖 3 测:
  test_ingest_document_chunks_text: ingest_document 分块 + embedding + upsert 端到端
  test_search_returns_top_k_relevant: 向量检索 top_k + score 过滤 (score > 0.3)
  test_query_rag_returns_answer_with_citations: RAG query: search → LLM 生成 → 含 sources (cite)

设计原则 (复用 B1+B2 模式):
  - mock LLM 在 app.services.knowledge.get_llm_client 入口 patch (B1 教训: module 内部名字)
  - mock Qdrant 在 app.services.knowledge.get_qdrant 入口 patch (隔离 Qdrant 依赖, 不污染 DB)
  - DB 真跑 (knowledge collection metadata)
  - 不动 production code
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.core.dependencies import get_current_user_id
from app.core.org_context import OrgContext, org_scoped_db
from app.main import app


@pytest_asyncio.fixture
async def e2e_client():
    """复用 A3+A4+B1+B2 fixture: AsyncClient + mock auth + 真 user (e2e-tester)."""

    real_user_id = "1d20462f-6dec-4be0-a48b-7595b3bf2ffb"

    async def _mock_user_id() -> str:
        return real_user_id

    async def _mock_org_scoped_db():
        from app.core.database import get_db as _get_db
        gen = _get_db()
        try:
            real_db = await gen.__anext__()
            yield OrgContext(org_id="test-org-id", user_id=real_user_id, role="hr"), real_db
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

    app.dependency_overrides[get_current_user_id] = _mock_user_id
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(org_scoped_db, None)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ingest_document_chunks_text(e2e_client):
    """B4 测 1: ingest_document 分块 + embedding + upsert 端到端.

    mock LLM.embed 返 fixed vector (避免真 omlx embed), mock Qdrant.upsert 验证调用.
    """
    from app.services.knowledge import KnowledgeService

    fake_embed = [0.1] * 768  # 假设 768-dim embedding (qdrant 默认)
    fake_llm_client = MagicMock()
    fake_llm_client.embed = AsyncMock(return_value=fake_embed)

    # mock Qdrant client — 验 upsert 被调, 参数对
    fake_qdrant = MagicMock()
    fake_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    fake_qdrant.create_collection = AsyncMock()
    fake_qdrant.upsert = AsyncMock()

    unique_id = uuid.uuid4().hex[:8]
    test_content = (
        "Qdrant 是一个开源的向量搜索引擎，用于生产环境的 AI 应用。"
        "它支持高效的相似度搜索，扩展性好，可与多种机器学习模型集成。"
    ) * 3  # 重复 3 次让 chunking > 1 chunk

    service = KnowledgeService()
    with patch("app.services.knowledge.get_llm_client", return_value=fake_llm_client):
        with patch("app.services.knowledge.get_qdrant", return_value=fake_qdrant):
            result = await service.ingest_document(
                title=f"Test Doc {unique_id}",
                content=test_content,
            )

    # 验 ingest 返 document_id + chunks_count
    assert result["document_id"] is not None
    assert result["title"] == f"Test Doc {unique_id}"
    assert result["chunks_count"] > 0
    assert "warning" not in result, f"unexpected warning: {result.get('warning')}"

    # 验 Qdrant 链被调 (create_collection + upsert)
    assert fake_qdrant.create_collection.await_count >= 1
    assert fake_qdrant.upsert.await_count >= 1

    # 验 upsert 的 points 含 document_id + title + content
    upsert_call = fake_qdrant.upsert.call_args
    assert upsert_call.kwargs["collection_name"] is not None
    points = upsert_call.kwargs["points"]
    assert len(points) > 0
    first_point = points[0]
    assert first_point.payload["title"] == f"Test Doc {unique_id}"
    assert first_point.payload["document_id"] == result["document_id"]
    assert first_point.payload["chunk_index"] == 0
    assert "Qdrant" in first_point.payload["content"]


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_search_returns_top_k_relevant(e2e_client):
    """B4 测 2: search 向量检索 top_k + score 过滤 (score > 0.3).

    mock LLM.embed + mock Qdrant.query_points 返 3 候选 (2 高分, 1 低分), 验 score > 0.3 过滤.
    """
    from app.services.knowledge import KnowledgeService

    fake_embed = [0.1] * 768
    fake_llm_client = MagicMock()
    fake_llm_client.embed = AsyncMock(return_value=fake_embed)

    # mock Qdrant query_points 返 3 候选 (2 高分 > 0.3, 1 低分 < 0.3)
    high_score_point_1 = MagicMock(
        id="chunk-1", score=0.85,
        payload={"title": "Doc A", "content": "A content", "document_id": "doc-1", "source": "src-a"},
    )
    high_score_point_2 = MagicMock(
        id="chunk-2", score=0.62,
        payload={"title": "Doc B", "content": "B content", "document_id": "doc-2", "source": "src-b"},
    )
    low_score_point = MagicMock(
        id="chunk-3", score=0.2,  # < 0.3 阈值
        payload={"title": "Doc C", "content": "C content", "document_id": "doc-3", "source": "src-c"},
    )
    mock_response = MagicMock(points=[high_score_point_1, high_score_point_2, low_score_point])

    fake_qdrant = MagicMock()
    fake_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    fake_qdrant.create_collection = AsyncMock()
    fake_qdrant.query_points = AsyncMock(return_value=mock_response)

    service = KnowledgeService()
    with patch("app.services.knowledge.get_llm_client", return_value=fake_llm_client):
        with patch("app.services.knowledge.get_qdrant", return_value=fake_qdrant):
            results = await service.search(query="什么是 Qdrant", top_k=5)

    # 验 3 候选 -> 过滤后 2 (score > 0.3)
    assert len(results) == 2, f"expected 2 after score filter, got {len(results)}"
    assert results[0]["id"] == "chunk-1"
    assert results[0]["score"] == 0.85
    assert results[0]["title"] == "Doc A"
    assert results[1]["id"] == "chunk-2"
    assert results[1]["score"] == 0.62
    # 低分 0.2 被过滤
    assert "chunk-3" not in [r["id"] for r in results]

    # 验 Qdrant query_points 被调
    fake_qdrant.query_points.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_query_rag_returns_answer_with_citations(e2e_client):
    """B4 测 3: RAG 端到端 — search → LLM 生成回答 → 含 sources (cite).

    mock LLM.embed (search 用) + LLM.chat (RAG 生成用) + Qdrant.query_points.
    验 query() 返 answer + sources list 含原文 + title (cite 格式).
    """
    from app.services.knowledge import KnowledgeService

    # search 阶段 mock
    fake_embed = [0.1] * 768
    search_point = MagicMock(
        id="chunk-cite-1", score=0.9,
        payload={"title": "RAG 文档", "content": "RAG 是检索增强生成技术", "document_id": "doc-rag"},
    )
    mock_search_response = MagicMock(points=[search_point])

    # RAG 生成阶段 mock — LLM 返带 cite 的回答
    rag_answer_with_cite = "根据 [来源: RAG 文档] 介绍, RAG 是检索增强生成技术。"

    fake_llm_client = MagicMock()
    fake_llm_client.embed = AsyncMock(return_value=fake_embed)
    fake_llm_client.chat = AsyncMock(return_value=rag_answer_with_cite)

    fake_qdrant = MagicMock()
    fake_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    fake_qdrant.create_collection = AsyncMock()
    fake_qdrant.query_points = AsyncMock(return_value=mock_search_response)

    service = KnowledgeService()
    with patch("app.services.knowledge.get_llm_client", return_value=fake_llm_client):
        with patch("app.services.knowledge.get_qdrant", return_value=fake_qdrant):
            result = await service.query(query="什么是 RAG", top_k=5)

    # 验 RAG 返 answer + sources
    assert "answer" in result
    assert "sources" in result
    assert "RAG" in result["answer"]  # 答案含 RAG
    assert "[来源: RAG 文档]" in result["answer"]  # cite 格式

    # 验 sources 含原文 (cite 内容)
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["title"] == "RAG 文档"
    assert source["content"] == "RAG 是检索增强生成技术"
    assert source["id"] == "chunk-cite-1"
    assert source["score"] == 0.9

    # 验 LLM chat 被调 1 次 (RAG 生成)
    fake_llm_client.chat.assert_awaited_once()
    # 验 LLM embed 被调 1 次 (search 阶段)
    fake_llm_client.embed.assert_awaited_once()
