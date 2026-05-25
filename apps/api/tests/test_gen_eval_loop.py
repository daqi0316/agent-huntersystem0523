"""GenEvalLoop unit tests — mocked LLM."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.gen_eval_loop import GenEvalLoop, GenEvalResult

# async tests marked individually; no module-level mark to avoid warnings on sync tests


@pytest.fixture
def llm_patch():
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.gen_eval_loop.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


# ── GenEvalResult ──


def test_gen_eval_result_constructor():
    r = GenEvalResult(iteration=1, generated="jd text", score=8.0, feedback="good", passed=True)
    assert r.iteration == 1
    assert r.generated == "jd text"
    assert r.score == 8.0
    assert r.passed is True


def test_gen_eval_result_to_dict():
    r = GenEvalResult(iteration=2, generated="g", score=5.0, feedback="fix", passed=False)
    d = r.to_dict()
    assert d["iteration"] == 2
    assert d["score"] == 5.0
    assert d["passed"] is False


# ── GenEvalLoop init ──


def test_init_default_state():
    agent = GenEvalLoop(name="ge")
    assert agent.name == "ge"
    assert agent.max_iterations == 6
    assert agent.threshold == 7.0
    assert agent._llm is None


def test_init_custom_params():
    agent = GenEvalLoop(name="ge", max_iterations=3, threshold=8.0)
    assert agent.max_iterations == 3
    assert agent.threshold == 8.0


# ── generate ──


async def test_generate_without_feedback(llm_patch):
    llm_patch.chat.return_value = "Generated JD content"
    agent = GenEvalLoop()
    result = await agent.generate({"title": "Engineer", "requirements": "Python"})
    assert result == "Generated JD content"
    call_args = llm_patch.chat.call_args[0][0]
    assert any("Engineer" in str(m) for m in call_args)


async def test_generate_with_feedback(llm_patch):
    llm_patch.chat.return_value = "Improved JD"
    agent = GenEvalLoop()
    result = await agent.generate(
        {"title": "Engineer"},
        feedback="Needs more detail on requirements",
    )
    assert result == "Improved JD"
    call_args = llm_patch.chat.call_args[1]
    assert call_args.get("temperature") == 0.7
    assert call_args.get("max_tokens") == 2048


# ── evaluate ──


async def test_evaluate_returns_score_and_feedback(llm_patch):
    llm_patch.chat.return_value = "总分: 8.5\n改进建议: Add more detail"
    agent = GenEvalLoop()
    score, feedback = await agent.evaluate("Generated JD content")
    assert score == 8.5
    assert feedback == "Add more detail"


async def test_evaluate_no_feedback_when_score_high(llm_patch):
    llm_patch.chat.return_value = "总分: 9.0\n改进建议: 无"
    agent = GenEvalLoop()
    score, feedback = await agent.evaluate("Good JD")
    assert score == 9.0
    assert feedback is None


async def test_evaluate_unparseable_score(llm_patch):
    llm_patch.chat.return_value = "not the right format"
    agent = GenEvalLoop()
    score, feedback = await agent.evaluate("JD")
    assert score == 0.0
    assert feedback is None


# ── run ──


async def test_run_passes_on_first_iteration(llm_patch):
    """Score >= threshold returns immediately."""
    agent = GenEvalLoop(max_iterations=5, threshold=7.0)
    llm_patch.chat.side_effect = [
        "JD version 1",
        "总分: 8.0\n改进建议: 无",
    ]
    result = await agent.run({"title": "Engineer"})
    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["total_iterations"] == 1
    assert result["final_output"] == "JD version 1"


async def test_run_iterates_until_threshold(llm_patch):
    """Low score loops until threshold is met."""
    agent = GenEvalLoop(max_iterations=5, threshold=7.0)
    llm_patch.chat.side_effect = [
        "JD v1",
        "总分: 5.0\n改进建议: Too short",
        "JD v2",
        "总分: 8.0\n改进建议: 无",
    ]
    result = await agent.run({"title": "Engineer"})
    assert result["passed"] is True
    assert result["total_iterations"] == 2


async def test_run_uses_last_output_when_threshold_not_met(llm_patch):
    """Max iterations reached without passing — returns last output."""
    agent = GenEvalLoop(max_iterations=2, threshold=9.0)
    llm_patch.chat.side_effect = [
        "JD v1",
        "总分: 5.0\n改进建议: Low",
        "JD v2",
        "总分: 6.0\n改进建议: Still low",
    ]
    result = await agent.run({"title": "Engineer"})
    assert result["passed"] is False
    assert result["total_iterations"] == 2
    assert result["final_output"] == "JD v2"
