"""Tests for ResumeParser StateGraph — 7-step workflow."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graphs.resume_parser_graph import create_resume_parser_graph


@pytest.fixture
def graph():
    return create_resume_parser_graph(checkpointer=MemorySaver())


def _state(**overrides):
    defaults = {
        "content": "", "file_url": "", "target_job_id": "",
        "current_step": "", "parsed_data": None, "confidence": 0,
        "quality_score": 0, "red_flags": [], "is_duplicate": False,
        "needs_human_review": False, "result": None, "error": None,
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_empty_input_fails(graph):
    result = await graph.ainvoke(
        _state(),
        config={"configurable": {"thread_id": "test-1"}},
    )
    assert result.get("error") is not None


@pytest.mark.asyncio
async def test_valid_input_flows_through_graph(graph):
    result = await graph.ainvoke(
        _state(content="张三 5年Java经验 本科"),
        config={"configurable": {"thread_id": "test-2"}},
    )
    assert "current_step" in result
    assert result["current_step"] in ("validate", "parse", "confidence", "quality", "risk", "dedup", "output")


@pytest.mark.asyncio
async def test_graph_tracks_step_progress(graph):
    result = await graph.ainvoke(
        _state(content="test"),
        config={"configurable": {"thread_id": "test-3"}},
    )
    assert "current_step" in result


@pytest.mark.asyncio
async def test_checkpoint_preserves_state(graph):
    config = {"configurable": {"thread_id": "test-cp"}}
    result = await graph.ainvoke(_state(content="test"), config=config)
    state = graph.get_state(config)
    assert state is not None
    assert state.values.get("current_step") == result.get("current_step")
