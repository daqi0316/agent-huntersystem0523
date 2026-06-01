"""Tests for app.agents.orchestrator_session — OrchestratorSession persistence."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.orchestrator_session import OrchestratorSession, _clean_results

# Async tests marked individually with @pytest.mark.asyncio.
# Module-level pytestmark is NOT set because _clean_results and init tests are sync.


# ── _clean_results ──


def test_clean_results_keeps_none():
    assert _clean_results([None]) == [None]


def test_clean_results_keeps_dicts():
    assert _clean_results([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_clean_results_wraps_exceptions():
    e = ValueError("bad data")
    result = _clean_results([e])
    assert len(result) == 1
    assert result[0]["status"] == "unknown"
    assert "bad data" in result[0]["summary"]


def test_clean_results_mixed():
    result = _clean_results([None, {"ok": True}, Exception("err")])
    assert result[0] is None
    assert result[1] == {"ok": True}
    assert result[2]["status"] == "unknown"


# ── OrchestratorSession init ──


def test_init_defaults():
    s = OrchestratorSession(session_id="test_session")
    assert s.session_id == "test_session"
    assert s.task == ""
    assert s.context == {}
    assert s.sub_tasks == []
    assert s.levels == []
    assert s.results == []
    assert s.shared_context == {}
    assert s.paused_at_level == -1
    assert s.approval_ids == []
    assert s.status == "paused"


def test_init_generates_session_id():
    s = OrchestratorSession()
    assert s.session_id.startswith("os_")
    assert len(s.session_id) > 5


# ── to_dict / from_dict ──


def test_to_dict_contains_all_fields():
    s = OrchestratorSession(session_id="sid1")
    s.task = "analyze candidate"
    s.context = {"job_id": "j1"}
    s.sub_tasks = [{"name": "check_resume"}]
    s.levels = [[0]]
    s.results = [{"done": True}]
    s.shared_context = {"score": 85}
    s.paused_at_level = 0
    s.approval_ids = ["a1"]
    s.status = "paused"

    d = s.to_dict()
    assert d["session_id"] == "sid1"
    assert d["task"] == "analyze candidate"
    assert d["results"] == [{"done": True}]


def test_from_dict_reconstructs():
    data = {
        "session_id": "sid2",
        "task": "review",
        "context": {"key": "val"},
        "sub_tasks": [{"name": "step1"}],
        "levels": [[0, 1]],
        "results": [None, {"done": True}],
        "shared_context": {"note": "hello"},
        "paused_at_level": 1,
        "approval_ids": ["a1", "a2"],
        "status": "resumed",
    }
    s = OrchestratorSession.from_dict(data)
    assert s.session_id == "sid2"
    assert s.task == "review"
    assert s.approval_ids == ["a1", "a2"]
    assert s.status == "resumed"
    assert s.paused_at_level == 1


# ── save / delete ──


@patch("app.core.redis.get_redis")
async def test_save_persists_to_redis(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = OrchestratorSession(session_id="save_test")
    s.approval_ids = ["apr1"]
    await s.save()

    # Should call set for session key and for each approval index
    assert mock_client.setex.call_count >= 2  # session + 1 approval


@patch("app.core.redis.get_redis", new_callable=AsyncMock, return_value=None)
async def test_save_warns_when_redis_unavailable(mock_get_redis):
    s = OrchestratorSession(session_id="no_redis")
    with patch("app.agents.orchestrator_session.logger") as mock_logger:
        await s.save()
        mock_logger.warning.assert_called_once()


@patch("app.core.redis.get_redis")
async def test_delete_removes_from_redis(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = OrchestratorSession(session_id="del_test")
    s.approval_ids = ["apr1"]
    await s.delete()

    # Should call delete for session key and for each approval index
    assert mock_client.delete.call_count >= 2


@patch("app.core.redis.get_redis", new_callable=AsyncMock, return_value=None)
async def test_delete_handles_redis_unavailable(mock_get_redis):
    s = OrchestratorSession(session_id="del_no_redis")
    # Should not raise
    await s.delete()


# ── load ──


@patch("app.core.redis.get_redis")
async def test_load_returns_session(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=json.dumps({
        "session_id": "load_test",
        "task": "loaded task",
        "status": "paused",
    }).encode())
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = await OrchestratorSession.load("load_test")
    assert s is not None
    assert s.session_id == "load_test"
    assert s.task == "loaded task"


@patch("app.core.redis.get_redis")
async def test_load_returns_none_when_not_found(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = await OrchestratorSession.load("missing")
    assert s is None


@patch("app.core.redis.get_redis", new_callable=AsyncMock, return_value=None)
async def test_load_returns_none_when_redis_unavailable(mock_get_redis):
    s = await OrchestratorSession.load("no_redis")
    assert s is None


@patch("app.core.redis.get_redis")
async def test_load_returns_none_on_corrupt_data(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"not valid json{{{")
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = await OrchestratorSession.load("corrupt")
    assert s is None


# ── find_by_approval_id ──


@patch("app.core.redis.get_redis")
async def test_find_by_approval_id(mock_get_redis):
    mock_client = AsyncMock()
    # First get returns the session_id, second returns session data
    session_data = json.dumps({"session_id": "apr_sesh", "task": "approval task", "status": "paused"}).encode()
    mock_client.get = AsyncMock(side_effect=[b"apr_sesh", session_data])
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = await OrchestratorSession.find_by_approval_id("approval_1")
    assert s is not None
    assert s.session_id == "apr_sesh"
    assert s.task == "approval task"


@patch("app.core.redis.get_redis")
async def test_find_by_approval_id_returns_none_when_not_found(mock_get_redis):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.ping = AsyncMock()
    mock_get_redis.return_value = mock_client

    s = await OrchestratorSession.find_by_approval_id("missing_apr")
    assert s is None


# ── _session_key ──


def test_session_key_format():
    s = OrchestratorSession(session_id="abc123")
    assert s._session_key() == "orch:session:abc123"
