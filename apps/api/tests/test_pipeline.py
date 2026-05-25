"""Pipeline agent unit tests — mocked LLM client at the import point."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.pipeline import PipelineAgent, PipelineStep

pytestmark = pytest.mark.asyncio

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def llm_patch():
    """Start patch on get_llm_client for the full test, yield a mock."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.pipeline.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


# ── PipelineStep ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_step_stores_name_and_handler():
    async def handler(ctx):
        return {"dummy": True}

    step = PipelineStep(name="parse", handler=handler)
    assert step.name == "parse"
    assert step.handler is handler


# ── PipelineAgent — init ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_default_state():
    agent = PipelineAgent(name="my_agent")
    assert agent.name == "my_agent"
    assert agent.steps == []
    assert agent.context == {}
    assert agent._llm is None


@pytest.mark.asyncio
async def test_llm_lazy_initialization(llm_patch):
    pipeline = PipelineAgent(name="test_pipeline")
    assert pipeline._llm is None
    llm = pipeline.llm
    assert llm is llm_patch
    assert pipeline._llm is llm


@pytest.mark.asyncio
async def test_add_step_fluent():
    async def handler(ctx):
        return {"dummy": True}

    agent = PipelineAgent(name="p")
    result = agent.add_step("parse", handler)
    assert result is agent
    assert len(agent.steps) == 1
    assert agent.steps[0].name == "parse"


# ── PipelineAgent.run() ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_all_steps_collected():
    async def handler(ctx):
        return {"dummy": True}

    agent = PipelineAgent(name="test_agent")
    agent.add_step("a", handler)
    agent.add_step("b", handler)

    result = await agent.run({"input_key": "val"})

    assert result["agent"] == "test_agent"
    assert result["pipeline_id"]
    assert result["status"] == "completed"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["step"] == "a"
    assert result["steps"][1]["step"] == "b"


@pytest.mark.asyncio
async def test_run_context_flows_across_steps():
    async def step_one(ctx):
        return {"step_one_done": True}

    async def step_two(ctx):
        return {"step_two_done": True, "sees_one": ctx.get("step_one_done")}

    agent = PipelineAgent(name="p")
    agent.add_step("one", step_one)
    agent.add_step("two", step_two)
    result = await agent.run({})
    assert result["final_output"]["step_one_done"] is True
    assert result["final_output"]["step_two_done"] is True
    assert result["final_output"]["sees_one"] is True


# ── PipelineAgent.parse_resume() ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_returns_parsed_json(llm_patch):
    llm_patch.chat.return_value = (
        '{"name": "John", "email": "jd@example.com", "skills": ["Python"]}'
    )
    result = await PipelineAgent.parse_resume(
        {"resume_text": "John Doe, jd@example.com, Python expert, 5 years"}
    )
    parsed = result["parsed_resume"]
    assert parsed["name"] == "John"
    assert parsed["email"] == "jd@example.com"
    assert parsed["skills"] == ["Python"]


@pytest.mark.asyncio
async def test_parse_handles_invalid_json(llm_patch):
    llm_patch.chat.return_value = "not json at all"
    result = await PipelineAgent.parse_resume({"resume_text": "test"})
    assert "error" in result["parsed_resume"]


@pytest.mark.asyncio
async def test_parse_handles_markdown_fence(llm_patch):
    llm_patch.chat.return_value = "```json\n{\"name\": \"John\"}\n```"
    result = await PipelineAgent.parse_resume({"resume_text": "test"})
    assert result["parsed_resume"]["name"] == "John"


@pytest.mark.asyncio
async def test_parse_handles_empty_resume(llm_patch):
    llm_patch.chat.return_value = "{\"name\": \"\"}"
    result = await PipelineAgent.parse_resume({"resume_text": ""})
    assert result["parsed_resume"]["name"] == ""


# ── PipelineAgent.match_job() ───────────────────────────────────────────────


MATCH_CONTEXT = {
    "parsed_resume": {"name": "John", "skills": ["Python"]},
    "job_requirements": "Python developer, 3+ years",
}


@pytest.mark.asyncio
async def test_match_returns_result(llm_patch):
    llm_patch.chat.return_value = (
        '{"overall_score": 8, "strengths": ["Python expert"], '
        '"weaknesses": [], "recommendation": "recommend"}'
    )
    result = await PipelineAgent.match_job(MATCH_CONTEXT)
    assert result["match_result"]["overall_score"] == 8
    assert "Python expert" in result["match_result"]["strengths"]


@pytest.mark.asyncio
async def test_match_handles_parse_failure(llm_patch):
    llm_patch.chat.return_value = "broken json{{{"
    result = await PipelineAgent.match_job(MATCH_CONTEXT)
    assert "error" in result["match_result"]


