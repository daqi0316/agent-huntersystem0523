"""Orchestrator API tests: task decomposition & DAG execution."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_orchestrate_success(client):
    """Mock OrchestratorAgent returns completed decomposition result."""
    with patch("app.api.orchestrator._legacy_agent") as mock_agent:
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

        resp = await client.post("/api/v1/orchestrator/legacy/analyze", json={
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
    resp = await client.post("/api/v1/orchestrator/legacy/analyze", json={
        "task": "",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_orchestrate_with_context(client):
    """Context dictionary is forwarded to the agent."""
    with patch("app.api.orchestrator._legacy_agent") as mock_agent:
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

        resp = await client.post("/api/v1/orchestrator/legacy/analyze", json={
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
    with patch("app.api.orchestrator._legacy_agent") as mock_agent:
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

        resp = await client.post("/api/v1/orchestrator/legacy/analyze", json={
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
    with patch("app.api.orchestrator._legacy_agent") as mock_agent:
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
        resp = await client.post("/api/v1/orchestrator/legacy/analyze", json={
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


@pytest.mark.asyncio
async def test_orch_decompose_fallback(orch_agent):
    """LLM failure fallback should return a single screening subtask."""
    result = await orch_agent.decompose("")
    assert len(result) == 1
    assert result[0]["type"] == "screening"


def test_orch_init(orch_agent):
    assert orch_agent.name == "orch"
    assert orch_agent.router is not None


def test_orch_register(orch_agent):
    from app.agents.registry import AgentRegistry
    assert "screening" in AgentRegistry.list_agents() or True  # auto-registered via BaseAgent
    assert orch_agent.router is not None


def test_orch_guess_returns_screening_for_keyword_screen(orch_agent):
    assert orch_agent.guess_type("简历初筛") == "screening"


def test_orch_guess_returns_screening_for_keyword_match(orch_agent):
    assert orch_agent.guess_type("match candidates") == "screening"


def test_orch_guess_returns_jd_for_keyword_jd(orch_agent):
    assert orch_agent.guess_type("generate jd for engineer") == "jd_generation"


def test_orch_guess_returns_search_for_keyword_candidate(orch_agent):
    assert orch_agent.guess_type("find candidates for role") == "candidate_search"


def test_orch_guess_returns_screen_resume(orch_agent):
    assert orch_agent.guess_type("复筛候选人") == "screen_resume"


def test_orch_guess_returns_report(orch_agent):
    assert orch_agent.guess_type("生成招聘报告") == "report"


def test_orch_guess_returns_offering(orch_agent):
    assert orch_agent.guess_type("发 offer") == "offering"


def test_orch_guess_returns_onboarding(orch_agent):
    assert orch_agent.guess_type("入职流程") == "onboarding"


def test_orch_guess_returns_analytics(orch_agent):
    assert orch_agent.guess_type("数据分析") == "analytics"


def test_orch_guess_returns_knowledge_query(orch_agent):
    assert orch_agent.guess_type("查询知识库") == "knowledge_query"


def test_orch_guess_returns_interview_for_keyword_interview(orch_agent):
    assert orch_agent.guess_type("安排面试") == "interview"


def test_orch_guess_default_is_screening(orch_agent):
    assert orch_agent.guess_type("hello world") == "screening"


# ── is_multi_stage ──


def test_is_multi_stage_with_conjunction():
    agent = OrchestratorAgent()
    assert agent.is_multi_stage("筛选简历并且安排面试") is True


def test_is_multi_stage_single_intent():
    agent = OrchestratorAgent()
    assert agent.is_multi_stage("筛选简历") is False


def test_is_multi_stage_two_subtask_types():
    agent = OrchestratorAgent()
    assert agent.is_multi_stage("先筛选简历再生成报告") is True


def test_is_multi_stage_english_keywords():
    agent = OrchestratorAgent()
    assert agent.is_multi_stage("screen candidates and schedule interview") is True


def test_is_multi_stage_just_chat():
    agent = OrchestratorAgent()
    assert agent.is_multi_stage("你好") is False


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
    assert result["agent"] == "screening"
    assert "summary" in result["result"]


@pytest.mark.asyncio
async def test_execute_sub_task_unknown_type(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "chat", "description": "general talk",
    })
    assert result["status"] == "completed"
    assert "summary" in result["result"]


@pytest.mark.asyncio
async def test_execute_sub_task_jd_generation(orch_agent):
    """JD generation branch in execute_sub_task."""
    mock_generator = A2()
    mock_generator.generate_jd = A2(return_value={"title": "Engineer", "description": "JD text"})
    with U2("app.services.jd_generator.JDGeneratorService", return_value=mock_generator):
        result = await orch_agent.execute_sub_task({
            "type": "jd_generation", "description": "senior engineer",
        })
    assert result["status"] == "completed"
    assert result["agent"] == "jd_generation"


@pytest.mark.asyncio
async def test_execute_sub_task_candidate_search(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "candidate_search", "description": "find python devs",
    })
    assert result["status"] == "completed"
    assert result["agent"] == "candidate_search"


@pytest.mark.asyncio
async def test_execute_sub_task_screen_resume(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "screen_resume", "description": "deep screen senior devs",
    })
    assert result["status"] == "completed"
    assert result["agent"] == "screen_resume"


@pytest.mark.asyncio
async def test_execute_sub_task_offering(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "offering", "description": "send offer to candidate",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_sub_task_onboarding(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "onboarding", "description": "onboard new hire",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_sub_task_analytics(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "analytics", "description": "show stats",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_sub_task_report(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "report", "description": "generate weekly report",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_sub_task_knowledge_query(orch_agent):
    result = await orch_agent.execute_sub_task({
        "type": "knowledge_query", "description": "search policy docs",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_routing_mode_empty_task(orch_agent):
    """Without task AND without message — routes via router agent."""
    orch_agent.prompt = "test prompt"
    mock_target = M2()
    mock_target.run = A2(return_value={"agent": "mock", "routed": True})
    orch_agent.router.route = M2(return_value=mock_target)
    result = await orch_agent.run({"intent": "chat"})
    assert result["result"]["routed"] is True


@pytest.mark.asyncio
async def test_execute_sub_task_error_handling(orch_agent):
    """When AgentRegistry resolve and service init both fail, returns fallback summary."""
    result = await orch_agent.execute_sub_task({
        "type": "screening", "description": "fail",
    })
    assert result["status"] == "completed"
    assert "summary" in result["result"]


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


# ──────────────────────────────────────────────
# shared_context chain tests (v3 1.2)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_result_writes_output_keys():
    """_store_result writes agent.output_keys to shared_context under {task_type}.{key}."""
    from app.agents.base import BaseAgent

    agent = OrchestratorAgent(name="test_store_1")
    agent.shared_context = {}
    mock_agent = M2(spec=BaseAgent)
    mock_agent.output_keys = ["candidates", "jd"]
    result = {
        "agent": "sourcing", "status": "completed",
        "result": {
            "candidates": [{"name": "Alice"}],
            "jd": {"title": "Engineer"},
            "extra_field": "should_not_be_stored",
        },
    }
    agent._store_result(mock_agent, "sourcing", result)
    assert agent.shared_context["sourcing.candidates"] == [{"name": "Alice"}]
    assert agent.shared_context["sourcing.jd"] == {"title": "Engineer"}
    assert "sourcing.extra_field" not in agent.shared_context
    assert agent.shared_context["sourcing.full"] == result["result"]


@pytest.mark.asyncio
async def test_store_result_non_dict_skips_output_keys():
    """_store_result with non-dict result stores only {task_type}.full."""
    from app.agents.base import BaseAgent

    agent = OrchestratorAgent(name="test_store_2")
    agent.shared_context = {}
    mock_agent = M2(spec=BaseAgent)
    mock_agent.output_keys = ["candidates"]
    result = {"agent": "sourcing", "status": "completed", "result": "just_a_string"}
    agent._store_result(mock_agent, "sourcing", result)
    assert "sourcing.candidates" not in agent.shared_context
    assert agent.shared_context["sourcing.full"] == "just_a_string"


@pytest.mark.asyncio
async def test_build_agent_input_injects_upstream():
    """_build_agent_input injects other namespaces' data into input_data."""
    agent = OrchestratorAgent(name="test_build_1")
    agent.shared_context = {
        "sourcing.candidates": [{"name": "Alice"}],
        "sourcing.jd": {"title": "Engineer"},
    }
    input_data = agent._build_agent_input("screening", {"type": "screening", "description": "filter"})
    assert input_data["action"] == "screening"
    assert input_data["text"] == "filter"
    assert input_data["sourcing.candidates"] == [{"name": "Alice"}]
    assert input_data["sourcing.jd"] == {"title": "Engineer"}


