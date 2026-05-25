"""Parallel / Aggregator API tests: multi-dimension evaluation & data aggregation."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_multi_evaluate_success(client):
    """Mock ScreeningService returns multi-dimension evaluation results."""
    mock_service = AsyncMock()
    mock_service.multi_evaluate.return_value = {
        "dimension_results": [
            {"name": "专业技能", "score": 85, "analysis": "Strong technical background"},
            {"name": "沟通能力", "score": 70, "analysis": "Good communicator"},
        ],
        "consensus": {"average_score": 77.5, "total_dimensions": 2},
        "total_dimensions": 2,
    }

    with patch("app.api.parallel.service", mock_service):
        resp = await client.post("/api/v1/parallel/multi-evaluate", json={
            "candidate_info": "Senior developer with 5 years experience",
            "dimensions": ["专业技能", "沟通能力"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["dimension_results"]) == 2
    assert data["total_dimensions"] == 2
    assert data["consensus"]["average_score"] == 77.5


@pytest.mark.asyncio
async def test_data_aggregate_success(client):
    """Data aggregate correctly computes stats."""
    resp = await client.post("/api/v1/parallel/data-aggregate", json={
        "dimension_results": [
            {"name": "专业技能", "score": 95},
            {"name": "沟通能力", "score": 80},
            {"name": "经验匹配", "score": 70},
        ],
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["average_score"] == pytest.approx(81.7, rel=0.1)
    assert data["data"]["max_score"] == 95
    assert data["data"]["min_score"] == 70
    assert data["data"]["total_dimensions"] == 3


@pytest.mark.asyncio
async def test_data_aggregate_empty(client):
    """Empty dimension_results returns error."""
    resp = await client.post("/api/v1/parallel/data-aggregate", json={
        "dimension_results": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_data_aggregate_distribution(client):
    """Data aggregate correctly distributes scores into buckets."""
    resp = await client.post("/api/v1/parallel/data-aggregate", json={
        "dimension_results": [
            {"name": "维度A", "score": 95},
            {"name": "维度B", "score": 85},
            {"name": "维度C", "score": 75},
            {"name": "维度D", "score": 65},
            {"name": "维度E", "score": 55},
        ],
    })

    assert resp.status_code == 200
    data = resp.json()
    dist = data["data"]["distribution"]
    assert dist["90-100"] == 1
    assert dist["80-89"] == 1
    assert dist["70-79"] == 1
    assert dist["60-69"] == 1
    assert dist["<60"] == 1
