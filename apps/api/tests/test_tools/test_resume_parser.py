"""Tests for resume_parser built-in tools — parse_resume, batch_parse, get_profile."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.resume_parser import (
    _handle_parse_resume,
    _handle_batch_parse,
    _handle_get_profile,
    _compute_quality,
    _detect_red_flags,
)


class FakeExtractedCandidate:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_compute_quality_full():
    c = FakeExtractedCandidate(
        name="张三", email="z@t.com", phone="13800138000",
        skills=["Python", "Java"], experience_years=5,
        education="本科", current_company="Acme", current_title="Engineer",
    )
    assert _compute_quality(c) == 100


def test_compute_quality_minimal():
    c = FakeExtractedCandidate(name="", email="", phone="", skills=[], experience_years=None, education="", current_company="", current_title="")
    assert _compute_quality(c) == 0


def test_detect_red_flags_none():
    c = FakeExtractedCandidate(experience_years=5)
    assert _detect_red_flags(c) == []


def test_detect_red_flags_inexperienced():
    c = FakeExtractedCandidate(experience_years=0)
    flags = _detect_red_flags(c)
    assert len(flags) == 1
    assert flags[0]["type"] == "inexperienced"


@pytest.mark.asyncio
async def test_handle_parse_resume_no_input():
    result = await _handle_parse_resume()
    assert result["status"] == "failed"
    assert "content or file_url required" in result["error"]["message"]


@pytest.mark.asyncio
async def test_handle_parse_resume_extraction_fails():
    with patch("app.tools.resume_parser.extract_from_text") as mock_extract:
        mock_extract.side_effect = Exception("LLM unavailable")
        result = await _handle_parse_resume(content="resume text")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "LOW_CONFIDENCE"


@pytest.mark.asyncio
async def test_handle_parse_resume_success():
    fake = FakeExtractedCandidate(
        name="张三", email="zhang@test.com", phone="13800138000",
        skills=["Python", "Java"], experience_years=5,
        education="本科", current_company="ByteDance", current_title="Senior",
        raw_text="resume text",
    )
    with patch("app.tools.resume_parser.extract_from_text", return_value=fake):
        result = await _handle_parse_resume(content="resume text", target_job_id="job-1")
    assert result["status"] == "success"
    data = result["data"]
    assert data["basic_info"]["name"] is not None
    assert "Python" in data["skills"]
    assert data["quality_score"] > 0
    assert data["confidence"] > 0.8


@pytest.mark.asyncio
async def test_handle_batch_parse_no_files():
    result = await _handle_batch_parse()
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_batch_parse_empty_files():
    result = await _handle_batch_parse(files=[])
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_batch_parse_mixed():
    fake = FakeExtractedCandidate(
        name="李四", email="li@test.com", phone="13900139000",
        skills=["Go"], experience_years=3, education="硕士",
        current_company="ACME", current_title="Dev",
        raw_text="some text",
    )
    with patch("app.tools.resume_parser.extract_from_text", return_value=fake):
        result = await _handle_batch_parse(files=[
            {"content": "valid resume", "filename": "li.pdf"},
            {"content": "", "filename": "empty.txt"},
        ])
    assert result["status"] == "success"
    assert result["data"]["success_count"] == 1
    assert result["data"]["fail_count"] == 1


@pytest.mark.asyncio
async def test_handle_get_profile_no_id():
    result = await _handle_get_profile()
    assert result["status"] == "failed"
