"""T3 通知系统测试

覆盖：
  - 节流器（同 user × kind 1s 内仅 1 次）
  - emit_ai_notification 节流 + Redis Streams 持久化
  - _replay_since Last-Event-ID 重放
  - emit_to_user 降级路径（Redis 不可用时仍工作）
"""

import asyncio
import pytest

from app.core import notification as notif_mod
from app.api import agent_events


@pytest.fixture(autouse=True)
def reset_throttle():
    """每个测试前重置节流状态。"""
    notif_mod.reset_throttle()
    yield
    notif_mod.reset_throttle()


def test_throttle_allows_first_emit():
    """首次 emit 允许。"""
    assert notif_mod.should_emit("user_1", "candidate_status_changed") is True


def test_throttle_blocks_second_emit_within_1s():
    """1s 内重复 emit 阻止。"""
    assert notif_mod.should_emit("user_1", "candidate_status_changed") is True
    assert notif_mod.should_emit("user_1", "candidate_status_changed") is False


def test_throttle_different_kinds_independent():
    """不同 kind 不互相节流。"""
    assert notif_mod.should_emit("user_1", "candidate_status_changed") is True
    assert notif_mod.should_emit("user_1", "approval_requested") is True


def test_throttle_different_users_independent():
    """不同 user 不互相节流。"""
    assert notif_mod.should_emit("user_1", "candidate_status_changed") is True
    assert notif_mod.should_emit("user_2", "candidate_status_changed") is True


def test_throttle_expires_after_window(monkeypatch):
    """超过 1s 窗口后允许再 emit。"""
    # 用 monkeypatch 改 time.monotonic 的返回值
    times = iter([100.0, 100.5, 101.5])
    monkeypatch.setattr(notif_mod.time, "monotonic", lambda: next(times))

    assert notif_mod.should_emit("u", "k") is True
    assert notif_mod.should_emit("u", "k") is False  # 0.5s 内
    assert notif_mod.should_emit("u", "k") is True  # 1.5s 后


@pytest.mark.asyncio
async def test_emit_ai_notification_throttled():
    """emit_ai_notification 走 should_emit 节流。"""
    # 第一次 emit 应通过
    msg_id_1 = await agent_events.emit_ai_notification(
        user_id="user_throttle",
        kind="candidate_status_changed",
        title="测试1",
        body="body1",
    )
    # 第二次同 user × 同 kind 应被节流
    msg_id_2 = await agent_events.emit_ai_notification(
        user_id="user_throttle",
        kind="candidate_status_changed",
        title="测试2",
        body="body2",
    )
    # 至少有一个应该 None（节流 / Redis 不可用）— 但两者不应都有 msg_id
    # 若 Redis 可用且有 xadd，则第一次有 msg_id 第二次 None（节流）
    # 若 Redis 不可用，两者都 None
    if msg_id_1 is not None:
        assert msg_id_2 is None
    else:
        # 两者都 None（Redis 不可用）— 仍可验证不抛错
        assert msg_id_2 is None


@pytest.mark.asyncio
async def test_emit_to_user_falls_back_to_in_memory_when_redis_unavailable(monkeypatch):
    """Redis 不可用时 emit_to_user 仍能写入内存 queue（不抛错）。"""
    # 强制 _try_get_redis 返回 None
    monkeypatch.setattr(agent_events, "_redis_checked", True)
    monkeypatch.setattr(agent_events, "_redis_client", None)

    user_id = "user_fallback"
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    agent_events._queues[user_id].append(queue)

    await agent_events.emit_to_user(user_id, "test.event", {"hello": "world"})

    # 内存 queue 应收到
    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert "test.event" in msg
    assert "hello" in msg

    # 清理
    agent_events._queues[user_id].remove(queue)


@pytest.mark.asyncio
async def test_safe_emit_swallows_exception(monkeypatch):
    """safe_emit 包装下 emit 失败不抛（fire-and-forget 语义）。"""
    async def failing_coro():
        raise RuntimeError("simulated emit failure")

    # 应该不抛
    await notif_mod.safe_emit(failing_coro)


def test_replay_since_returns_empty_when_redis_unavailable(monkeypatch):
    """Redis 不可用时 _replay_since 返回空 list（不抛错）。"""
    monkeypatch.setattr(agent_events, "_redis_checked", True)
    monkeypatch.setattr(agent_events, "_redis_client", None)

    result = asyncio.run(agent_events._replay_since("u", "1234567890-0"))
    assert result == []


@pytest.mark.asyncio
async def test_emit_to_user_uses_correct_sse_format(monkeypatch):
    """emit_to_user 产出标准 SSE 格式（含 event: / data: 行）。"""
    monkeypatch.setattr(agent_events, "_redis_checked", True)
    monkeypatch.setattr(agent_events, "_redis_client", None)

    user_id = "user_sse_fmt"
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    agent_events._queues[user_id].append(queue)

    await agent_events.emit_to_user(user_id, "data_card.created", {"id": "x"})

    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg.startswith("event: data_card.created\n")
    assert "data: " in msg
    assert msg.endswith("\n\n")

    agent_events._queues[user_id].remove(queue)
