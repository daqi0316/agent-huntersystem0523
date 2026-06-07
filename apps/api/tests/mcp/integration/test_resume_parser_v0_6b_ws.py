"""v0.6b WebSocket 进度推送测试。

覆盖:
  1. _authenticate_ws header Authorization 走通
  2. _authenticate_ws ?token= 兜底走通 (CLAUDE.md 模式 5)
  3. _authenticate_ws 无 token 拒收返 None
  4. _authenticate_ws 坏 token 拒收返 None
  5. 状态变化轮询: processing → parsed (terminal) 后停止
  6. 状态变化轮询: processing → failed (terminal) 后停止
  7. 状态变化轮询: raw_resume 不存在返 not_found

注: WS 端到端测试 (TestClient.websocket_connect) 涉及 starlette TestClient 与
pytest-asyncio 事件循环冲突, 推 v0.6b.1 走 Playwright e2e。unit test 覆盖核心逻辑。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeWebSocket:
    """Mock starlette WebSocket — 只实现 _authenticate_ws 用的属性。"""

    def __init__(self, headers: dict | None = None, query_params: dict | None = None):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self._closed_with_code: int | None = None

    async def close(self, code: int = 1000):
        self._closed_with_code = code


@pytest.mark.asyncio
async def test_authenticate_ws_via_authorization_header():
    """_authenticate_ws 优先读 Authorization: Bearer header。"""
    from app.api.raw_resume import _authenticate_ws

    ws = _FakeWebSocket(
        headers={"authorization": "Bearer my-jwt-token"},
    )
    fake_payload = {"sub": "user-1"}

    with patch("app.api.raw_resume.decode_access_token", return_value=fake_payload) as mock_decode:
        user_id = await _authenticate_ws(ws)

    assert user_id == "user-1"
    mock_decode.assert_called_once_with("my-jwt-token")
    assert ws._closed_with_code is None


@pytest.mark.asyncio
async def test_authenticate_ws_via_query_token_fallback():
    """_authenticate_ws ?token= 兜底 (CLAUDE.md 模式 5 推 WS 版)。"""
    from app.api.raw_resume import _authenticate_ws

    ws = _FakeWebSocket(
        headers={},
        query_params={"token": "query-jwt"},
    )
    fake_payload = {"sub": "user-2"}

    with patch("app.api.raw_resume.decode_access_token", return_value=fake_payload) as mock_decode:
        user_id = await _authenticate_ws(ws)

    assert user_id == "user-2"
    mock_decode.assert_called_once_with("query-jwt")


@pytest.mark.asyncio
async def test_authenticate_ws_no_token_closes_with_1008():
    """_authenticate_ws 无 token 返 None + close(1008 policy violation)。"""
    from app.api.raw_resume import _authenticate_ws

    ws = _FakeWebSocket(headers={}, query_params={})
    user_id = await _authenticate_ws(ws)

    assert user_id is None
    assert ws._closed_with_code == 1008


@pytest.mark.asyncio
async def test_authenticate_ws_bad_token_closes_with_1008():
    """_authenticate_ws 坏 token (decode 抛异常) 返 None + close(1008)。"""
    from app.api.raw_resume import _authenticate_ws
    from jose import JWTError

    ws = _FakeWebSocket(headers={"authorization": "Bearer bad-jwt"})

    with patch("app.api.raw_resume.decode_access_token", side_effect=JWTError("invalid")):
        user_id = await _authenticate_ws(ws)

    assert user_id is None
    assert ws._closed_with_code == 1008


@pytest.mark.asyncio
async def test_state_polling_emits_processing_then_parsed_then_stops():
    """状态变化逻辑: processing → parsed (terminal) 后停止轮询。"""
    from app.api.raw_resume import _poll_state_until_terminal

    states = iter([
        {"raw_resume_id": "rr-1", "status": "processing", "candidate_id": None,
         "error_message": None, "updated_at": "2026-06-07T10:00:00+00:00"},
        {"raw_resume_id": "rr-1", "status": "parsed", "candidate_id": "cand-1",
         "error_message": None, "updated_at": "2026-06-07T10:00:05+00:00"},
    ])

    async def fake_poll(raw_resume_id: str):
        return next(states)

    ws = _FakeWebSocket()
    emitted: list[dict] = []

    async def fake_send_json(payload: dict):
        emitted.append(payload)

    async def fast_sleep(_seconds: float):
        return None

    with patch("app.api.raw_resume.poll_parse_task", side_effect=fake_poll):
        with patch("app.api.raw_resume.asyncio.sleep", side_effect=fast_sleep):
            await _poll_state_until_terminal(ws, "rr-1", fake_send_json)

    assert len(emitted) == 2
    assert emitted[0]["status"] == "processing"
    assert emitted[1]["status"] == "parsed"
    assert emitted[1]["candidate_id"] == "cand-1"


@pytest.mark.asyncio
async def test_state_polling_emits_processing_then_failed_then_stops():
    """状态变化逻辑: processing → failed (terminal) 后停止轮询。"""
    from app.api.raw_resume import _poll_state_until_terminal

    states = iter([
        {"raw_resume_id": "rr-2", "status": "processing", "candidate_id": None,
         "error_message": None, "updated_at": "2026-06-07T10:00:00+00:00"},
        {"raw_resume_id": "rr-2", "status": "failed", "candidate_id": None,
         "error_message": "low_confidence_or_extraction_error", "updated_at": "2026-06-07T10:00:03+00:00"},
    ])

    async def fake_poll(raw_resume_id: str):
        return next(states)

    ws = _FakeWebSocket()
    emitted: list[dict] = []

    async def fake_send_json(payload: dict):
        emitted.append(payload)

    async def fast_sleep(_seconds: float):
        return None

    with patch("app.api.raw_resume.poll_parse_task", side_effect=fake_poll):
        with patch("app.api.raw_resume.asyncio.sleep", side_effect=fast_sleep):
            await _poll_state_until_terminal(ws, "rr-2", fake_send_json)

    assert len(emitted) == 2
    assert emitted[0]["status"] == "processing"
    assert emitted[1]["status"] == "failed"
    assert "low_confidence" in emitted[1]["error_message"]


@pytest.mark.asyncio
async def test_state_polling_not_found_emits_not_found():
    """状态变化逻辑: poll 返 None (raw_resume 不存在) 发 not_found 后停止。"""
    from app.api.raw_resume import _poll_state_until_terminal

    async def fake_poll(raw_resume_id: str):
        return None

    ws = _FakeWebSocket()
    emitted: list[dict] = []

    async def fake_send_json(payload: dict):
        emitted.append(payload)

    async def fast_sleep(_seconds: float):
        return None

    with patch("app.api.raw_resume.poll_parse_task", side_effect=fake_poll):
        with patch("app.api.raw_resume.asyncio.sleep", side_effect=fast_sleep):
            await _poll_state_until_terminal(ws, "rr-not-exists", fake_send_json)

    assert len(emitted) == 1
    assert emitted[0]["status"] == "not_found"
    assert emitted[0]["raw_resume_id"] == "rr-not-exists"
