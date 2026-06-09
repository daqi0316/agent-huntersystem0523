"""Tests for InterviewAgent — evaluation forms, feedback, scheduling (mocked LLM)."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.agents.interview_agent import (
    InterviewAgent,
    INTERVIEW_ROUNDS,
    EVALUATION_FORM_PROMPT,
    FEEDBACK_SUMMARY_PROMPT,
    TRANSCRIPT_FEEDBACK_PROMPT,
)


@pytest.fixture
def agent():
    return InterviewAgent()


def test_init(agent):
    assert agent.name == "interview"


def test_interview_rounds_defined():
    assert len(INTERVIEW_ROUNDS) == 4
    rounds = [r["round"] for r in INTERVIEW_ROUNDS]
    assert rounds == ["R1", "R2", "R3", "R4"]


def test_schedule_interview_rounds(agent):
    plan = agent.schedule_interview_rounds("张三", "Python 工程师")
    assert len(plan) == 4
    for p in plan:
        assert "round" in p
        assert "label" in p
        assert "duration_minutes" in p
        assert p["status"] == "pending"


@pytest.mark.asyncio
async def test_generate_evaluation_form_llm_fallback(agent):
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="not json at all")
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        form = await agent.generate_evaluation_form(
            candidate_name="张三", candidate_background="5 年 Python 开发", round_id="R2",
        )
    assert form["round"] == "R2"
    assert "dimensions" in form
    assert len(form["dimensions"]) >= 1


@pytest.mark.asyncio
async def test_evaluation_form_defaults_for_unknown_round(agent):
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="not json")
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        form = await agent.generate_evaluation_form(
            candidate_name="李四", round_id="R99",
        )
    assert form["round"] == "R99"


@pytest.mark.asyncio
async def test_collect_feedback(agent):
    result = await agent.collect_feedback(
        interview_id="i-1",
        feedback_data={"overall_score": 8, "comment": "技术扎实"},
    )
    assert result["status"] == "recorded"
    assert result["record"]["interview_id"] == "i-1"


@pytest.mark.asyncio
async def test_summarize_feedback_empty(agent):
    result = await agent.summarize_feedback("张三", [])
    assert result["consensus"] == "consider"
    assert result["overall_score"] == 0
    assert "暂无评估数据" in result["final_recommendation"]


@pytest.mark.asyncio
async def test_summarize_feedback_fallback(agent):
    evaluations = [
        {"round": "R1", "overall_score": 8, "feedback": "不错"},
        {"round": "R2", "overall_score": 6, "feedback": "一般"},
    ]
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        result = await agent.summarize_feedback("张三", evaluations)
    assert result["overall_score"] == 7.0
    assert result["consensus"] in ("hire", "consider")


@pytest.mark.asyncio
async def test_generate_feedback_from_transcript_requires_transcript(agent):
    result = await agent.generate_feedback_from_transcript("张三", "")
    assert result["status"] == "insufficient_data"
    assert result["overall_score"] is None
    assert "不能声称" in result["feedback"]


@pytest.mark.asyncio
async def test_generate_feedback_from_transcript_fallback_uses_quote(agent):
    transcript = "候选人：我主导过支付系统重构，并把接口延迟降低了 40%。"
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        result = await agent.generate_feedback_from_transcript("张三", transcript, "后端工程师")
    assert result["status"] == "completed"
    assert result["evidence_quotes"]
    assert "支付系统重构" in result["evidence_quotes"][0]


@pytest.mark.asyncio
async def test_send_reminder_stub(agent):
    result = await agent.send_reminder("i-1")
    assert result["status"] == "sent"
    assert result["interview_id"] == "i-1"
    assert "email" in result["channels"]


@pytest.mark.asyncio
async def test_run_action_schedule(agent):
    result = await agent.run({
        "action": "schedule",
        "candidate_name": "张三",
        "job_title": "工程师",
    })
    assert result["status"] == "completed"
    assert len(result["result"]["plan"]) == 4


@pytest.mark.asyncio
async def test_run_action_evaluation_form(agent):
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="not json")
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        result = await agent.run({
            "action": "evaluation_form",
            "candidate_name": "张三",
            "round_id": "R1",
        })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_action_collect_feedback(agent):
    result = await agent.run({
        "action": "collect_feedback",
        "interview_id": "i-1",
        "feedback_data": {"overall_score": 9},
    })
    assert result["status"] == "completed"
    assert result["result"]["status"] == "recorded"


@pytest.mark.asyncio
async def test_run_action_summarize_feedback(agent):
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    agent._llm = mock_llm
    with patch.object(InterviewAgent, "llm", new_callable=PropertyMock, return_value=mock_llm):
        result = await agent.run({
            "action": "summarize_feedback",
            "candidate_name": "张三",
            "evaluations": [{"round": "R1", "overall_score": 8, "feedback": "好"}],
        })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_action_reminder(agent):
    result = await agent.run({
        "action": "reminder",
        "interview_id": "i-1",
    })
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_action_transcript_feedback(agent):
    result = await agent.run({
        "action": "transcript_feedback",
        "candidate_name": "张三",
        "transcript_text": "候选人：我负责过招聘系统后端。",
    })
    assert result["status"] == "completed"
    assert result["result"]["status"] == "completed"


def test_prompt_templates_defined():
    assert "{round_name}" in EVALUATION_FORM_PROMPT
    assert "{candidate_name}" in FEEDBACK_SUMMARY_PROMPT
    assert "{feedback_list}" in FEEDBACK_SUMMARY_PROMPT
    assert "{transcript_text}" in TRANSCRIPT_FEEDBACK_PROMPT
