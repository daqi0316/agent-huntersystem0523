"""AggregatorAgent unit tests — mocked LLM."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.aggregator import AggregatorAgent, DIMENSION_PROMPTS
from app.agents.single_agent import SingleAgent

pytestmark = pytest.mark.asyncio


@pytest.fixture
def llm_patch():
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.aggregator.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


@pytest.mark.asyncio
async def test_init_default_state():
    agent = AggregatorAgent(name="test_agg")
    assert agent.name == "test_agg"
    assert agent.workers == []
    assert agent._llm is None


@pytest.mark.asyncio
async def test_llm_lazy_init(llm_patch):
    agent = AggregatorAgent()
    assert agent._llm is None
    llm = agent.llm
    assert llm is llm_patch
    assert agent._llm is llm


@pytest.mark.asyncio
async def test_add_worker():
    agent = AggregatorAgent()
    worker = SingleAgent(name="test")
    agent.add_worker(worker)
    assert len(agent.workers) == 1
    assert agent.workers[0] is worker


@pytest.mark.asyncio
async def test_run_parallel_uses_all_dimensions_by_default(llm_patch):
    llm_patch.chat.return_value = '{"dimension": "technical", "overall": 8, "scores": {}, "summary": "", "highlights": [], "concerns": []}'
    agent = AggregatorAgent()
    results = await agent.run_parallel("Candidate info text")
    assert len(results) == len(DIMENSION_PROMPTS)
    assert llm_patch.chat.await_count == len(DIMENSION_PROMPTS)


@pytest.mark.asyncio
async def test_run_parallel_uses_specified_dimensions(llm_patch):
    llm_patch.chat.return_value = '{"dimension": "test", "overall": 7, "scores": {}, "summary": "", "highlights": [], "concerns": []}'
    agent = AggregatorAgent()
    results = await agent.run_parallel("Info", dimensions=["technical", "behavioral"])
    assert len(results) == 2


@pytest.mark.asyncio
async def test_run_parallel_handles_llm_parse_failure(llm_patch):
    llm_patch.chat.return_value = "broken json{{{"
    agent = AggregatorAgent()
    results = await agent.run_parallel("Info", dimensions=["technical"])
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_aggregate_returns_consensus(llm_patch):
    llm_patch.chat.return_value = (
        '{"final_score": 8, "dimension_scores": {"technical": 8}, '
        '"consensus_summary": "good", "top_strengths": [], '
        '"top_concerns": [], "recommendation": "hire", "next_steps": []}'
    )
    agent = AggregatorAgent()
    dim_results = [{"dimension": "technical", "overall": 8}]
    result = await agent.aggregate(dim_results)
    assert result["consensus"]["final_score"] == 8
    assert result["total_dimensions"] == 1
    assert result["dimension_results"] == dim_results


@pytest.mark.asyncio
async def test_aggregate_handles_parse_failure(llm_patch):
    llm_patch.chat.return_value = "{{{"
    agent = AggregatorAgent()
    result = await agent.aggregate([{"dummy": True}])
    assert "error" in result["consensus"]


@pytest.mark.asyncio
async def test_run_full_flow(llm_patch):
    """Aggregator.run() executes run_parallel + aggregate."""
    mock_returns = [
        '{"dimension": "technical", "overall": 8, "scores": {}, "summary": "", "highlights": [], "concerns": []}',
        '{"dimension": "behavioral", "overall": 7, "scores": {}, "summary": "", "highlights": [], "concerns": []}',
        '{"final_score": 7.5, "dimension_scores": {"technical": 8, "behavioral": 7}, "consensus_summary": "ok", "top_strengths": [], "top_concerns": [], "recommendation": "consider", "next_steps": []}',
    ]
    llm_patch.chat.side_effect = mock_returns
    agent = AggregatorAgent()
    result = await agent.run({
        "candidate_info": "John, Python expert, 5yrs",
        "dimensions": ["technical", "behavioral"],
    })
    assert result["agent"] == "aggregator"
    assert result["status"] == "completed"
    assert result["total_dimensions"] == 2
    assert result["consensus"]["final_score"] == 7.5
