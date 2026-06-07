"""v1.4a Phase A E2E — orchestrator parse → evaluate 子图端到端.

Momus §1.1 修正版:
  v1.4 "full pipeline orchestrator" 范围不明 → 拆 v1.4a (parse→evaluate) + v1.4b (match→schedule) 2 PR.
  本测试覆盖 v1.4a 前 2 阶段 (parse + evaluate).

覆盖 2 测:
  test_orchestrator_parse_subgraph: resume_parser subgraph 端到端 (mock LLM extract_from_text)
  test_orchestrator_evaluate_subgraph: screening subgraph 端到端 (mock screening agent)

设计原则 (复用 v1.1+v1.2 模式):
  - mock LLM 在 app.tools.resume_parser.extract_from_text 入口 patch
  - mock agent 在 app.agents.registry.AgentRegistry.resolve 入口 patch
  - DB 真跑, unique email 避免污染
  - 不动 production code

v1.4a 编排测试 (parse→evaluate 串联) 推 A4 v1.4b 一起做:
  orchestrator 编排需要 mock RouterAgent._rule_classify + intent_recognition,
  复杂度高, 跟 v1.4b 编排测试一起做避免重复 setup.
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
from app.schemas.resume import ExtractedCandidate


RESUME_TEXT = """张三
男 | 13800138000 | zhangsan@test.com
5年 Python 后端开发经验
熟练掌握 Python, FastAPI, PostgreSQL, Redis, Docker
本科 @ 清华大学 @ 计算机科学
现任 Acme 公司 Senior Engineer
"""


def _make_extracted(unique_id: str) -> ExtractedCandidate:
    return ExtractedCandidate(
        name=f"张三_{unique_id[:8]}",
        email=f"z_{unique_id}@test.com",
        phone="13800138000",
        summary="5年 Python 后端开发经验",
        skills=["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
        experience_years=5,
        education="本科 @ 清华大学 @ 计算机科学",
        current_company="Acme",
        current_title="Senior Engineer",
    )


@pytest_asyncio.fixture
async def e2e_client():
    """复用 v1.1+v1.2 模式: AsyncClient + mock auth + org context."""

    async def _mock_user_id() -> str:
        return "test-user-id"

    async def _mock_org_scoped_db():
        from app.core.database import get_db as _get_db
        gen = _get_db()
        try:
            real_db = await gen.__anext__()
            yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), real_db
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
@pytest.mark.timeout(60)
async def test_orchestrator_parse_subgraph(e2e_client):
    """v1.4a 阶段 1: resume_parser subgraph 端到端 — mock LLM extract_from_text, 验 parsed_data.

    直接调 create_resume_parser_subgraph() (而不是 orchestrator 编排), 隔离 subgraph 测试.
    """
    from app.graphs.agents.resume_parser import create_resume_parser_subgraph

    unique_id = uuid.uuid4().hex
    extracted = _make_extracted(unique_id)

    files = {"file": ("r.txt", RESUME_TEXT.encode(), "text/plain")}
    r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
    assert r.status_code == 200, f"upload failed: {r.text}"
    plain_text = r.json()["plain_text"]

    subgraph = create_resume_parser_subgraph()
    init_state = {
        "content": plain_text,
        "file_url": "",
        "parsed_data": None,
        "confidence": 0,
        "current_step": "init",
        "error": None,
    }
    with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = extracted
        result = await subgraph.ainvoke(
            init_state,
            config={"configurable": {"thread_id": f"v1_4a_{unique_id}"}},
        )

    assert result.get("error") is None, f"subgraph error: {result}"
    parsed = result.get("parsed_data")
    assert parsed is not None, f"no parsed_data: {result}"
    # parsed_data 嵌套结构: basic_info {name, email(mask_pii 后), years_of_experience, ...} + skills (顶层 list)
    basic = parsed.get("basic_info", {})
    assert basic.get("name") == extracted.name
    assert "@" in basic.get("email", ""), f"email malformed: {basic.get('email')}"
    assert basic.get("years_of_experience") == 5
    assert "Python" in parsed.get("skills", [])
    assert parsed.get("candidate_id"), f"no candidate_id: {parsed}"
    assert parsed.get("confidence", 0) > 0
    mock_extract.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_orchestrator_evaluate_subgraph(e2e_client):
    """v1.4a 阶段 2: screening subgraph 端到端 — mock screening agent.run, 返 evaluation_result."""
    fake_eval = {
        "result": {
            "overall_score": 8.5,
            "dimensions": {"技术": 9, "沟通": 8},
            "verdict": "strong_hire",
            "reasoning": "扎实的 FastAPI 经验",
        }
    }
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_eval)

    from app.graphs.agents.screening import create_screening_subgraph

    subgraph = create_screening_subgraph()
    init_state = {
        "candidate_id": "test-candidate-id",
        "job_id": "test-job-id",
        "match_score": 0,
        "screening_result": None,
        "current_step": "init",
        "error": None,
    }

    with patch("app.agents.registry.AgentRegistry.resolve", return_value=fake_agent):
        result = await subgraph.ainvoke(
            init_state,
            config={"configurable": {"thread_id": f"v1_4a_eval_{uuid.uuid4().hex}"}},
        )

    assert result.get("error") is None, f"subgraph error: {result}"
    assert result.get("match_score") == 8.5
    screening = result.get("screening_result")
    assert screening is not None
    assert screening.get("overall_score") == 8.5
    assert screening.get("verdict") == "strong_hire"
    fake_agent.run.assert_awaited_once()
