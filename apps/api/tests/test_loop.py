"""Loop API tests: JD generation and improvement."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_jd_generate_success(client):
    """Mock JDGeneratorService returns a completed JD."""
    from app.api import loop as loop_module

    mock_service = AsyncMock()
    mock_service.generate_jd.return_value = {
        "final_output": "# Senior Engineer\n\n## Requirements\n- 5+ years",
        "iterations": [
            {"iteration": 1, "generated": "# Senior Engineer\n\n...", "score": 8.5, "passed": True}
        ],
        "total_iterations": 2,
        "passed": True,
    }

    original_service = loop_module.service
    loop_module.service = mock_service
    try:
        resp = await client.post("/api/v1/loop/jd-generate", json={
            "title": "Senior Engineer",
            "requirements": "5+ years experience in Python",
            "preferences": "Team player",
            "auto_improve": True,
        })
    finally:
        loop_module.service = original_service

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Senior Engineer" in data["data"]
    assert data["total_iterations"] == 2
    assert data["passed"] is True


@pytest.mark.asyncio
async def test_jd_generate_no_title_returns_422(client):
    """JD generation without a title returns 422."""
    resp = await client.post("/api/v1/loop/jd-generate", json={
        "requirements": "some skills",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_jd_improve_success(client):
    """Mock JDGeneratorService.improve_jd returns improved content."""
    from app.api import loop as loop_module

    mock_service = AsyncMock()
    mock_service.improve_jd.return_value = {
        "jd_content": "# Improved Senior Engineer\n\n## Requirements\n- 5+ years",
        "original": "# Senior Engineer\n\n...",
        "feedback": "Add more detail about team culture",
    }

    original_service = loop_module.service
    loop_module.service = mock_service
    try:
        resp = await client.post("/api/v1/loop/jd-improve", json={
            "jd_content": "# Senior Engineer\n\n...",
            "feedback": "Add more detail about team culture",
        })
    finally:
        loop_module.service = original_service

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Improved" in data["jd_content"]


@pytest.mark.asyncio
async def test_jd_generate_auto_improve_false(client):
    """Single generation without auto-improve returns 1 iteration."""
    from app.api import loop as loop_module

    mock_service = AsyncMock()
    mock_service.generate_jd.return_value = {
        "final_output": "# Junior Developer\n\n...",
        "iterations": [{"iteration": 1, "generated": "# Junior Developer\n\n...", "passed": True}],
        "total_iterations": 1,
        "passed": True,
    }

    original_service = loop_module.service
    loop_module.service = mock_service
    try:
        resp = await client.post("/api/v1/loop/jd-generate", json={
            "title": "Junior Developer",
            "requirements": "1+ year experience",
            "auto_improve": False,
        })
    finally:
        loop_module.service = original_service

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_iterations"] == 1
