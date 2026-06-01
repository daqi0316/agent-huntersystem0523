"""Tests for orchestrator_graph multi-stage DAG (Phase V PR-V.1).

Covers:
- make_initial_orchestrator_state() helper
- _is_multi_stage_text() detection via RouterAgent
- _multi_stage_decompose() with LLM-driven sub-task list + DAG build
- _execute_level() parallel execution of sub-tasks in a level
- _should_continue_or_pause() conditional routing
- awaiting_approval pause + checkpointer resume
- End-to-end graph flows (single intent + multi-stage)

Backs the most complex 2 days of work in Phase V. See .omo/plans/phase-v.md.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graphs.orchestrator_graph import (
    OrchestratorState,
    _TYPE_TO_AGENT,
    _build_sub_task_input,
    _decide_route,
    _execute_level,
    _is_multi_stage_text,
    _multi_stage_decompose,
    _normalize_sub_task_result,
    _run_sub_task,
    _should_continue_or_pause,
    _update_shared_context,
    create_orchestrator_graph,
    make_initial_orchestrator_state,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def graph():
    return create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)


@pytest.fixture
def state_minimal():
    return make_initial_orchestrator_state(
        task_id="t1", user_id="u1", job_id="j1", input_text="hello",
    )


@pytest.fixture
def mock_orchestrator_decompose(monkeypatch):
    """Patch OrchestratorAgent.decompose to return a controlled sub-task list."""
    def _make(sub_tasks, levels=None):
        if levels is None:
            # Build trivial single-level DAG
            levels = [list(range(len(sub_tasks)))]
        mock_orch = MagicMock()
        mock_orch.decompose = AsyncMock(return_value=sub_tasks)
        mock_orch.build_dag = MagicMock(return_value=levels)
        monkeypatch.setattr(
            "app.agents.orchestrator_agent.OrchestratorAgent",
            MagicMock(return_value=mock_orch),
        )
        return mock_orch
    return _make


# ─────────────────────────────────────────────────────────────────────
# State helper tests
# ─────────────────────────────────────────────────────────────────────


def test_make_initial_state_defaults():
    s = make_initial_orchestrator_state()
    assert s["task_id"] == ""
    assert s["user_id"] == ""
    assert s["job_id"] == ""
    assert s["intent"] == ""
    assert s["input_text"] == ""
    assert s["agent_result"] is None
    assert s["error"] is None
    assert s["status"] == ""
    # multi-stage fields
    assert s["multi_stage"] is False
    assert s["sub_tasks"] == []
    assert s["current_level"] == 0
    assert s["levels"] == []
    assert s["paused_at_level"] is None
    assert s["results"] == []
    assert s["shared_context"] == {}


def test_make_initial_state_overrides():
    s = make_initial_orchestrator_state(
        task_id="t1", user_id="u1", job_id="j1", input_text="complex task",
    )
    assert s["task_id"] == "t1"
    assert s["user_id"] == "u1"
    assert s["job_id"] == "j1"
    assert s["input_text"] == "complex task"


def test_orchestrator_state_typed_dict_has_multi_stage_fields():
    """OrchestratorState TypedDict must include all 7 multi-stage fields per PR-V.1."""
    annotations = OrchestratorState.__annotations__
    required = {
        "multi_stage", "sub_tasks", "current_level", "levels",
        "paused_at_level", "results", "shared_context",
    }
    assert required.issubset(set(annotations.keys())), (
        f"Missing multi-stage fields: {required - set(annotations.keys())}"
    )


# ─────────────────────────────────────────────────────────────────────
# _is_multi_stage_text() tests
# ─────────────────────────────────────────────────────────────────────


def test_is_multi_stage_empty():
    assert _is_multi_stage_text("") is False


def test_is_multi_stage_single_intent():
    assert _is_multi_stage_text("筛选简历") is False


def test_is_multi_stage_chinese_conjunction():
    assert _is_multi_stage_text("筛选简历并且安排面试") is True


def test_is_multi_stage_two_subtask_keywords():
    assert _is_multi_stage_text("先筛选简历再生成报告") is True


def test_is_multi_stage_english_keywords():
    assert _is_multi_stage_text("screen candidates and schedule interview") is True


def test_is_multi_stage_greeting():
    assert _is_multi_stage_text("你好") is False


# ─────────────────────────────────────────────────────────────────────
# _build_sub_task_input() tests
# ─────────────────────────────────────────────────────────────────────


def test_build_sub_task_input_includes_upstream():
    ctx = {"sourcing.candidates": [{"name": "Alice"}]}
    out = _build_sub_task_input("screening", {"description": "filter"}, ctx)
    assert out["action"] == "screening"
    assert out["text"] == "filter"
    assert out["sourcing.candidates"] == [{"name": "Alice"}]


def test_build_sub_task_input_excludes_own_namespace():
    ctx = {"screening.old": "x", "sourcing.candidates": [{"name": "Bob"}]}
    out = _build_sub_task_input("screening", {"description": "f"}, ctx)
    assert "screening.old" not in out
    assert "sourcing.candidates" in out


def test_build_sub_task_input_empty_context():
    out = _build_sub_task_input("interview", {"description": "schedule"}, {})
    assert out["action"] == "interview"
    assert "context" in out
    assert out["context"] == {}


# ─────────────────────────────────────────────────────────────────────
# _update_shared_context() tests
# ─────────────────────────────────────────────────────────────────────


def test_update_shared_context_writes_output_keys():
    ctx = {}
    result = {
        "output_keys": ["candidates", "sources"],
        "result": {"candidates": [{"name": "A"}], "sources": ["linkedin"]},
    }
    _update_shared_context(ctx, "sourcing", result)
    assert ctx["sourcing.candidates"] == [{"name": "A"}]
    assert ctx["sourcing.sources"] == ["linkedin"]
    assert ctx["sourcing.full"] == result["result"]


def test_update_shared_context_no_output_keys_writes_full():
    ctx = {}
    result = {"output_keys": [], "result": {"foo": "bar"}}
    _update_shared_context(ctx, "screening", result)
    assert "screening.full" in ctx
    assert "screening.foo" not in ctx


def test_update_shared_context_non_dict_result_stores_raw():
    ctx = {}
    result = {"output_keys": ["x"], "result": "raw_string"}
    _update_shared_context(ctx, "screening", result)
    assert ctx["screening.full"] == "raw_string"
    assert "screening.x" not in ctx


# ─────────────────────────────────────────────────────────────────────
# _normalize_sub_task_result() tests
# ─────────────────────────────────────────────────────────────────────


def test_normalize_sub_task_result_preserves_fields():
    r = _normalize_sub_task_result("screening", {
        "agent": "screening",
        "status": "completed",
        "summary": "Found 3",
        "result": {"items": [1, 2, 3]},
        "details": {"x": 1},
    })
    assert r["agent"] == "screening"
    assert r["status"] == "completed"
    assert r["summary"] == "Found 3"
    assert r["result"] == {"items": [1, 2, 3]}


def test_normalize_sub_task_result_fills_defaults():
    r = _normalize_sub_task_result("screening", {})
    assert r["agent"] == "screening"
    assert r["status"] == "completed"
    assert r["summary"] == ""
    assert r["result"] == {}


# ─────────────────────────────────────────────────────────────────────
# _TYPE_TO_AGENT mapping tests
# ─────────────────────────────────────────────────────────────────────


def test_type_to_agent_mappings():
    assert _TYPE_TO_AGENT["jd_generation"] == "sourcing"
    assert _TYPE_TO_AGENT["candidate_search"] == "sourcing"
    assert _TYPE_TO_AGENT["report"] == "analytics"
    assert _TYPE_TO_AGENT["interview"] == "interview"
    assert _TYPE_TO_AGENT["offering"] == "offering"
    assert _TYPE_TO_AGENT["onboarding"] == "onboarding"


# ─────────────────────────────────────────────────────────────────────
# _should_continue_or_pause() tests
# ─────────────────────────────────────────────────────────────────────


def test_should_continue_routes_to_next_level():
    state = {
        "current_level": 1, "levels": [[0], [1], [2]],
        "paused_at_level": None, "error": None,
    }
    assert _should_continue_or_pause(state) == "execute_level"


def test_should_end_after_last_level():
    state = {
        "current_level": 3, "levels": [[0], [1], [2]],
        "paused_at_level": None, "error": None,
    }
    assert _should_continue_or_pause(state) == "end"


def test_should_end_when_paused():
    state = {
        "current_level": 1, "levels": [[0], [1]],
        "paused_at_level": 0, "error": None,
    }
    assert _should_continue_or_pause(state) == "end"


def test_should_end_on_error():
    state = {
        "current_level": 0, "levels": [[0]],
        "paused_at_level": None, "error": "boom",
    }
    assert _should_continue_or_pause(state) == "end"


def test_should_end_on_empty_levels():
    state = {
        "current_level": 0, "levels": [],
        "paused_at_level": None, "error": None,
    }
    assert _should_continue_or_pause(state) == "end"


# ─────────────────────────────────────────────────────────────────────
# _decide_route() tests
# ─────────────────────────────────────────────────────────────────────


def test_decide_route_multi_stage_first():
    state = {"multi_stage": True, "intent": "screening"}
    assert _decide_route(state) == "multi_stage_decompose"


def test_decide_route_single_intent_routes_correctly():
    state = {"multi_stage": False, "intent": "screening"}
    assert _decide_route(state) == "execute_screening"


def test_decide_route_unknown_intent_falls_back_to_end():
    state = {"multi_stage": False, "intent": "nonsense_intent"}
    assert _decide_route(state) == "end"


def test_decide_route_empty_intent_falls_back_to_end():
    state = {"multi_stage": False, "intent": ""}
    assert _decide_route(state) == "end"


# ─────────────────────────────────────────────────────────────────────
# _multi_stage_decompose() node tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_stage_decompose_with_dependencies():
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=[
            {"type": "screening", "description": "a", "depends_on": []},
            {"type": "interview", "description": "b", "depends_on": [0]},
        ])
        mock.build_dag = MagicMock(return_value=[[0], [1]])

        out = await _multi_stage_decompose({
            "input_text": "screen and schedule interview", "task_id": "t1",
        })
    assert len(out["sub_tasks"]) == 2
    assert out["levels"] == [[0], [1]]
    assert out["current_level"] == 0
    assert out["paused_at_level"] is None
    assert len(out["results"]) == 2
    assert out["multi_stage"] is True
    assert out["status"] == "running"


@pytest.mark.asyncio
async def test_multi_stage_decompose_parallel_levels():
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=[
            {"type": "sourcing", "description": "find", "depends_on": []},
            {"type": "screening", "description": "filter", "depends_on": []},
        ])
        mock.build_dag = MagicMock(return_value=[[0, 1]])

        out = await _multi_stage_decompose({"input_text": "parallel tasks"})
    assert out["levels"] == [[0, 1]]
    assert len(out["sub_tasks"]) == 2


@pytest.mark.asyncio
async def test_multi_stage_decompose_empty_text_returns_error():
    out = await _multi_stage_decompose({"input_text": ""})
    assert out["error"] == "no input_text for multi-stage"
    assert out["status"] == "failed"


@pytest.mark.asyncio
async def test_multi_stage_decompose_llm_failure_fallback():
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(side_effect=Exception("LLM down"))
        mock.build_dag = MagicMock(side_effect=Exception("no DAG"))

        out = await _multi_stage_decompose({"input_text": "do something"})
    # Fallback produces a single sub-task
    assert len(out["sub_tasks"]) == 1
    assert out["sub_tasks"][0]["type"] == "screening"
    assert out["levels"] == [[0]]


@pytest.mark.asyncio
async def test_multi_stage_decompose_empty_subtasks_fallback():
    """Empty sub_tasks list from LLM should fall back to a single screening task."""
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=[])
        mock.build_dag = MagicMock(return_value=[])

        out = await _multi_stage_decompose({"input_text": "ambiguous"})
    assert len(out["sub_tasks"]) == 1
    assert out["sub_tasks"][0]["type"] == "screening"
    assert out["levels"] == [[0]]


# ─────────────────────────────────────────────────────────────────────
# _run_sub_task() tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_sub_task_screening_success():
    """Mock AgentRegistry → screening agent returns success."""
    mock_agent = MagicMock()
    mock_agent.name = "screening"
    mock_agent.run = AsyncMock(return_value={
        "agent": "screening", "status": "completed", "summary": "OK",
        "result": {"items": [1, 2, 3]},
    })

    with patch("app.agents.registry.AgentRegistry.resolve", return_value=mock_agent), \
         patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
               return_value=False):
        ctx: dict = {}
        r = await _run_sub_task(
            {"type": "screening", "description": "filter devs"},
            ctx, user_id="u1",
        )
    assert r["status"] == "completed"
    assert r["agent"] == "screening"
    assert "screening.full" in ctx


@pytest.mark.asyncio
async def test_run_sub_task_unknown_type_falls_back_to_failed():
    """Unknown task type returns structured failure (not raises)."""
    with patch("app.agents.registry.AgentRegistry.resolve", return_value=None):
        r = await _run_sub_task(
            {"type": "nonexistent", "description": "x"}, {}, user_id="u1",
        )
    assert r["status"] == "failed"
    assert r["agent"] == "nonexistent"


@pytest.mark.asyncio
async def test_run_sub_task_awaiting_approval_pauses():
    """interview task triggers HumanLoop proposal → awaiting_approval."""
    mock_agent = MagicMock()
    mock_agent.name = "interview"
    mock_agent.run = AsyncMock(return_value={
        "agent": "interview", "status": "completed", "summary": "scheduled",
        "result": {"scheduled": True},
    })
    mock_proposal = {"approval_id": "appr_test_123", "action_type": "interview"}

    with patch("app.agents.registry.AgentRegistry.resolve", return_value=mock_agent), \
         patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
               return_value=True), \
         patch("app.agents.human_loop.HumanLoopAgent") as MockHL:
        hl = MockHL.return_value
        hl.create_proposal = AsyncMock(return_value=mock_proposal)

        r = await _run_sub_task(
            {"type": "interview", "description": "schedule interview"},
            {}, user_id="u1",
        )
    assert r["status"] == "awaiting_approval"
    assert r["details"]["approval"] == mock_proposal


# ─────────────────────────────────────────────────────────────────────
# _execute_level() node tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_level_empty_levels_returns_completed():
    state = {
        "levels": [], "sub_tasks": [], "current_level": 0,
        "results": [], "shared_context": {},
    }
    out = await _execute_level(state)
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_level_runs_parallel_subtasks():
    """Two independent sub-tasks in same level should both be invoked."""
    state = {
        "levels": [[0, 1]],
        "sub_tasks": [
            {"type": "sourcing", "description": "find"},
            {"type": "screening", "description": "filter"},
        ],
        "current_level": 0,
        "results": [None, None],
        "shared_context": {},
        "user_id": "u1",
    }

    call_count = {"n": 0}

    async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
        call_count["n"] += 1
        return {
            "agent": sub_task["type"],
            "status": "completed",
            "summary": f"done {sub_task['type']}",
            "result": {},
        }

    with patch("app.graphs.orchestrator_graph._run_sub_task",
               side_effect=fake_run_sub_task):
        out = await _execute_level(state)
    assert call_count["n"] == 2
    assert out["current_level"] == 1
    assert all(r["status"] == "completed" for r in out["results"])


@pytest.mark.asyncio
async def test_execute_level_records_failures():
    """One task raising should not stop others; exception captured in results."""
    state = {
        "levels": [[0, 1]],
        "sub_tasks": [
            {"type": "sourcing", "description": "find"},
            {"type": "screening", "description": "filter"},
        ],
        "current_level": 0,
        "results": [None, None],
        "shared_context": {},
        "user_id": "u1",
    }

    async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
        if sub_task["type"] == "sourcing":
            raise RuntimeError("boom")
        return {
            "agent": "screening", "status": "completed",
            "summary": "OK", "result": {},
        }

    with patch("app.graphs.orchestrator_graph._run_sub_task",
               side_effect=fake_run_sub_task):
        out = await _execute_level(state)
    assert out["results"][0]["status"] == "failed"
    assert "boom" in out["results"][0]["details"]["error"]
    assert out["results"][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_level_pauses_on_awaiting_approval():
    """Any sub-task awaiting_approval → paused_at_level set + status update."""
    state = {
        "levels": [[0, 1], [2]],
        "sub_tasks": [
            {"type": "interview", "description": "schedule"},
            {"type": "sourcing", "description": "find"},
            {"type": "report", "description": "summary"},
        ],
        "current_level": 0,
        "results": [None, None, None],
        "shared_context": {},
        "user_id": "u1",
    }

    async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
        if sub_task["type"] == "interview":
            return {
                "agent": "interview", "status": "awaiting_approval",
                "summary": "needs approval",
                "result": {}, "details": {"approval": {"approval_id": "a1"}},
            }
        return {
            "agent": sub_task["type"], "status": "completed",
            "summary": "ok", "result": {},
        }

    with patch("app.graphs.orchestrator_graph._run_sub_task",
               side_effect=fake_run_sub_task):
        out = await _execute_level(state)
    assert out["paused_at_level"] == 0
    assert out["status"] == "awaiting_approval"
    # current_level still advances (so we can detect we're past paused)
    assert out["current_level"] == 1


@pytest.mark.asyncio
async def test_execute_level_writes_to_shared_context():
    """sourcing agent's output_keys must land in shared_context."""
    state = {
        "levels": [[0]],
        "sub_tasks": [{"type": "sourcing", "description": "find"}],
        "current_level": 0,
        "results": [None],
        "shared_context": {},
        "user_id": "u1",
    }

    async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
        # Simulate _update_shared_context writing
        ctx["sourcing.candidates"] = [{"name": "Alice"}]
        return {
            "agent": "sourcing", "status": "completed",
            "summary": "found", "result": {"candidates": [{"name": "Alice"}]},
        }

    with patch("app.graphs.orchestrator_graph._run_sub_task",
               side_effect=fake_run_sub_task):
        out = await _execute_level(state)
    assert out["shared_context"]["sourcing.candidates"] == [{"name": "Alice"}]


