"""Tests for Screening API routes via FastAPI TestClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_user_id

# Override auth dependency
app.dependency_overrides[get_current_user_id] = lambda: "test-user-id"

client = TestClient(app, raise_server_exceptions=False)


def teardown_module():
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_screen_candidate_success():
    mock_service = MagicMock()
    mock_service.screen = AsyncMock(return_value={
        "candidate_id": "c-1",
        "overall_score": 85,
        "gate_passed": True,
    })
    with patch("app.api.screening.ScreeningService", return_value=mock_service):
        resp = client.post("/api/v1/screen", json={
            "candidate_id": "c-1",
            "job_id": "j-1",
            "resume_text": "python 5年经验",
            "job_requirements": "python developer",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["candidate_id"] == "c-1"
    assert data["data"]["overall_score"] == 85


@pytest.mark.asyncio
async def test_screen_candidate_error():
    mock_service = MagicMock()
    mock_service.screen = AsyncMock(side_effect=Exception("service down"))
    with patch("app.api.screening.ScreeningService", return_value=mock_service):
        resp = client.post("/api/v1/screen", json={
            "candidate_id": "c-1",
            "job_id": "j-1",
            "resume_text": "python",
            "job_requirements": "python",
        })
    # Should return 500 from global exception handler
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_batch_screen_success():
    mock_agent = MagicMock()
    mock_agent.batch_screen = AsyncMock(return_value=[
        {"candidate_id": "c-1", "overall_score": 85},
        {"candidate_id": "c-2", "overall_score": 72},
    ])
    mock_service = MagicMock()
    mock_service.screening_agent = mock_agent
    with patch("app.api.screening.ScreeningService", return_value=mock_service):
        resp = client.post("/api/v1/screen/batch", json={
            "candidates": [
                {"candidate_id": "c-1", "job_id": "j-1", "resume_text": "r", "job_requirements": "j"},
                {"candidate_id": "c-2", "job_id": "j-1", "resume_text": "r2", "job_requirements": "j"},
            ],
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) == 2


@pytest.mark.asyncio
async def test_get_screen_result():
    resp = client.get("/api/v1/screen/c-123/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["candidate_id"] == "c-123"


@pytest.mark.asyncio
async def test_evaluate_candidate_success():
    mock_agent = MagicMock()
    mock_agent.multi_evaluate = AsyncMock(return_value={
        "dimension_results": [
            {"dimension": "technical", "score": 80},
            {"dimension": "culture", "score": 90},
        ],
    })
    mock_service = MagicMock()
    mock_service.screening_agent = mock_agent
    with patch("app.api.screening.ScreeningService", return_value=mock_service):
        resp = client.post("/api/v1/screen/evaluate", json={
            "candidate_info": "python developer 5年经验",
            "dimensions": ["technical", "culture"],
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]["dimension_results"]) == 2


@pytest.mark.asyncio
async def test_evaluate_candidate_default_dims():
    mock_agent = MagicMock()
    mock_agent.multi_evaluate = AsyncMock(return_value={"dimension_results": []})
    mock_service = MagicMock()
    mock_service.screening_agent = mock_agent
    with patch("app.api.screening.ScreeningService", return_value=mock_service):
        resp = client.post("/api/v1/screen/evaluate", json={
            "candidate_info": "test",
        })
    assert resp.status_code == 200
    mock_agent.multi_evaluate.assert_awaited_once()
    call = mock_agent.multi_evaluate.await_args
    assert call is not None
    assert call.kwargs.get("dimensions") is None  # default dimensions
