"""P5-8: 配额/限流 — 3-key 滑动窗口 (org/user/IP) + per-org quota + 飞书 + 灰度。

设计:
- 3 个独立限流 key:
  - org_id: 100 req/min (per org) — 防团队滥用
  - user_id: 60 req/min (per user) — 防个人刷
  - client_ip: 30 req/min (per IP, 匿名端点) — 防恶意
- 任意一个 key 超限 → 429
- per-org LLM token quota: 超 80% 预警, 超 100% 自动降级
- 灰度发布: RATELIMIT_ROLLOUT_PCT 0-100, 1% 起步
- 飞书通知: owner webhook (超 quota 时)
- A1 增强: module-level singleton store, admin reset/state 接口可访问
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateStoreProtocol:
    async def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        raise NotImplementedError

    async def remaining(self, key: str, limit: int, window: float) -> int:
        raise NotImplementedError

    async def reset(self, key: str) -> None:
        raise NotImplementedError

    async def incr_counter(self, key: str, amount: int = 1) -> int:
        raise NotImplementedError

    async def get_counter(self, key: str) -> int:
        raise NotImplementedError


class InMemoryRateStore(RateStoreProtocol):
    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)

    def _prune(self, key: str, window: float) -> None:
        now = time.monotonic()
        cutoff = now - window
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]

    async def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        self._prune(key, window)
        current = len(self._buckets[key])
        if current >= limit:
            return False, 0
        self._buckets[key].append(time.monotonic())
        return True, limit - current - 1

    async def remaining(self, key: str, limit: int, window: float) -> int:
        self._prune(key, window)
        return max(0, limit - len(self._buckets[key]))

    async def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    async def incr_counter(self, key: str, amount: int = 1) -> int:
        self._counters[key] += amount
        return self._counters[key]

    async def get_counter(self, key: str) -> int:
        return self._counters.get(key, 0)


class RedisStore(RateStoreProtocol):
    """Redis-backed: 跨副本共享, 原子 INCR+EXPIRE (Lua 风格)。"""

    def __init__(self, redis_client):
        self._redis = redis_client

    async def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        pipe = self._redis.pipeline()
        await pipe.incr(key)
        await pipe.ttl(key)
        count, ttl = await pipe.execute()
        if count == 1:
            await self._redis.expire(key, int(window))
        if count > limit:
            return False, 0
        return True, max(0, limit - count)

    async def remaining(self, key: str, limit: int, window: float) -> int:
        val = await self._redis.get(key)
        if val is None:
            return limit
        return max(0, limit - int(val))

    async def reset(self, key: str) -> None:
        await self._redis.delete(key)

    async def incr_counter(self, key: str, amount: int = 1) -> int:
        return await self._redis.incrby(key, amount)

    async def get_counter(self, key: str) -> int:
        val = await self._redis.get(key)
        return int(val) if val is not None else 0


# 默认 3-key 限流配置
DEFAULT_LIMITS = {
    "org": (100, 60),   # 100 req/min per org
    "user": (60, 60),   # 60 req/min per user
    "ip": (30, 60),     # 30 req/min per IP (匿名端点)
}


# ── A1: Module-level singleton store ────────────────────────────
# 之前 create_rate_limit_middleware() 每次都新建 InMemoryRateStore，
# 导致外部拿不到引用、admin 端点无法 reset/inspect。
# 改为 module-level singleton：middleware 闭包用同一个 store，admin 接口
# 拿同一引用。
# 初始化策略: get_rate_store() 默认返 InMemoryRateStore (sync, 零依赖);
# Redis 模式需 lifespan 启动时显式 await init_rate_store()。

_rate_store: RateStoreProtocol | None = None


def get_rate_store() -> RateStoreProtocol:
    """获取限流存储单例。默认 InMemory，lifespan 启动时 init_rate_store() 可切 Redis。"""
    global _rate_store
    if _rate_store is None:
        _rate_store = InMemoryRateStore()
        logger.info("rate_limit: using InMemory store (default; call init_rate_store() for Redis)")
    return _rate_store


def set_rate_store(store: RateStoreProtocol) -> None:
    """显式设置 store（测试/lifespan 启动用）。"""
    global _rate_store
    _rate_store = store


async def init_rate_store() -> None:
    """lifespan 启动时调用：按环境选 Redis 或 InMemory store。

    REDIS_URL 非空时用 Redis（共享存储，跨副本一致）;
    否则 InMemory（单进程，重启丢状态，dev 够用）。
    """
    global _rate_store
    from app.core.config import settings
    redis_url = getattr(settings, "redis_url", None) or os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            from app.core.redis import get_redis
            client = await get_redis()
            _rate_store = RedisStore(client)
            logger.info("rate_limit: using Redis store at %s", _redis_mask(redis_url))
            return
        except Exception as e:
            logger.warning("rate_limit: Redis init failed (%s), fallback to InMemory", e)
    _rate_store = InMemoryRateStore()
    logger.info("rate_limit: using InMemory store (no REDIS_URL or init failed)")


def _redis_mask(url: str) -> str:
    """隐藏 redis url 中的密码字段。"""
    if "@" in url:
        prefix, suffix = url.split("@", 1)
        if ":" in prefix:
            scheme_user, _ = prefix.rsplit(":", 1)
            return f"{scheme_user}:***@{suffix}"
    return url


async def admin_reset_all() -> dict:
    """重置所有限流状态（admin 端点调用）。

    适用场景: health-check/load test 留下限流污染, 真实用户访问时撞 429。
    返: {"reset_keys": N, "reset_counters": M}
    """
    store = get_rate_store()
    snapshot = await get_state_snapshot()
    if isinstance(store, InMemoryRateStore):
        bucket_count = len(store._buckets)
        counter_count = len(store._counters)
        store._buckets.clear()
        store._counters.clear()
    elif isinstance(store, RedisStore):
        # Redis: SCAN + DEL 所有 ratelimit:* key（不删 quota:*）
        bucket_count = 0
        try:
            redis = store._redis
            async for k in redis.scan_iter(match="ratelimit:*"):
                await redis.delete(k)
                bucket_count += 1
        except Exception as e:
            logger.warning("admin_reset_all: redis scan failed: %s", e)
        counter_count = 0
    else:
        bucket_count, counter_count = 0, 0
    logger.info("admin_reset_all: cleared %d buckets, %d counters", bucket_count, counter_count)
    return {
        "reset_buckets": bucket_count,
        "reset_counters": counter_count,
        "snapshot_before_reset": snapshot,
    }


async def get_state_snapshot() -> dict:
    """获取限流状态快照（admin/inspect 端点用）。

    返: {"active_buckets": N, "active_counters": M, "store_type": "..."}
    """
    store = get_rate_store()
    if isinstance(store, InMemoryRateStore):
        active_buckets = len(store._buckets)
        active_counters = sum(1 for v in store._counters.values() if v > 0)
        return {
            "store_type": "in_memory",
            "active_buckets": active_buckets,
            "active_counters": active_counters,
            "limits": DEFAULT_LIMITS,
        }
    if isinstance(store, RedisStore):
        try:
            redis = store._redis
            bucket_count = 0
            async for _ in redis.scan_iter(match="ratelimit:*", count=1000):
                bucket_count += 1
            counter_count = 0
            async for _ in redis.scan_iter(match="quota:*", count=1000):
                counter_count += 1
            return {
                "store_type": "redis",
                "active_buckets": bucket_count,
                "active_counters": counter_count,
                "limits": DEFAULT_LIMITS,
            }
        except Exception as e:
            logger.warning("get_state_snapshot: redis scan failed: %s", e)
            return {
                "store_type": "redis",
                "error": str(e),
                "limits": DEFAULT_LIMITS,
            }
    return {
        "store_type": type(store).__name__,
        "limits": DEFAULT_LIMITS,
    }


@dataclass
class QuotaConfig:
    """per-org LLM token 月度配额 (来自 organization 表)。"""
    plan: str
    monthly_limit: int


PLAN_QUOTAS_TOKENS = {
    "starter": 500_000,
    "pro": 2_000_000,
    "enterprise": 10_000_000,
}


class QuotaTracker:
    """跟踪每个 org 本月已用 LLM token。

    生产用 Redis 持久化; 本地用内存 (P5-7 默认 mock 走内存)。
    """

    def __init__(self, store: RateStoreProtocol | None = None):
        self._store = store or InMemoryRateStore()

    def _key(self, org_id: str) -> str:
        import datetime
        year_month = datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
        return f"quota:llm_tokens:{org_id}:{year_month}"

    async def used(self, org_id: str) -> int:
        return await self._store.get_counter(self._key(org_id))

    async def consume(self, org_id: str, tokens: int) -> int:
        return await self._store.incr_counter(self._key(org_id), tokens)

    async def remaining(self, org_id: str, monthly_limit: int) -> int:
        return max(0, monthly_limit - await self.used(org_id))

    async def check_and_consume(
        self, org_id: str, plan: str, tokens: int
    ) -> tuple[bool, int, int]:
        """返 (allowed, remaining_after, monthly_limit). 超 100% 拒绝。"""
        limit = PLAN_QUOTAS_TOKENS.get(plan, 100_000)
        used_before = await self.used(org_id)
        if used_before >= limit:
            return False, 0, limit
        await self.consume(org_id, tokens)
        used_after = await self.used(org_id)
        return used_after <= limit, max(0, limit - used_after), limit


_quota_tracker: Optional[QuotaTracker] = None


def get_quota_tracker() -> QuotaTracker:
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = QuotaTracker()
    return _quota_tracker


def reset_quota_tracker() -> None:
    global _quota_tracker
    _quota_tracker = None


async def send_quota_breach_notification(org_id: str, plan: str, used: int, limit: int) -> bool:
    """超 quota 80% 时通知 owner (飞书 webhook)。"""
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        return False
    pct = used / max(limit, 1) * 100
    content = (
        f"⚠️ [P2] LLM token 配额预警\n"
        f"Org: {org_id}\n"
        f"Plan: {plan}\n"
        f"已用: {used:,} / {limit:,} ({pct:.1f}%)\n"
        f"建议: 升级 plan 或等下月初重置"
    )
    payload = {"msg_type": "text", "content": {"text": content}}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error("feishu quota notify failed: %s", e)
        return False


# 灰度发布 (按 user_id hash 取模)
def is_in_rollout(user_key: str, rollout_pct: int) -> bool:
    """返 True 表示此 key 在灰度范围内。rollout_pct 0-100。"""
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0:
        return False
    import hashlib
    h = int(hashlib.md5(user_key.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 100) < rollout_pct


def extract_limit_keys(request: Request) -> dict[str, Optional[str]]:
    """从 request 提取 3 个 key (缺失则为 None)。"""
    ip_key = request.client.host if request.client else None
    auth = request.headers.get("authorization", "")
    user_id = None
    org_id = None
    if auth.lower().startswith("bearer "):
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(auth.split(" ", 1)[1])
            user_id = payload.get("sub")
            org_id = payload.get("current_org_id")
        except Exception:
            pass
    return {"ip": ip_key, "user": user_id, "org": org_id}


def create_rate_limit_middleware(
    limit: int = 100,
    window: int = 60,
    exclude_paths: tuple[str, ...] = (
        "/health", "/metrics", "/docs", "/redoc", "/openapi.json",
    ),
    store: RateStoreProtocol | None = None,
    limits: dict[str, tuple[int, int]] | None = None,
    rollout_pct: int = 100,
):
    """Factory: 3-key 限流 (org/user/IP) + 灰度。

    limits: {"org": (100, 60), "user": (60, 60), "ip": (30, 60)}
    rollout_pct: 0-100, 灰度比例
    A1: 不传 store 时用 module-level singleton (admin 接口能拿到同一引用)。
    """
    effective_store = store if store is not None else get_rate_store()
    effective_limits = limits or DEFAULT_LIMITS

    async def rate_limit_dispatch(request: Request, call_next):
        if (
            request.url.path in exclude_paths
            or request.url.path.startswith("/docs")
            or request.url.path.startswith("/redoc")
        ):
            return await call_next(request)

        # 灰度发布: 按 IP hash 决定是否启用
        ip_for_rollout = request.client.host if request.client else "unknown"
        if not is_in_rollout(ip_for_rollout, rollout_pct):
            return await call_next(request)

        keys = extract_limit_keys(request)
        path = request.url.path

        most_restrictive: Optional[dict] = None
        for key_type, key_value in keys.items():
            if not key_value:
                continue
            limit_value, window_value = effective_limits.get(key_type, (limit, window))
            redis_key = f"ratelimit:{key_type}:{key_value}:{path}"
            allowed, remaining = await effective_store.check(redis_key, limit_value, window_value)
            try:
                from app.core.telemetry import record_rate_limit_event
                if allowed:
                    record_rate_limit_event(key_type=key_type, path=path, blocked=False)
                else:
                    record_rate_limit_event(key_type=key_type, path=path, blocked=True)
            except Exception:
                pass
            if not allowed:
                logger.warning(
                    "rate limit exceeded: type=%s key=%s path=%s limit=%d/%ds",
                    key_type, key_value, path, limit_value, window_value,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "rate_limited",
                        "message": f"请求过快 ({key_type} 维度), 请稍后重试",
                        "retry_after": window_value,
                    },
                    headers={
                        "Retry-After": str(window_value),
                        "X-RateLimit-Limit": str(limit_value),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + window_value),
                        "X-RateLimit-Key": key_type,
                    },
                )
            if most_restrictive is None or remaining < most_restrictive["remaining"]:
                most_restrictive = {"limit": limit_value, "remaining": remaining}

        response = await call_next(request)
        if most_restrictive:
            response.headers["X-RateLimit-Limit"] = str(most_restrictive["limit"])
            response.headers["X-RateLimit-Remaining"] = str(most_restrictive["remaining"])
        return response

    return rate_limit_dispatch