@pytest.mark.asyncio
async def test_match_missing_requirements(llm_patch):
    llm_patch.chat.return_value = '{"overall_score": 5}'
    result = await PipelineAgent.match_job({"parsed_resume": {}})
    assert result["match_result"]["overall_score"] == 5


# ── PipelineAgent.gate_check() ──────────────────────────────────────────────


CONTEXT_PASSING = {"match_result": {"overall_score": 8, "strengths": []}}
CONTEXT_FAILING = {"match_result": {"overall_score": 3, "weaknesses": ["no relevant exp"]}}


@pytest.mark.asyncio
async def test_gate_passes_good_score(llm_patch):
    llm_patch.chat.return_value = (
        '{"gate_passed": true, "score_adjusted": 8, "issues": [], '
        '"needs_human_review": false, "gate_summary": "合格"}'
    )
    result = await PipelineAgent.gate_check(CONTEXT_PASSING)
    assert result["gate_passed"] is True
    assert result["final_score"] == 8
    assert result["needs_human_review"] is False


@pytest.mark.asyncio
async def test_gate_fails_low_score(llm_patch):
    llm_patch.chat.return_value = (
        '{"gate_passed": false, "score_adjusted": 3, "issues": ["经验不足"], '
        '"needs_human_review": true, "gate_summary": "不合格"}'
    )
    result = await PipelineAgent.gate_check(CONTEXT_FAILING)
    assert result["gate_passed"] is False
    assert result["needs_human_review"] is True


@pytest.mark.asyncio
async def test_gate_fallback_on_parse_failure_good(llm_patch):
    """Score >= 6 -> gate passes when LLM response can't be parsed."""
    llm_patch.chat.return_value = "{{{broken}"
    result = await PipelineAgent.gate_check(CONTEXT_PASSING)
    assert result["gate_passed"] is True
    assert "gate_parse_failed" in result["gate_result"]["issues"]


@pytest.mark.asyncio
async def test_gate_fallback_on_parse_failure_bad(llm_patch):
    """Score < 6 -> gate fails when LLM can't be parsed."""
    llm_patch.chat.return_value = "{{{broken}"
    result = await PipelineAgent.gate_check(CONTEXT_FAILING)
    assert result["gate_passed"] is False


@pytest.mark.asyncio
async def test_gate_uses_score_adjusted(llm_patch):
    llm_patch.chat.return_value = (
        '{"gate_passed": true, "score_adjusted": 7, "issues": [], '
        '"needs_human_review": false, "gate_summary": "ok"}'
    )
    result = await PipelineAgent.gate_check(CONTEXT_PASSING)
    assert result["final_score"] == 7


@pytest.mark.asyncio
async def test_gate_falls_back_to_overall(llm_patch):
    llm_patch.chat.return_value = (
        '{"gate_passed": true, "issues": [], '
        '"needs_human_review": false, "gate_summary": "ok"}'
    )
    result = await PipelineAgent.gate_check(CONTEXT_PASSING)
    assert result["final_score"] == 8


# ── PipelineAgent.build_screening_pipeline() ────────────────────────────────


@pytest.mark.asyncio
async def test_build_screening_three_steps():
    pipeline = PipelineAgent.build_screening_pipeline()
    assert pipeline.name == "resume_screening"
    assert len(pipeline.steps) == 3
    assert [s.name for s in pipeline.steps] == ["parse", "match", "gate"]


@pytest.mark.asyncio
async def test_build_screening_round_trip(llm_patch):
    """Run the full screening pipeline with all 3 steps plus LLM mocking."""
    llm_patch.chat.side_effect = [
        '{"name": "John", "skills": ["Python"]}',
        '{"overall_score": 8, "strengths": ["Python"], '
        '"weaknesses": [], "recommendation": "推荐"}',
        '{"gate_passed": true, "score_adjusted": 8, "issues": [], '
        '"needs_human_review": false, "gate_summary": "通过"}',
    ]
    pipeline = PipelineAgent.build_screening_pipeline()
    result = await pipeline.run({
        "resume_text": "John, Python, 5yrs",
        "job_requirements": "Python dev",
    })

    assert result["status"] == "completed"
    assert len(result["steps"]) == 3
    steps = result["steps"]
    assert steps[0]["step"] == "parse"
    assert steps[1]["step"] == "match"
    assert steps[2]["step"] == "gate"
    final = result["final_output"]
    assert final["parsed_resume"]["name"] == "John"
    assert final["match_result"]["overall_score"] == 8
    assert final["gate_passed"] is True
