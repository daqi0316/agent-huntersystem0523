"""Tests for ResumeParsingAgent — 7-step workflow."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.resume_parser import ResumeParserAgent


@pytest.fixture
def agent():
    return ResumeParserAgent(name="test_parser")


@pytest.mark.asyncio
async def test_single_parse_no_input(agent):
    result = await agent.run({"content": "", "file_url": ""})
    assert result["status"] == "failed"
    assert "缺少" in result["summary"]


@pytest.mark.asyncio
async def test_single_parse_failed(agent):
    with patch("app.agents.resume_parser._handle_parse_resume", return_value={
        "status": "failed", "error": {"code": "LOW_CONFIDENCE", "message": "解析失败"},
    }):
        result = await agent.run({"content": "bad resume"})
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_single_parse_success(agent):
    with patch("app.agents.resume_parser._handle_parse_resume", return_value={
        "status": "success",
        "data": {
            "candidate_id": "cand-1",
            "basic_info": {"name": "张三"},
            "skills": ["Python"],
            "quality_score": 85,
            "confidence": 0.92,
            "red_flags": [],
            "is_duplicate": False,
            "needs_human_review": False,
        },
    }):
        result = await agent.run({"content": "good resume", "target_job_id": "job-1"})
    assert result["status"] == "completed"
    assert result["result"]["quality_score"] == 85
    assert "92%" in result["summary"]


@pytest.mark.asyncio
async def test_single_parse_low_confidence(agent):
    with patch("app.agents.resume_parser._handle_parse_resume", return_value={
        "status": "success",
        "data": {
            "candidate_id": "",
            "basic_info": {"name": ""},
            "skills": [],
            "quality_score": 30,
            "confidence": 0.55,
            "red_flags": [],
            "is_duplicate": False,
            "needs_human_review": True,
        },
    }):
        result = await agent.run({"content": "poor resume"})
    assert result["status"] == "partial"
    assert result["result"]["needs_human_review"] is True


@pytest.mark.asyncio
async def test_batch_parse_no_files(agent):
    result = await agent.run({"action": "batch", "files": []})
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_batch_parse_success(agent):
    fake_handler = AsyncMock(return_value={
        "status": "success",
        "data": {"total": 2, "success_count": 2, "fail_count": 0, "results": [{}, {}], "failures": []},
    })
    with patch("app.agents.resume_parser._handle_batch_parse", fake_handler):
        result = await agent.run({"action": "batch", "files": [{"content": "a"}, {"content": "b"}]})
    assert result["status"] == "completed"
    assert result["result"]["success_count"] == 2


@pytest.mark.asyncio
async def test_get_profile_no_id(agent):
    result = await agent.run({"action": "get_profile", "candidate_id": ""})
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_get_profile_success(agent):
    with patch("app.agents.resume_parser._handle_get_profile", return_value={
        "status": "success",
        "data": {"candidate_id": "cand-1", "basic_info": {"name": "张三"}},
    }):
        result = await agent.run({"action": "get_profile", "candidate_id": "cand-1"})
    assert result["status"] == "completed"
    assert result["result"]["candidate_id"] == "cand-1"
