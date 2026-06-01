"""Tests for ScreeningAgent — Pipeline + Aggregator wrapper (mocked)."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.agents.screening_agent import (
    ScreeningAgent,
    SCREENING_DIMENSIONS,
    RISK_TAGS,
)


@pytest.fixture
def agent():
    return ScreeningAgent()


MOCK_PIPELINE_RESULT = {
    "final_output": {
        "parsed_resume": {"experience_years": 5, "skills": ["Python", "Java"]},
        "match_result": {
            "overall_score": 85,
            "recommendation": "strong_hire",
            "strengths": ["Python 熟练"],
            "weaknesses": [],
        },
        "gate_result": {
            "needs_human_review": False,
            "gate_summary": "通过初筛",
        },
        "final_score": 85,
        "gate_passed": True,
    }
}


def test_init(agent):
    assert agent.name == "screening"
    assert agent._pipeline is None
    assert agent._aggregator is None


def test_pipeline_lazy(agent):
    p = agent.pipeline
    assert p is not None
    assert agent._pipeline is p


def test_aggregator_lazy(agent):
    a = agent.aggregator
    assert a is not None
    assert agent._aggregator is a


@pytest.mark.asyncio
async def test_screen_basic(agent):
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(return_value=MOCK_PIPELINE_RESULT)
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.screen(
            candidate_id="c-1", job_id="j-1",
            resume_text="张三，5 年 Python 开发经验",
            job_requirements="Python 开发，3 年以上经验",
        )
    assert result["candidate_id"] == "c-1"
    assert result["job_id"] == "j-1"
    assert result["overall_score"] == 85
    assert result["gate_passed"] is True
    assert "risks" in result


@pytest.mark.asyncio
async def test_screen_returns_all_keys(agent):
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(return_value=MOCK_PIPELINE_RESULT)
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.screen("c-2", "j-2", "简历文本", "职位要求")
    expected_keys = {
        "candidate_id", "job_id", "overall_score",
        "parsed_resume", "dimensions", "gate_passed",
        "needs_human_review", "risks", "strengths",
        "weaknesses", "recommendation", "summary",
    }
    assert expected_keys.issubset(result.keys())


@pytest.mark.asyncio
async def test_multi_evaluate_default_dims(agent):
    mock_agg = MagicMock()
    mock_agg.run = AsyncMock(return_value={"dimension_results": []})
    agent._aggregator = mock_agg
    with patch.object(ScreeningAgent, "aggregator", new_callable=PropertyMock, return_value=mock_agg):
        result = await agent.multi_evaluate("候选人有 5 年经验")
    assert "dimension_results" in result


@pytest.mark.asyncio
async def test_multi_evaluate_custom_dims(agent):
    mock_agg = MagicMock()
    mock_agg.run = AsyncMock(return_value={"dimension_results": []})
    agent._aggregator = mock_agg
    with patch.object(ScreeningAgent, "aggregator", new_callable=PropertyMock, return_value=mock_agg):
        result = await agent.multi_evaluate("test", dimensions=["technical", "experience"])
    assert "dimension_results" in result


@pytest.mark.asyncio
async def test_batch_screen(agent):
    candidates = [
        {"id": "c-1", "job_id": "j-1", "resume_text": "张三，5 年经验", "job_requirements": "3 年经验"},
        {"id": "c-2", "job_id": "j-1", "resume_text": "李四，1 年经验", "job_requirements": "3 年经验"},
    ]
    with patch.object(agent, "screen") as mock_screen:
        mock_screen.side_effect = [
            {"candidate_id": "c-1", "overall_score": 85, "recommendation": "推荐", "risks": [], "gate_passed": True},
            {"candidate_id": "c-2", "overall_score": 45, "recommendation": "不推荐", "risks": ["gap"], "gate_passed": False},
        ]
        result = await agent.batch_screen(candidates)
    assert result["total"] == 2
    assert len(result["results"]) == 2
    assert result["passed"] == 1
    assert "comparison_matrix" in result


@pytest.mark.asyncio
async def test_batch_screen_with_error(agent):
    with patch.object(agent, "screen") as mock_screen:
        mock_screen.side_effect = ValueError("模拟错误")
        result = await agent.batch_screen([{"id": "c-1", "job_id": "j-1", "resume_text": "", "job_requirements": ""}])
    assert result["total"] == 1
    assert "error" in result["results"][0]


def test_detect_risks_short_experience(agent):
    risks = agent._detect_risks({"experience_years": 1, "skills": []}, {})
    types = [r["type"] for r in risks]
    assert "gap" in types


def test_detect_risks_skill_inflation(agent):
    skills = [f"skill-{i}" for i in range(20)]
    risks = agent._detect_risks({"experience_years": 5, "skills": skills}, {})
    types = [r["type"] for r in risks]
    assert "skill_inflation" in types


def test_detect_risks_job_hopping(agent):
    risks = agent._detect_risks(
        {"experience_years": 5, "skills": []},
        {"recommendation": "待定"},
    )
    types = [r["type"] for r in risks]
    assert "job_hopping" in types


def test_no_risks_clean_profile(agent):
    risks = agent._detect_risks(
        {"experience_years": 5, "skills": ["Python", "Java"]},
        {"recommendation": "strong_hire"},
    )
    assert len(risks) == 0


def test_risk_tags_completeness():
    assert "gap" in RISK_TAGS
    assert "job_hopping" in RISK_TAGS
    assert "skill_inflation" in RISK_TAGS
    assert "salary_mismatch" in RISK_TAGS


def test_screening_dimensions():
    assert "technical" in SCREENING_DIMENSIONS
    assert "experience" in SCREENING_DIMENSIONS
    assert len(SCREENING_DIMENSIONS) == 6


# ── _estimate_years ──


def test_estimate_years_explicit_pattern():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("5年软件开发经验") == 5.0


def test_estimate_years_work_pattern():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("8年工作经验") == 8.0


def test_estimate_years_work_before():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("从事工作12年") == 12.0


def test_estimate_years_experience_before():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("丰富经验3年") == 3.0


def test_estimate_years_from_date_ranges():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("2018年-2022年  ABC Corp\n2022年-2024年  XYZ Corp") == 6.0


def test_estimate_years_date_ranges_no_match():
    from app.agents.screening_agent import _estimate_years

    assert _estimate_years("some text without year info") == 3.0


# ── screen LLM fallback path ──


@pytest.mark.asyncio
async def test_screen_llm_failure_fallback(agent):
    """screen() falls back to rule-based when pipeline raises."""
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(side_effect=Exception("LLM down"))
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.screen("c-3", "j-3", "python java react 3年经验", "python developer")
    assert result["candidate_id"] == "c-3"
    assert result["overall_score"] > 0  # rule-based fallback
    assert result["gate_passed"] is False  # rule fallback low match
    assert result["needs_human_review"] is True


@pytest.mark.asyncio
async def test_screen_llm_failure_low_match(agent):
    """Rule fallback with low keyword match."""
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(side_effect=Exception("LLM down"))
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.screen("c-4", "j-4", "unrelated text", "rare requirement")
    assert result["overall_score"] <= 40
    assert result["recommendation"] == "待定"


@pytest.mark.asyncio
async def test_multi_evaluate_extra_dims(agent):
    """multi_evaluate adds placeholder results for dimensions beyond 3."""
    mock_agg = MagicMock()
    mock_agg.run = AsyncMock(return_value={"dimension_results": [{"dimension": "technical"}]})
    agent._aggregator = mock_agg
    with patch.object(ScreeningAgent, "aggregator", new_callable=PropertyMock, return_value=mock_agg):
        result = await agent.multi_evaluate("test", dimensions=["technical", "skills", "culture", "potential"])
    assert len(result["dimension_results"]) == 2  # 1 from mock agg + 1 extra dim ("potential")


@pytest.mark.asyncio
async def test_run_default_action(agent):
    """run() with no action defaults to screen."""
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(return_value=MOCK_PIPELINE_RESULT)
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.run({"candidate_id": "c-1", "job_id": "j-1",
                                   "resume_text": "test", "job_requirements": "test"})
    assert result["status"] == "completed"
    assert result["result"]["candidate_id"] == "c-1"


@pytest.mark.asyncio
async def test_run_action_screen(agent):
    mock_pipe = MagicMock()
    mock_pipe.run = AsyncMock(return_value=MOCK_PIPELINE_RESULT)
    agent._pipeline = mock_pipe
    with patch.object(ScreeningAgent, "pipeline", new_callable=PropertyMock, return_value=mock_pipe):
        result = await agent.run({"action": "screen", "candidate_id": "c-1", "job_id": "j-1",
                                   "resume_text": "test", "job_requirements": "test"})
    assert result["agent"] == "screening"
    assert result["status"] == "completed"
    assert result["result"]["candidate_id"] == "c-1"
    assert result["result"]["gate_passed"] is True
    assert "summary" in result


@pytest.mark.asyncio
async def test_run_action_batch(agent):
    with patch.object(agent, "screen") as mock_screen:
        mock_screen.return_value = {"candidate_id": "c-1", "gate_passed": True}
        result = await agent.run({"action": "batch", "candidates": [{"id": "c-1"}]})
    assert result["agent"] == "screening"
    assert result["status"] == "completed"
    assert result["result"]["total"] == 1


@pytest.mark.asyncio
async def test_run_action_evaluate(agent):
    mock_agg = MagicMock()
    mock_agg.run = AsyncMock(return_value={"dimension_results": [{"dimension": "x"}]})
    agent._aggregator = mock_agg
    with patch.object(ScreeningAgent, "aggregator", new_callable=PropertyMock, return_value=mock_agg):
        result = await agent.run({"action": "evaluate", "candidate_info": "test"})
    assert result["agent"] == "screening"
    assert result["status"] == "completed"
    assert "dimension_results" in result["result"]
