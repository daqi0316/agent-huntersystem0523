"""T3 SSE 集成测试（真实 Redis Streams + Last-Event-ID 重放）

覆盖 plan §3 验收项：
  1. emit 5 条 → SSE 客户端实时收到 5 条
  2. 断线 → emit 2 条 → 重连带 Last-Event-ID → 收到 2 条（重放）

要求：dev 环境有真实 Redis（localhost:6379）。无 Redis 时测试 skip。
"""

import asyncio
import os

import httpx
import pytest
import requests

# 真实 Redis（dev 起容器时）
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# 用 127.0.0.1（IPv4）避免 httpx 默认解析 ::1 失败（uvicorn 只 listen IPv4）
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")
TEST_EMAIL = "e2e-tester@test.com"
TEST_PASSWORD = "E2ePass123!"


def _redis_available() -> bool:
    """快速探测 Redis 是否在线（避免 5s 超时）。"""
    try:
        import socket
        s = socket.create_connection(("127.0.0.1", 6379), timeout=1.0)
        s.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    os.getenv("REDIS_E2E") != "1" or not _redis_available(),
    reason="Set REDIS_E2E=1 and ensure Redis on 127.0.0.1:6379 (docker compose up postgres redis qdrant minio)",
)


@pytest.fixture
def auth_token():
    """登录拿 token（用于 SSE ?token= query 鉴权）。"""
    res = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    if res.status_code != 200:
        pytest.skip(f"Login failed: {res.status_code} {res.text}")
    data = res.json()
    token = data.get("data", data).get("access_token")
    assert token, f"no token in {data}"
    return token


@pytest.fixture
async def cleanup_streams():
    """测试前后清理测试 user 的 stream。"""
    import redis.asyncio as aioredis

    user_id = "t3-e2e-user"
    key = f"agent_events:stream:{user_id}"

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    await client.delete(key)
    yield user_id
    await client.delete(key)
    await client.aclose()


async def _consume_sse(token: str, last_event_id: str | None = None, max_events: int = 10, timeout: float = 5.0) -> list[tuple[str | None, str, dict]]:
    """消费 SSE 流直到收 max_events 条或 timeout。

    Returns: list of (event_id, event_name, data_dict)
    """
    events: list[tuple[str | None, str, dict]] = []
    params: dict = {"token": token}
    if last_event_id:
        params["last_event_id"] = last_event_id

    url = f"{API_BASE}/agent/events"
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            buf: list[str] = []
            async for chunk in response.aiter_text():
                buf.append(chunk)
                text = "".join(buf)
                while "\n\n" in text:
                    raw, text = text.split("\n\n", 1)
                    buf = [text]
                    event_id: str | None = None
                    event_name = "message"
                    data_lines: list[str] = []
                    for line in raw.split("\n"):
                        if line.startswith("id: "):
                            event_id = line[4:].strip()
                        elif line.startswith("event: "):
                            event_name = line[7:].strip()
                        elif line.startswith("data: "):
                            data_lines.append(line[6:])
                    if data_lines:
                        import json as _json
                        try:
                            data_dict = _json.loads("\n".join(data_lines))
                        except _json.JSONDecodeError:
                            data_dict = {"_raw": "\n".join(data_lines)}
                        events.append((event_id, event_name, data_dict))
                        if len(events) >= max_events:
                            return events
    return events


@pytest.mark.asyncio
async def test_emit_5_events_realtime(auth_token, cleanup_streams):
    """验收 1：emit 5 条 → SSE 客户端实时收到 5 条。"""
    import json

    from app.api import agent_events

    user_id = "t3-e2e-user"

    # 后台 consumer 协程：消费 SSE 流
    consumer = asyncio.create_task(
        _consume_sse(auth_token, max_events=5, timeout=8.0)
    )

    # 给 consumer 时间连上 SSE
    await asyncio.sleep(0.5)

    # emit 5 条
    for i in range(5):
        await agent_events.emit_ai_notification(
            user_id=user_id,
            kind="candidate_status_changed",
            title=f"实时通知 {i+1}",
            body=f"body {i+1}",
            action_url=f"/candidates/{i}",
        )
        await asyncio.sleep(0.05)

    events = await asyncio.wait_for(consumer, timeout=5.0)

    notification_events = [e for e in events if e[1] == "notification.fired"]
    assert len(notification_events) == 5, (
        f"expected 5 notification.fired, got {len(notification_events)}: {events}"
    )

    for i, (eid, ename, data) in enumerate(notification_events):
        assert ename == "notification.fired"
        assert data.get("title") == f"实时通知 {i+1}"