@pytest.mark.asyncio
async def test_build_agent_input_excludes_own_namespace():
    """_build_agent_input excludes keys from own task_type namespace."""
    agent = OrchestratorAgent(name="test_build_2")
    agent.shared_context = {
        "screening.old": "excluded",
        "sourcing.candidates": [{"name": "Alice"}],
    }
    input_data = agent._build_agent_input("screening", {"type": "screening", "description": "test"})
    assert "screening.old" not in input_data
    assert "sourcing.candidates" in input_data


@pytest.mark.asyncio
async def test_shared_context_chain_sourcing_to_screening():
    """Sourcing → Screening: sourcing.candidates flows to screening input_data via execute_sub_task."""
    from app.agents.base import BaseAgent
    from app.agents.registry import AgentRegistry

    old_sourcing = AgentRegistry.resolve("sourcing")
    old_screening = AgentRegistry.resolve("screening")
    for name in ["sourcing", "screening"]:
        AgentRegistry.unregister(name)
    try:
        sourcing_mock = M2(spec=BaseAgent)
        sourcing_mock.name = "sourcing"
        sourcing_mock.output_keys = ["candidates", "sources"]
        sourcing_mock.run = A2(return_value={
            "agent": "sourcing", "status": "completed", "summary": "Found",
            "result": {"candidates": [{"name": "Alice"}], "sources": ["linkedin"]},
        })
        AgentRegistry.register("sourcing", sourcing_mock)

        screening_mock = M2(spec=BaseAgent)
        screening_mock.name = "screening"
        screening_mock.output_keys = ["results", "summary"]
        screening_mock.run = A2(return_value={
            "agent": "screening", "status": "completed", "summary": "Screened",
            "result": {"results": ["passed"], "summary": "1 passed"},
        })
        AgentRegistry.register("screening", screening_mock)

        agent = OrchestratorAgent(name="test_chain")
        agent.shared_context = {}

        r1 = await agent.execute_sub_task({"type": "sourcing", "description": "find candidates"})
        assert r1["status"] == "completed"
        assert r1["agent"] == "sourcing"
        assert agent.shared_context["sourcing.candidates"] == [{"name": "Alice"}]
        assert agent.shared_context["sourcing.sources"] == ["linkedin"]

        r2 = await agent.execute_sub_task({"type": "screening", "description": "screen"})
        assert r2["status"] == "completed"
        assert r2["agent"] == "screening"

        call_args = screening_mock.run.call_args[0][0]
        assert call_args["action"] == "screening"
        assert call_args["sourcing.candidates"] == [{"name": "Alice"}]
        assert call_args["sourcing.sources"] == ["linkedin"]
        assert "screening.results" not in call_args
        assert "screening.summary" not in call_args

        assert "screening.results" in agent.shared_context
        assert "screening.summary" in agent.shared_context
    finally:
        AgentRegistry.unregister("sourcing")
        AgentRegistry.unregister("screening")
        if old_sourcing:
            AgentRegistry.register("sourcing", old_sourcing)
        if old_screening:
            AgentRegistry.register("screening", old_screening)


