"""Tests for _adapt_graph_result_to_legacy() — Phase V scaffolding.

Adapter maps new orchestrator_graph.ainvoke() output (OrchestratorState) to
legacy OrchestratorAgent.route_single() return format so existing
_build_approval_response() and _summarize_orch_result() keep working.

See .omo/plans/phase-v.md PR-V.3 for full migration context.
"""

from app.services.agent_service import _adapt_graph_result_to_legacy


def test_adapt_completed_intent():
    state = {
        "intent": "screening",
        "status": "completed",
        "agent_result": {"summary": "Found 3 candidates", "items": [1, 2, 3]},
        "error": None,
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["agent"] == "screening"
    assert result["status"] == "completed"
    assert result["summary"] == "Found 3 candidates"
    assert result["result"] == {"summary": "Found 3 candidates", "items": [1, 2, 3]}


def test_adapt_no_handler_intent():
    state = {
        "intent": "chat",
        "status": "no_handler",
        "agent_result": None,
        "error": None,
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["agent"] == "chat"
    assert result["status"] == "no_handler"
    assert result["summary"] == ""


def test_adapt_error_state():
    state = {
        "intent": "sourcing",
        "status": "failed",
        "agent_result": None,
        "error": "LLM timeout",
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["agent"] == "sourcing"
    assert result["status"] == "failed"
    assert "LLM timeout" in result["summary"]
    assert result["result"] == {}


def test_adapt_missing_intent_defaults_to_unknown():
    state = {"status": "completed", "agent_result": {"summary": "ok"}, "error": None}
    result = _adapt_graph_result_to_legacy(state)
    assert result["agent"] == "unknown"


def test_adapt_unknown_status_normalized_to_completed():
    state = {
        "intent": "interview",
        "status": "running",  # not in legacy allowed set
        "agent_result": {"summary": "in progress"},
        "error": None,
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["status"] == "completed"


def test_adapt_awaiting_approval_passthrough():
    state = {
        "intent": "interview",
        "status": "awaiting_approval",
        "agent_result": {"approval_id": "appr_123"},
        "error": None,
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["status"] == "awaiting_approval"


def test_adapt_non_dict_agent_result_safe():
    state = {
        "intent": "screening",
        "status": "completed",
        "agent_result": "raw string",  # not a dict
        "error": None,
    }
    result = _adapt_graph_result_to_legacy(state)
    assert result["summary"] == ""
    assert result["result"] == "raw string"