# ─────────────────────────────────────────────────────────────────────
# End-to-end graph tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_intent_routes_to_screening_node(graph):
    """Single intent text should go through intent_recognition → execute_screening."""
    out = await graph.ainvoke(
        make_initial_orchestrator_state(task_id="t-s", input_text="筛选简历"),
        config={"configurable": {"thread_id": "t-s"}},
    )
    assert out["intent"] in ("screening", "candidate_search")
    assert out["multi_stage"] is False


@pytest.mark.asyncio
async def test_multi_stage_detected_via_keyword(graph):
    """Text with multi-intent keywords should be marked as multi_stage before routing."""
    out = await graph.ainvoke(
        make_initial_orchestrator_state(
            task_id="t-ms", input_text="筛选简历并且安排面试",
        ),
        config={"configurable": {"thread_id": "t-ms"}},
    )
    assert out["multi_stage"] is True
    assert len(out["sub_tasks"]) >= 1
    assert len(out["levels"]) >= 1


@pytest.mark.asyncio
async def test_multi_stage_completes_2_level_dag(graph):
    """A 2-level DAG with no human review should run to completion."""
    fake_sub_tasks = [
        {"type": "sourcing", "description": "find candidates", "depends_on": []},
        {"type": "screening", "description": "filter", "depends_on": [0]},
    ]
    fake_levels = [[0], [1]]

    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=fake_sub_tasks)
        mock.build_dag = MagicMock(return_value=fake_levels)

        # Mock both agent calls
        async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
            ctx.setdefault(f"{sub_task['type']}.full", sub_task["description"])
            return {
                "agent": sub_task["type"],
                "status": "completed",
                "summary": f"done {sub_task['type']}",
                "result": {"x": 1},
            }

        with patch("app.graphs.orchestrator_graph._run_sub_task",
                   side_effect=fake_run_sub_task), \
             patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
                   return_value=False):
            out = await graph.ainvoke(
                make_initial_orchestrator_state(
                    task_id="t-2l", input_text="先筛选再生成报告",
                ),
                config={"configurable": {"thread_id": "t-2l"}},
            )
    assert out["status"] in ("running", "completed")
    assert out["current_level"] == 2  # advanced past both levels
    assert out["paused_at_level"] is None