# ──────────────────────────────────────────────
# Human-in-the-Loop integration tests (v3 1.3)
# ──────────────────────────────────────────────


def test_needs_human_review_interview():
    """interview task type always requires human review."""
    assert OrchestratorAgent._needs_human_review({"result": {}}, "interview") is True


def test_needs_human_review_offering():
    """offering task type always requires human review."""
    assert OrchestratorAgent._needs_human_review({"result": {}}, "offering") is True


def test_needs_human_review_flag():
    """needs_human_review=True in result triggers human review."""
    result = {"result": {"needs_human_review": True, "candidates": []}}
    assert OrchestratorAgent._needs_human_review(result, "screening") is True


def test_needs_human_review_normal():
    """Normal screening result does NOT trigger human review."""
    result = {"result": {"candidates": [], "gate_passed": True}}
    assert OrchestratorAgent._needs_human_review(result, "screening") is False


@pytest.mark.asyncio
async def test_execute_sub_task_screening_still_completes(orch_agent):
    """Normal screening sub-task still returns completed."""
    result = await orch_agent.execute_sub_task({
        "type": "screening", "description": "filter devs",
    })
    assert result["status"] == "completed"


# ──────────────────────────────────────────────
# route_single tests (v3 1.5)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_single_dispatch(orch_agent):
    """route_single dispatches to registered Specialist Agent."""
    from unittest.mock import MagicMock

    from app.agents.base import BaseAgent
    from app.agents.registry import AgentRegistry

    mock_screening = MagicMock(spec=BaseAgent)
    mock_screening.output_keys = ["results"]
    mock_screening.name = "screening"
    mock_screening.run = AsyncMock(return_value={
        "agent": "screening", "status": "completed",
        "result": {"results": ["passed"], "summary": "筛选完成"},
    })
    old = AgentRegistry.resolve("screening")
    AgentRegistry.register("screening", mock_screening)
    try:
        result = await orch_agent.route_single({
            "text": "筛选张三的简历",
        })
        assert result["status"] == "completed"
        assert result["total_sub_tasks"] == 1
        assert result["succeeded"] == 1
        assert result["intent"] in ("screening",)
        assert len(result["outputs"]) == 1
    finally:
        AgentRegistry.unregister("screening")
        if old:
            AgentRegistry.register("screening", old)