@pytest.mark.asyncio
async def test_replay_after_reconnect_with_last_event_id(auth_token, cleanup_streams):
    """验收 2：断线 → emit 2 条 → 重连带 Last-Event-ID → 收到 2 条（重放）。"""
    import json

    from app.api import agent_events

    user_id = "t3-e2e-user"

    # 第一步：连 SSE 拿一个 lastEventId（connected 事件没有，但下一条会带）
    consumer1 = asyncio.create_task(
        _consume_sse(auth_token, max_events=1, timeout=5.0)
    )
    await asyncio.sleep(0.5)

    # emit 1 条让 consumer1 收到
    msg_id_1 = await agent_events.emit_ai_notification(
        user_id=user_id,
        kind="candidate_status_changed",
        title="在线通知 1",
        body="first",
        action_url="/candidates/1",
    )
    await asyncio.sleep(0.2)

    # 拿 events 列表
    events1 = await asyncio.wait_for(consumer1, timeout=3.0)
    notification_1 = [e for e in events1 if e[1] == "notification.fired"]
    assert len(notification_1) == 1
    eid_1 = notification_1[0][0]
    assert eid_1, f"first event should have id, got {notification_1[0]}"
    print(f"first event id: {eid_1}")

    # 第二步：emit 2 条（断线期间）
    for i in range(2):
        await agent_events.emit_ai_notification(
            user_id=user_id,
            kind="approval_requested",
            title=f"断线期间通知 {i+1}",
            body=f"offline {i+1}",
            action_url=f"/candidates/{i+1}",
        )
        await asyncio.sleep(0.05)

    # 等 streams 持久化
    await asyncio.sleep(0.5)

    # 第三步：重连带 last_event_id=eid_1
    consumer2 = asyncio.create_task(
        _consume_sse(
            auth_token,
            last_event_id=eid_1,
            max_events=3,  # 期望收到 2 条重放 + 1 条实时（如果有）
            timeout=5.0,
        )
    )
    events2 = await asyncio.wait_for(consumer2, timeout=5.0)
    replayed = [e for e in events2 if e[1] == "notification.fired"]

    # 至少收到 2 条（断线期间 emit 的）
    assert len(replayed) >= 2, (
        f"expected ≥2 replayed events, got {len(replayed)}: {events2}"
    )

    # 验证重放是按时间序
    titles = [r[2].get("title", "") for r in replayed[:2]]
    assert titles == ["断线期间通知 1", "断线期间通知 2"], (
        f"replay order wrong: {titles}"
    )

    # 验证重放事件的 id 严格大于 eid_1
    for eid, _, _ in replayed[:2]:
        assert eid and eid > eid_1, f"replay id {eid} should be > {eid_1}"


@pytest.mark.asyncio
async def test_persistence_maxlen_1000(auth_token, cleanup_streams):
    """验收 3：XADD MAXLEN ~ 1000 不会无限增长。

    策略：emit 1500 条 → 验证 XLEN < 1100（裁剪生效）。
    """
    import redis.asyncio as aioredis

    from app.api import agent_events

    user_id = "t3-e2e-user"

    # emit 1500 条
    for i in range(1500):
        await agent_events.emit_ai_notification(
            user_id=user_id,
            kind="system",
            title=f"bulk {i}",
            body="",
        )

    # 验证 Stream 被裁剪
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        length = await client.xlen(f"agent_events:stream:{user_id}")
        # MAXLEN ~ 1000（approximate=True）— 实际可能略多
        assert length < 1100, f"Stream not trimmed: {length} entries"
        assert length >= 900, f"Stream unexpectedly small: {length}"
    finally:
        await client.aclose()
