from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio


def _token() -> str:
    return create_access_token(f"test-user-{uuid.uuid4().hex[:8]}")


async def test_list_summaries_success(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.list_by_user.return_value = (
        [{"id": "s1", "session_id": "sess-1", "summary": "test", "created_at": "2025-01-01"}],
        1,
    )

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.get("/api/v1/summaries", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["total"] == 1


async def test_list_summaries_empty(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.list_by_user.return_value = ([], 0)

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.get("/api/v1/summaries", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] == []
    assert data["total"] == 0


async def test_update_summary_success(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.update_summary.return_value = True

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.put(
            "/api/v1/summaries/s1",
            json={"summary": "Updated summary text"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_update_summary_not_found(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.update_summary.return_value = False

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.put(
            "/api/v1/summaries/nonexistent",
            json={"summary": "text"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 404


async def test_delete_summary_success(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.delete_summary.return_value = True

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.delete(
            "/api/v1/summaries/s1",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_delete_summary_not_found(client):
    token = _token()
    mock_svc = AsyncMock()
    mock_svc.delete_summary.return_value = False

    with patch("app.api.summaries.SummaryService", return_value=mock_svc):
        resp = await client.delete(
            "/api/v1/summaries/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 404