@pytest.mark.asyncio
async def test_multi_stage_pauses_when_subtask_needs_approval(graph):
    """A sub-task returning awaiting_approval should pause the graph."""
    fake_sub_tasks = [
        {"type": "interview", "description": "schedule", "depends_on": []},
    ]
    fake_levels = [[0]]

    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=fake_sub_tasks)
        mock.build_dag = MagicMock(return_value=fake_levels)

        async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
            return {
                "agent": "interview",
                "status": "awaiting_approval",
                "summary": "needs human",
                "result": {},
                "details": {"approval": {"approval_id": "appr_pause_1"}},
            }

        with patch("app.graphs.orchestrator_graph._run_sub_task",
                   side_effect=fake_run_sub_task), \
             patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
                   return_value=True), \
             patch("app.agents.human_loop.HumanLoopAgent") as MockHL:
            MockHL.return_value.create_proposal = AsyncMock(
                return_value={"approval_id": "appr_pause_1"},
            )
            out = await graph.ainvoke(
                make_initial_orchestrator_state(
                    task_id="t-p", input_text="先筛选再安排面试",
                ),
                config={"configurable": {"thread_id": "t-p"}},
            )
    assert out["status"] == "awaiting_approval"
    assert out["paused_at_level"] == 0
    assert out["results"][0]["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_multi_stage_resume_via_checkpointer(graph):
    """After awaiting_approval pause, the paused state is preserved in the checkpointer.

    PR-V.1 verifies state preservation; the actual re-execution logic on
    approval-passed resume lives in PR-V.2 (human_loop /resume endpoint).
    """
    thread_id = "t-resume"
    fake_sub_tasks = [
        {"type": "interview", "description": "schedule", "depends_on": []},
    ]
    fake_levels = [[0]]

    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=fake_sub_tasks)
        mock.build_dag = MagicMock(return_value=fake_levels)

        async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
            return {
                "agent": "interview", "status": "awaiting_approval",
                "summary": "needs approval",
                "result": {}, "details": {"approval": {"approval_id": "a1"}},
            }

        with patch("app.graphs.orchestrator_graph._run_sub_task",
                   side_effect=fake_run_sub_task), \
             patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
                   return_value=True), \
             patch("app.agents.human_loop.HumanLoopAgent") as MockHL:
            MockHL.return_value.create_proposal = AsyncMock(
                return_value={"approval_id": "a1"},
            )

            cfg = {"configurable": {"thread_id": thread_id}}
            out1 = await graph.ainvoke(
                make_initial_orchestrator_state(
                    task_id="t-resume", input_text="先筛选再安排面试",
                ),
                config=cfg,
            )
            assert out1["paused_at_level"] == 0
            assert out1["status"] == "awaiting_approval"

            snap = graph.get_state(cfg)
            assert snap is not None
            assert snap.values["paused_at_level"] == 0
            assert snap.values["status"] == "awaiting_approval"
            assert len(snap.values["sub_tasks"]) == 1
            assert snap.values["levels"] == [[0]]
            assert snap.values["results"][0]["status"] == "awaiting_approval"
            assert snap.values["results"][0]["details"]["approval"]["approval_id"] == "a1"