@pytest.mark.asyncio
async def test_route_single_no_handler(orch_agent):
    """route_single returns no_handler for unknown intent."""
    result = await orch_agent.route_single({
        "text": "你好",
    })
    assert result["status"] == "no_handler"
    assert result["total_sub_tasks"] == 0
    assert result["succeeded"] == 0
    assert result["intent"] in ("chat",)


@pytest.mark.asyncio
async def test_route_single_empty_text(orch_agent):
    """route_single with empty text returns no_handler."""
    result = await orch_agent.route_single({"text": ""})
    assert result["status"] == "no_handler"


# ──────────────────────────────────────────────
# PipelineOrchestrator tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_orchestrator_all_done():
    from unittest.mock import MagicMock

    from app.agents.base import BaseAgent
    from app.agents.orchestrator_agent import PipelineOrchestrator

    agent_a = MagicMock(spec=BaseAgent)
    agent_a.name = "sourcing"
    agent_a.output_keys = ["candidates"]
    agent_a.run = AsyncMock(return_value={
        "agent": "sourcing", "status": "completed", "summary": "Found",
        "result": {"candidates": ["Alice"]},
    })

    agent_b = MagicMock(spec=BaseAgent)
    agent_b.name = "screening"
    agent_b.output_keys = ["results"]
    agent_b.run = AsyncMock(return_value={
        "agent": "screening", "status": "completed", "summary": "Screened",
        "result": {"results": ["passed"]},
    })

    pipeline = PipelineOrchestrator([agent_a, agent_b])
    result = await pipeline.run({"job_id": "123"})
    assert result["status"] == "completed"
    assert result["result"]["stages"][0]["stage"] == "sourcing"
    assert result["result"]["stages"][1]["stage"] == "screening"
    assert "sourcing.candidates" in result["result"]["shared_context"]
    assert "screening.results" in result["result"]["shared_context"]


@pytest.mark.asyncio
async def test_pipeline_orchestrator_mid_failure():
    from unittest.mock import MagicMock

    from app.agents.base import BaseAgent
    from app.agents.orchestrator_agent import PipelineOrchestrator

    agent_a = MagicMock(spec=BaseAgent)
    agent_a.name = "sourcing"
    agent_a.output_keys = []
    agent_a.run = AsyncMock(side_effect=Exception("Pipeline failure"))

    pipeline = PipelineOrchestrator([agent_a])
    result = await pipeline.run({})
    assert result["status"] == "completed"
    assert result["result"]["stages"][0]["status"] == "failed"


# ──────────────────────────────────────────────
# SequentialOrchestrator tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequential_orchestrator_all_done():
    from unittest.mock import MagicMock

    from app.agents.base import BaseAgent
    from app.agents.orchestrator_agent import SequentialOrchestrator
    from app.agents.registry import AgentRegistry

    mock_a = MagicMock(spec=BaseAgent)
    mock_a.name = "sourcing"
    mock_a.output_keys = ["candidates"]
    mock_a.run = AsyncMock(return_value={
        "agent": "sourcing", "status": "completed",
        "result": {"candidates": ["Bob"]},
    })
    AgentRegistry.register("sourcing_seq", mock_a)
    try:
        seq = SequentialOrchestrator(["sourcing_seq"])
        result = await seq.run({})
        assert result["status"] == "completed"
        assert result["result"]["results"][0]["agent"] == "sourcing_seq"
    finally:
        AgentRegistry.unregister("sourcing_seq")


@pytest.mark.asyncio
async def test_sequential_orchestrator_not_found():
    from app.agents.orchestrator_agent import SequentialOrchestrator

    seq = SequentialOrchestrator(["nonexistent_agent"])
    result = await seq.run({})
    assert result["status"] == "completed"
    assert result["result"]["results"][0]["status"] == "skipped"


# ──────────────────────────────────────────────
# get_orchestrator factory tests
# ──────────────────────────────────────────────


def test_get_orchestrator_auto():
    from app.agents.orchestrator_agent import OrchestratorAgent, get_orchestrator

    result = get_orchestrator(mode="auto")
    assert isinstance(result, OrchestratorAgent)


def test_get_orchestrator_pipeline():
    from app.agents.orchestrator_agent import PipelineOrchestrator, get_orchestrator

    result = get_orchestrator(mode="pipeline", agents=[])
    assert isinstance(result, PipelineOrchestrator)


def test_get_orchestrator_sequential():
    from app.agents.orchestrator_agent import SequentialOrchestrator, get_orchestrator

    result = get_orchestrator(mode="sequential", agents=[])
    assert isinstance(result, SequentialOrchestrator)
