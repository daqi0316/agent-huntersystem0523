"""v1.4b Phase A E2E — orchestrator match → schedule 子图 + 4 阶段编排端到端.

Momus §1.1 修正版:
  v1.4 "full pipeline orchestrator" 范围不明 → 拆 v1.4a (parse→evaluate) + v1.4b (match→schedule) 2 PR.
  本测试覆盖 v1.4b 后 2 阶段 (match + schedule) + 4 阶段编排 (parse→evaluate→match→schedule).

覆盖 3 测:
  test_orchestrator_match_subgraph: sourcing subgraph 端到端 (mock sourcing agent)
  test_orchestrator_schedule_subgraph: interview subgraph 端到端 (mock interview agent)
  test_orchestrator_full_pipeline: 4 阶段编排 (mock RouterAgent._rule_classify, 走 resume_parser → screening → sourcing → interview)

设计原则 (复用 A3 v1.4a 模式):
  - mock agent 在 app.agents.registry.AgentRegistry.resolve 入口 patch
  - mock router 在 app.graphs.orchestrator.RouterAgent._rule_classify 入口 patch
  - DB 真跑, unique email 避免污染
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
from app.core.state import make_initial_task_state
from app.graphs.orchestrator import create_orchestrator_graph
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
    """复用 A3 v1.4a fixture: AsyncClient + mock auth + org context."""

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
async def test_orchestrator_match_subgraph(e2e_client):
    """v1.4b 阶段 3: sourcing subgraph 端到端 — mock sourcing agent, 验 candidates_found."""
    from app.graphs.agents.sourcing import create_sourcing_subgraph

    fake_search = {
        "result": {
            "candidates": [
                {"candidate_id": "cand-1", "name": "Alice", "match_score": 0.92},
                {"candidate_id": "cand-2", "name": "Bob", "match_score": 0.85},
            ]
        }
    }
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_search)

    subgraph = create_sourcing_subgraph()
    init_state = {
        "job_id": "test-job-id",
        "skills": ["Python", "FastAPI"],
        "candidates_found": [],
        "current_step": "init",
        "error": None,
    }

    with patch("app.agents.registry.AgentRegistry.resolve", return_value=fake_agent):
        result = await subgraph.ainvoke(
            init_state,
            config={"configurable": {"thread_id": f"v1_4b_match_{uuid.uuid4().hex}"}},
        )

    assert result.get("error") is None, f"subgraph error: {result}"
    candidates = result.get("candidates_found", [])
    assert len(candidates) == 2, f"expected 2 candidates, got {len(candidates)}"
    assert candidates[0]["candidate_id"] == "cand-1"
    assert candidates[1]["match_score"] == 0.85
    fake_agent.run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_orchestrator_schedule_subgraph(e2e_client):
    """v1.4b 阶段 4: interview subgraph 端到端 — mock interview agent, 验 interview_scheduled."""
    from app.graphs.agents.interview import create_interview_subgraph

    fake_schedule = {
        "result": {
            "interview_id": "interview-uuid-12345",
            "scheduled_time": "2026-07-01T10:00:00+08:00",
            "status": "scheduled",
            "feedback": "视频面试 R1, 面试官: HR 张三",
        }
    }
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_schedule)

    subgraph = create_interview_subgraph()
    init_state = {
        "candidate_id": "cand-uuid-67890",
        "job_id": "job-uuid-11111",
        "interview_scheduled": False,
        "feedback": None,
        "current_step": "init",
        "error": None,
    }

    with patch("app.agents.registry.AgentRegistry.resolve", return_value=fake_agent):
        result = await subgraph.ainvoke(
            init_state,
            config={"configurable": {"thread_id": f"v1_4b_sched_{uuid.uuid4().hex}"}},
        )

    assert result.get("error") is None, f"subgraph error: {result}"
    assert result.get("interview_scheduled") is True
    feedback = result.get("feedback", {})
    assert feedback.get("interview_id") == "interview-uuid-12345"
    assert feedback.get("status") == "scheduled"
    fake_agent.run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_orchestrator_full_pipeline(e2e_client):
    """v1.4 全 4 阶段编排: parse → evaluate → match → schedule.

    orchestrator 单次 ainvoke 跑 1 intent (router → 1 subgraph → END).
    测 4 阶段串联: 4 次 ainvoke, 每次 mock router 返下一个 intent,
    验 4 子图依次跑 + execution_history 含 4 entry + 最终 state 含所有子图 state.
    """
    unique_id = uuid.uuid4().hex
    extracted = _make_extracted(unique_id)

    fake_eval = {
        "result": {
            "overall_score": 8.5,
            "dimensions": {"技术": 9, "沟通": 8},
            "verdict": "strong_hire",
        }
    }
    fake_search = {
        "result": {
            "candidates": [{"candidate_id": f"cand-{unique_id[:8]}", "match_score": 0.92}]
        }
    }
    fake_schedule = {
        "result": {
            "interview_id": f"interview-{unique_id[:8]}",
            "status": "scheduled",
        }
    }

    fake_eval_agent = MagicMock()
    fake_eval_agent.run = AsyncMock(return_value=fake_eval)
    fake_search_agent = MagicMock()
    fake_search_agent.run = AsyncMock(return_value=fake_search)
    fake_schedule_agent = MagicMock()
    fake_schedule_agent.run = AsyncMock(return_value=fake_schedule)

    agents_by_name = {
        "screening": fake_eval_agent,
        "sourcing": fake_search_agent,
        "interview": fake_schedule_agent,
    }

    def _resolve(name: str):
        return agents_by_name.get(name)

    # RouterAgent mock: 每次 ainvoke 返下一个 intent
    # (router_call_count 不限, 每次进 graph 入口 intent_recognition 调一次)
    router_intent_index = {"i": 0}
    intent_sequence = ["resume_parser", "screening", "sourcing", "interview"]

    def _mock_classify(text: str) -> tuple[str, float]:
        intent = intent_sequence[router_intent_index["i"] % len(intent_sequence)]
        router_intent_index["i"] += 1
        return intent, 0.95

    graph = create_orchestrator_graph(checkpointer=None)

    files = {"file": ("r.txt", RESUME_TEXT.encode(), "text/plain")}
    r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
    assert r.status_code == 200
    plain_text = r.json()["plain_text"]

    # 4 阶段: 4 次 ainvoke 串联, state 累积
    state = make_initial_task_state(
        task_id=f"v1_4b_full_{unique_id}",
        user_id="test-user-id",
        job_id="test-job-id",
        input_text=plain_text,
    )
    thread_id = f"v1_4b_full_{unique_id}"

    with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = extracted
        with patch("app.agents.registry.AgentRegistry.resolve", side_effect=_resolve):
            with patch("app.agents.router_agent.RouterAgent._rule_classify", side_effect=_mock_classify):
                # 阶段 1: parse (router mock → resume_parser)
                state = await graph.ainvoke(
                    state,
                    config={"configurable": {"thread_id": thread_id}},
                )
                # 阶段 2: evaluate (router mock → screening)
                state = await graph.ainvoke(
                    state,
                    config={"configurable": {"thread_id": thread_id}},
                )
                # 阶段 3: match (router mock → sourcing)
                state = await graph.ainvoke(
                    state,
                    config={"configurable": {"thread_id": thread_id}},
                )
                # 阶段 4: schedule (router mock → interview)
                state = await graph.ainvoke(
                    state,
                    config={"configurable": {"thread_id": thread_id}},
                )

    # 验 4 阶段结果 (state 累积)
    assert router_intent_index["i"] == 4, f"router called {router_intent_index['i']} times, expected 4"
    assert state.get("resume_parser_state", {}).get("error") is None
    assert state.get("screening_state", {}).get("match_score") == 8.5
    assert len(state.get("sourcing_state", {}).get("candidates_found", [])) == 1
    assert state.get("interview_state", {}).get("interview_scheduled") is True

    # 验 execution_history 含 4 entry
    history = state.get("execution_history", [])
    agents_in_history = [entry.get("agent") for entry in history]
    for expected in ["resume_parser", "screening", "sourcing", "interview"]:
        assert expected in agents_in_history, f"missing {expected} in history: {agents_in_history}"

    mock_extract.assert_awaited_once()
    fake_eval_agent.run.assert_awaited_once()
    fake_search_agent.run.assert_awaited_once()
    fake_schedule_agent.run.assert_awaited_once()