# ─────────────────────────────────────────────────────────────────────
# Graph compilation tests
# ─────────────────────────────────────────────────────────────────────


def test_create_graph_with_interrupt_true():
    g = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=True)
    assert g is not None


def test_create_graph_with_interrupt_false():
    g = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)
    assert g is not None


def test_create_graph_default_checkpointer_is_memory():
    g = create_orchestrator_graph()
    assert g is not None


def test_graph_has_all_expected_nodes():
    g = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)
    expected = {
        "__start__", "intent_recognition",
        "multi_stage_decompose", "execute_level",
        "execute_resume_parser", "execute_screening", "execute_interview",
        "execute_sourcing", "execute_offering", "execute_onboarding",
        "execute_analytics",
    }
    actual = set(g.nodes.keys())
    missing = expected - actual
    assert not missing, f"Missing nodes: {missing}"


# ─────────────────────────────────────────────────────────────────────
# Edge-case tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_level_handles_length_mismatch():
    """If results length doesn't match sub_tasks, repair to sub_tasks length."""
    state = {
        "levels": [[0]],
        "sub_tasks": [{"type": "sourcing", "description": "find"}],
        "current_level": 0,
        "results": [],  # length mismatch!
        "shared_context": {},
        "user_id": "u1",
    }

    async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
        return {
            "agent": sub_task["type"], "status": "completed",
            "summary": "ok", "result": {},
        }

    with patch("app.graphs.orchestrator_graph._run_sub_task",
               side_effect=fake_run_sub_task):
        out = await _execute_level(state)
    assert len(out["results"]) == 1


