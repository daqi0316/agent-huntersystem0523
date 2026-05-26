"""Orchestrator API tests: task decomposition & DAG execution."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_orchestrate_success(client):
    """Mock OrchestratorAgent returns completed decomposition result."""
    with patch("app.api.orchestrator.agent") as mock_agent:
        mock_agent.run = AsyncMock(return_value={
            "agent": "orchestrator",
            "status": "completed",
            "total_sub_tasks": 2,
            "succeeded": 2,
            "failed": 0,
            "duration_seconds": 1.23,
            "outputs": [{"summary": "Task 1 done"}, {"summary": "Task 2 done"}],
            "sub_tasks": [
                {"type": "screening", "description": "Screen resumes", "status": "completed"},
                {"type": "report", "description": "Generate report", "status": "completed"},
            ],
        })

        resp = await client.post("/api/v1/orchestrator/analyze", json={
            "task": "Screen candidates and generate a report",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["total_sub_tasks"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert "编排完成" in data["summary"]


@pytest.mark.asyncio
async def test_orchestrate_empty_task_returns_422(client):
    """Empty task string returns 422."""
    resp = await client.post("/api/v1/orchestrator/analyze", json={
        "task": "",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_orchestrate_with_context(client):
    """Context dictionary is forwarded to the agent."""
    with patch("app.api.orchestrator.agent") as mock_agent:
        mock_agent.run = AsyncMock(return_value={
            "agent": "orchestrator",
            "status": "completed",
            "total_sub_tasks": 1,
            "succeeded": 1,
            "failed": 0,
            "duration_seconds": 0.5,
            "outputs": [{"summary": "Done with context"}],
            "sub_tasks": [{"type": "jd_generation", "description": "Generate JD", "status": "completed"}],
        })

        resp = await client.post("/api/v1/orchestrator/analyze", json={
            "task": "Generate a JD for a senior role",
            "context": {"company": "Acme Corp", "department": "Engineering"},
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_sub_tasks"] == 1
    # Verify context was passed to agent.run
    call_args = mock_agent.run.call_args[0][0]
    assert call_args["context"]["company"] == "Acme Corp"


@pytest.mark.asyncio
async def test_orchestrate_partial_failure(client):
    """Some sub-tasks fail, returns partial status."""
    with patch("app.api.orchestrator.agent") as mock_agent:
        mock_agent.run = AsyncMock(return_value={
            "agent": "orchestrator",
            "status": "partial",
            "total_sub_tasks": 3,
            "succeeded": 2,
            "failed": 1,
            "duration_seconds": 2.0,
            "outputs": [{"summary": "OK"}, {"summary": "OK"}, {"error": "Failed"}],
            "sub_tasks": [
                {"type": "screening", "description": "Screen", "status": "completed"},
                {"type": "report", "description": "Report", "status": "completed"},
                {"type": "interview", "description": "Interview", "status": "failed", "error": "Timeout"},
            ],
        })

        resp = await client.post("/api/v1/orchestrator/analyze", json={
            "task": "Run screening, report, and interview",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True  # partial is not "failed"
    assert data["status"] == "partial"
    assert data["total_sub_tasks"] == 3
    assert data["succeeded"] == 2
    assert data["failed"] == 1
    assert "部分完成" in data["summary"]


@pytest.mark.asyncio
async def test_orchestrate_unknown_status(client):
    """Unknown status returns fallback summary."""
    with patch("app.api.orchestrator.agent") as mock_agent:
        mock_agent.run = AsyncMock(return_value={
            "agent": "orchestrator",
            "status": "unknown",
            "total_sub_tasks": 0,
            "succeeded": 0,
            "failed": 0,
            "duration_seconds": 0,
            "outputs": [],
            "sub_tasks": [],
        })
        resp = await client.post("/api/v1/orchestrator/analyze", json={
            "task": "something weird",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "编排执行异常"


# ──────────────────────────────────────────────
# OrchestratorAgent unit tests
# ──────────────────────────────────────────────

from unittest.mock import AsyncMock as A2, MagicMock as M2, patch as U2
from app.agents.orchestrator_agent import OrchestratorAgent


@pytest.fixture
def orch_agent():
    agent = OrchestratorAgent(name="orch")
    mock_agent = M2()
    mock_agent.run = A2(return_value={"agent": "mock", "status": "completed"})
    agent.router.route = M2(return_value=mock_agent)
    return agent


@pytest.fixture
def orch_llm():
    mock_llm = A2()
    mock_llm.chat = A2()
    patcher = U2("app.agents.orchestrator_agent.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


def test_orch_init(orch_agent):
    assert orch_agent.name == "orch"
    assert orch_agent.sub_agents == {}


def test_orch_register(orch_agent):
    mock = M2()
    mock.name = "test_a"
    orch_agent.register("screening", mock)
    assert "screening" in orch_agent.sub_agents
    assert orch_agent.sub_agents["screening"] is mock


def test_orch_guess_returns_screening_for_keyword_screen(orch_agent):
    assert orch_agent.guess_type("简历初筛") == "screening"


def test_orch_guess_returns_screening_for_keyword_match(orch_agent):
    assert orch_agent.guess_type("match candidates") == "screening"


def test_orch_guess_returns_jd_for_keyword_jd(orch_agent):
    assert orch_agent.guess_type("generate jd for engineer") == "jd_generation"


def test_orch_guess_returns_search_for_keyword_candidate(orch_agent):
    assert orch_agent.guess_type("find candidates for role") == "candidate_search"


def test_orch_guess_returns_interview_for_keyword_interview(orch_agent):
    assert orch_agent.guess_type("安排面试") == "interview"


def test_orch_guess_default_is_screening(orch_agent):
    assert orch_agent.guess_type("hello world") == "screening"


@pytest.mark.asyncio
async def test_decompose_returns_list(orch_llm, orch_agent):
    orch_llm.chat.return_value = (
        '[{"type": "screening", "description": "filter", "depends_on": []}]'
    )
    result = await orch_agent.decompose("screen candidates")
    assert len(result) == 1
    assert result[0]["type"] == "screening"


@pytest.mark.asyncio
async def test_decompose_fallback_on_llm_failure(orch_llm, orch_agent):
    orch_llm.chat.return_value = "broken{{{"
    result = await orch_agent.decompose("新手 Java 开发")
    assert len(result) == 1
    assert result[0]["type"] == "screening"


def test_build_dag_topological(orch_agent):
    tl = [
        {"type": "screening", "depends_on": []},
        {"type": "search", "depends_on": [0]},
        {"type": "report", "depends_on": [1]},
    ]
    levels = orch_agent.build_dag(tl)
    assert levels == [[0], [1], [2]]


def test_build_dag_parallel_levels(orch_agent):
    tl = [
        {"type": "a", "depends_on": []},
        {"type": "b", "depends_on": []},
        {"type": "c", "depends_on": [0, 1]},
    ]
    levels = orch_agent.build_dag(tl)
    # a and b are parallel (same level), c depends on both
    assert len(levels) == 2
    assert 0 in levels[0]
    assert 1 in levels[0]
    assert levels[1] == [2]


def test_build_dag_with_cycle(orch_agent):
    tl = [
        {"type": "a", "depends_on": [1]},
        {"type": "b", "depends_on": [0]},
    ]
    levels = orch_agent.build_dag(tl)
    # cycle handling: no-zero in-degree nodes placed at end
    assert len(levels) >= 1


@pytest.mark.asyncio
async def test_execute_sub_task_screening(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "screening", "description": "filter senior devs",
    })
    assert result["status"] == "completed"
    assert result["type"] == "screening"
    assert "summary" in result["result"]


@pytest.mark.asyncio
async def test_execute_sub_task_unknown_type(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "chat", "description": "general talk",
    })
    assert result["status"] == "completed"
    assert "summary" in result["result"]


@pytest.mark.asyncio
async def test_execute_sub_task_error_handling(orch_agent):
    """Inject a type whose lazy import will fail."""
    with U2("app.services.screening.ScreeningService.__init__", return_value=None, side_effect=ValueError("mock fail")):
        result = await orch_agent.execute_sub_task({
            "type": "screening", "description": "fail",
        })
    assert result["status"] == "failed"
    assert "error" in result


@pytest.mark.asyncio
async def test_run_flow(orch_llm, orch_agent):
    orch_llm.chat.side_effect = [
        '[{"type": "screening", "description": "filter", "depends_on": []}]',
    ]
    result = await orch_agent.run({
        "task": "screen candidates",
        "context": {},
    })
    assert result["agent"] == "orch"
    assert result["status"] == "completed"
    assert result["total_sub_tasks"] == 1


@pytest.mark.asyncio
async def test_run_routing_mode(orch_agent):
    """Without task field → routes via router agent."""
    mock_target = M2()
    mock_target.run = A2(return_value={"agent": "mock", "status": "completed"})
    orch_agent.router.route = M2(return_value=mock_target)
    result = await orch_agent.run({"intent": "chat", "message": "hi"})
    assert result["status"] == "completed"
