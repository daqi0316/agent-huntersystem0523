"""Tests for screening built-in tools — search_candidates, get_candidate, screen_resume, list_jobs, get_evaluations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.screening import (
    _handle_search_candidates,
    _handle_get_candidate,
    _handle_list_jobs,
    _handle_get_evaluations,
)


@pytest.mark.asyncio
async def test_search_candidates_default():
    with patch("app.tools.screening.CandidateService") as MockSvc:
        svc = AsyncMock()
        svc.list.return_value = ([], 0)
        MockSvc.return_value = svc
        result = await _handle_search_candidates()
    assert "candidates" in result
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_candidate_not_found():
    with patch("app.tools.screening.CandidateService") as MockSvc:
        svc = AsyncMock()
        svc.get_by_id.return_value = None
        MockSvc.return_value = svc
        result = await _handle_get_candidate(candidate_id="nonexistent")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_candidate_found():
    mock_c = MagicMock()
    mock_c.id = "cand-1"
    mock_c.name = "张三"
    mock_c.email = "z@t.com"
    mock_c.phone = "13800138000"
    mock_c.skills = ["Python"]
    mock_c.experience_years = 5
    mock_c.current_company = "Acme"
    mock_c.current_title = "Engineer"
    mock_c.status = MagicMock(value="active")

    with patch("app.tools.screening.CandidateService") as MockSvc:
        svc = AsyncMock()
        svc.get_by_id.return_value = mock_c
        MockSvc.return_value = svc
        result = await _handle_get_candidate(candidate_id="cand-1")
    assert result["name"] == "张三"
    assert "Python" in result["skills"]


@pytest.mark.asyncio
async def test_list_jobs_empty():
    with patch("app.services.job.JobService") as MockSvc:
        svc = AsyncMock()
        svc.list.return_value = ([], 0)
        MockSvc.return_value = svc
        result = await _handle_list_jobs()
    assert result["total"] == 0
    assert result["jobs"] == []