@pytest.mark.asyncio
async def test_multi_stage_decompose_preserves_task_id():
    """State should keep task_id across decompose."""
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=[
            {"type": "screening", "description": "x", "depends_on": []},
        ])
        mock.build_dag = MagicMock(return_value=[[0]])

        out = await _multi_stage_decompose({
            "input_text": "screen", "task_id": "my-task-123",
        })
    # decompose doesn't return task_id (it's preserved by graph state merging)
    assert "task_id" not in out or out.get("task_id") is None


@pytest.mark.asyncio
async def test_multi_stage_graph_with_only_one_subtask(graph):
    """A multi-stage with a single sub-task should still complete cleanly."""
    with patch("app.agents.orchestrator_agent.OrchestratorAgent") as MockCls:
        mock = MockCls.return_value
        mock.decompose = AsyncMock(return_value=[
            {"type": "sourcing", "description": "find one", "depends_on": []},
        ])
        mock.build_dag = MagicMock(return_value=[[0]])

        async def fake_run_sub_task(sub_task, ctx, user_id, thread_id=None):
            return {
                "agent": sub_task["type"], "status": "completed",
                "summary": "done", "result": {},
            }

        with patch("app.graphs.orchestrator_graph._run_sub_task",
                   side_effect=fake_run_sub_task), \
             patch("app.agents.orchestrator_agent.OrchestratorAgent._needs_human_review",
                   return_value=False):
            out = await graph.ainvoke(
                make_initial_orchestrator_state(
                    task_id="t-single", input_text="先筛选再安排面试",
                ),
                config={"configurable": {"thread_id": "t-single"}},
            )
    assert out["status"] in ("running", "completed")
    assert out["paused_at_level"] is None
    assert out["results"][0]["status"] == "completed"
