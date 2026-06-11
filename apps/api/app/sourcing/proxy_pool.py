"""代理池 — 三层代理管理 + IP 质量评分 + 自动剔除 + 健康探测"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

from app.sourcing.config import sourcing_settings

logger = logging.getLogger(__name__)

REDIS_PREFIX = "sourcing:proxy:"
MAX_FAILURES = 5          # 超过此值自动剔除
MAX_LATENCY_MS = 8000     # 超过此延迟自动降分
FETCH_TTL = 600            # 代理列表 Redis 缓存 10min
REFILL_MIN = 3             # 低于此数量触发补充
HEALTH_CHECK_INTERVAL = 300  # 健康探测间隔 5min
SCORE_DECAY_INTERVAL = 3600  # 分数衰减间隔 1h
QUALITY_THRESHOLD = -10     # 分数低于此值自动剔除
LATENCY_WEIGHT = 0.3       # 延迟在综合评分中的权重
FAILURE_WEIGHT = 0.7       # 失败在综合评分中的权重


class ProxyPool:
    """代理池管理（Redis 后端 + 自动补充 + 失败评分）"""

    TIERS = {
        "premium":  {"type": "residential_china", "cost_per_gb": 5},
        "standard": {"type": "residential_global", "cost_per_gb": 0.8},
        "mobile":   {"type": "mobile", "cost_per_gb": 8},
    }

    def __init__(self, redis=None):
        self.redis = redis
        self._in_memory: dict[str, list[dict[str, Any]]] = {t: [] for t in self.TIERS}
        self._fetch_lock = asyncio.Lock()

    # ── 公共接口 ──

    async def get_proxy(self, platform: str, anti_crawl_level: int) -> str | None:
        """按平台反爬等级返回代理

        - boss_zhipin 强制走 premium（住宅代理）
        - anti_crawl_level >= 4 → premium
        - anti_crawl_level >= 2 → standard
        - 其他 → None（直连）
        """
        if platform == "boss_zhipin":
            tier = "premium"
        elif anti_crawl_level >= 4:
            tier = "premium"
        elif anti_crawl_level >= 2:
            tier = "standard"
        else:
            return None

        return await self._acquire(tier)

    async def report_failure(self, proxy: str, platform: str, error_type: str = "unknown"):
        """报告代理失败 → 质量分下降，超阈值自动剔除"""
        logger.debug("Proxy failure: %s on %s (%s)", proxy, platform, error_type)
        penalty = 2 if error_type in ("TIMEOUT", "CONNECTION_RESET") else 1
        if self.redis:
            for tier in self.TIERS:
                key = f"{REDIS_PREFIX}{tier}"
                current = await self.redis.zscore(key, proxy)
                if current is not None:
                    new_score = current - penalty
                    await self.redis.zadd(key, {proxy: new_score})
                    if new_score <= QUALITY_THRESHOLD:
                        await self.redis.zrem(key, proxy)
                        logger.info("Evicted low-quality proxy %s from %s (score=%.1f)", proxy, tier, new_score)
                else:
                    score = await self.redis.zincrby(key, 1, proxy)
                    if score is not None and score >= MAX_FAILURES:
                        await self.redis.zrem(key, proxy)
                        logger.info("Evicted proxy %s from %s (failures=%d)", proxy, tier, score)
        else:
            for tier_proxies in self._in_memory.values():
                for p in tier_proxies:
                    if p.get("url") == proxy:
                        p["failures"] = p.get("failures", 0) + 1
                        p["quality_score"] = p.get("quality_score", 0) - penalty
                        if p["quality_score"] <= QUALITY_THRESHOLD:
                            tier_proxies.remove(p)
                        return

    async def report_success(self, proxy: str, platform: str, latency_ms: float | None = None):
        """报告代理成功 → 质量分提升 + 记录延迟"""
        if self.redis:
            for tier in self.TIERS:
                key = f"{REDIS_PREFIX}{tier}"
                current = await self.redis.zscore(key, proxy)
                if current is not None:
                    boost = 0.5 if (latency_ms is None or latency_ms < 2000) else 0.1
                    await self.redis.zadd(key, {proxy: current + boost})
                if latency_ms is not None:
                    latency_key = f"{REDIS_PREFIX}{tier}:latency"
                    await self.redis.hset(latency_key, proxy, latency_ms)
                    await self.redis.expire(latency_key, 3600)
        else:
            for tier_proxies in self._in_memory.values():
                for p in tier_proxies:
                    if p.get("url") == proxy:
                        p["quality_score"] = p.get("quality_score", 0) + 0.5
                        if latency_ms is not None:
                            p["latency_ms"] = latency_ms
                        return

    async def check_proxy_health(self, proxy: str) -> dict:
        """探测单个代理的延迟和可达性"""
        result = {"proxy": proxy, "latency_ms": None, "alive": False, "error": None}
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(proxies=proxy, timeout=5) as client:
                resp = await client.get("http://httpbin.org/ip", timeout=5)
                latency = int((time.monotonic() - start) * 1000)
                result["latency_ms"] = latency
                result["alive"] = resp.is_success
        except Exception as e:
            result["error"] = str(e)
        return result

    async def run_health_check(self) -> dict[str, Any]:
        """对所有代理执行批量健康探测 → 移除死代理 + 更新延迟分"""
        logger.info("Starting proxy health check...")
        total = 0
        removed = 0
        details = {"checked": 0, "removed": 0, "alive": 0, "dead": 0, "by_tier": {}}
        for tier in self.TIERS:
            if self.redis:
                key = f"{REDIS_PREFIX}{tier}"
                proxies = await self.redis.zrange(key, 0, -1)
            else:
                proxies = [p["url"] for p in self._in_memory.get(tier, [])]
            tier_alive = 0
            tier_dead = 0
            tier_removed = 0
            sem = asyncio.Semaphore(5)

            async def check_one(proxy_url: str) -> None:
                nonlocal tier_alive, tier_dead, tier_removed
                async with sem:
                    info = await self.check_proxy_health(proxy_url)
                    if info["alive"]:
                        tier_alive += 1
                        await self._update_health_score(tier, proxy_url, info["latency_ms"])
                    else:
                        tier_dead += 1
                        if self.redis:
                            await self.redis.zrem(key, proxy_url)
                        else:
                            self._in_memory[tier] = [p for p in self._in_memory[tier] if p.get("url") != proxy_url]
                        tier_removed += 1

            tasks = [check_one(p) for p in proxies]
            await asyncio.gather(*tasks)
            total += len(proxies)
            removed += tier_removed
            details["by_tier"][tier] = {"total": len(proxies), "alive": tier_alive, "dead": tier_dead, "removed": tier_removed}
            logger.info("Proxy health %s: %d alive, %d dead, %d removed", tier, tier_alive, tier_dead, tier_removed)

        details["checked"] = total
        details["removed"] = removed
        details["alive"] = total - removed
        details["dead"] = removed
        logger.info("Proxy health check done: %d checked, %d removed", total, removed)
        return details

    async def _update_health_score(self, tier: str, proxy: str, latency_ms: int | None):
        """根据延迟更新代理质量分"""
        if not self.redis:
            return
        key = f"{REDIS_PREFIX}{tier}"
        current = await self.redis.zscore(key, proxy)
        if current is None:
            return
        if latency_ms is not None:
            latency_penalty = min(latency_ms / MAX_LATENCY_MS, 1.0) * -2
            new_score = current + (latency_penalty * LATENCY_WEIGHT)
            await self.redis.zadd(key, {proxy: new_score})
            latency_key = f"{REDIS_PREFIX}{tier}:latency"
            await self.redis.hset(latency_key, proxy, latency_ms)
            await self.redis.expire(latency_key, 3600)

    async def health_check(self) -> dict[str, int]:
        """返回各 tier 可用代理数 + 质量概览"""
        counts: dict[str, int] = {}
        if self.redis:
            for tier in self.TIERS:
                key = f"{REDIS_PREFIX}{tier}"
                count = await self.redis.zcard(key)
                # 统计高质量代理（score > QUALITY_THRESHOLD / 2）
                high_quality = 0
                all_proxies = await self.redis.zrange(key, 0, -1, withscores=True)
                for _, score in all_proxies:
                    if score > QUALITY_THRESHOLD / 2:
                        high_quality += 1
                counts[tier] = count if count is not None else 0
                counts[f"{tier}_high_quality"] = high_quality
        else:
            counts = {t: len(ps) for t, ps in self._in_memory.items()}
            counts.update({f"{t}_high_quality": sum(1 for p in ps if p.get("quality_score", 0) > QUALITY_THRESHOLD / 2) for t, ps in self._in_memory.items()})
        return counts

    # ── 内部 ──

    async def _acquire(self, tier: str) -> str | None:
        """获取 tier 中最低失败率的代理（随机打平）"""
        proxy = None
        if self.redis:
            proxy = await self._acquire_from_redis(tier)
        else:
            proxy = self._acquire_from_memory(tier)
        return proxy

    async def _acquire_from_redis(self, tier: str) -> str | None:
        assert self.redis is not None  # guarded by caller
        key = f"{REDIS_PREFIX}{tier}"

        # 检查是否需要补充
        count = await self.redis.zcard(key)
        if count is not None and count < REFILL_MIN:
            await self._fetch_proxies(tier)

        # 取出所有代理（返回 (member, score) 列表）
        proxies = await self.redis.zrange(key, 0, -1, withscores=True)
        if not proxies:
            # 尝试补充一次
            await self._fetch_proxies(tier)
            proxies = await self.redis.zrange(key, 0, -1, withscores=True)
            if not proxies:
                return None

        # 找到最低分的一组，随机挑选
        min_score = min(p[1] for p in proxies)
        candidates = [p[0] for p in proxies if p[1] == min_score]
        return random.choice(candidates)

    def _acquire_from_memory(self, tier: str) -> str | None:
        proxies = self._in_memory.get(tier, [])
        if not proxies:
            return None
        # 按失败数排序
        proxies.sort(key=lambda p: p.get("failures", 0))
        min_failures = proxies[0].get("failures", 0)
        candidates = [p for p in proxies if p.get("failures", 0) == min_failures]
        return random.choice(candidates).get("url")

    async def _fetch_proxies(self, tier: str):
        """从配置 URL 拉取代理列表→写入 Redis"""
        url_map = {
            "premium":  sourcing_settings.proxy_premium_url,
            "standard": sourcing_settings.proxy_standard_url,
            "mobile":   sourcing_settings.proxy_mobile_url,
        }
        url = url_map.get(tier)
        if not url:
            logger.debug("No proxy source URL for %s", tier)
            return

        async with self._fetch_lock:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                logger.warning("Failed to fetch %s proxies from %s: %s", tier, url, e)
                return

        proxies = self._parse_proxy_response(data)
        if not proxies:
            logger.warning("Empty proxy list for %s from %s", tier, url)
            return

        if self.redis:
            key = f"{REDIS_PREFIX}{tier}"
            # 用 dict 批量 zadd（去掉已存在的）
            mapping = {p: 0 for p in proxies}
            await self.redis.zadd(key, mapping)  # pyright: ignore[reportGeneralTypeIssues]
            await self.redis.expire(key, FETCH_TTL)
            logger.info("Fetched %d proxies for %s", len(proxies), tier)

    @staticmethod
    def _parse_proxy_response(data: Any) -> list[str]:
        """解析不同格式的代理 API 响应

        支持格式:
        - ["http://ip:port", ...]
        - {"data": [{"ip": "...", "port": 8080}, ...]}
        - {"proxies": ["http://ip:port", ...]}
        """
        if isinstance(data, list):
            return [str(item) if isinstance(item, str) else f"http://{item['ip']}:{item['port']}"
                    for item in data]

        if isinstance(data, dict):
            # 常见代理 API 格式
            for key in ("data", "proxies", "results", "list"):
                items = data.get(key)
                if isinstance(items, list):
                    return [str(item) if isinstance(item, str)
                            else f"http://{item['ip']}:{item['port']}"
                            for item in items]
            # 键值对格式 {"proxy1": "http://...", ...}
            return [v for v in data.values() if isinstance(v, str) and v.startswith("http")]

        return []


# 模块级快捷函数
async def get_proxy_pool_health() -> dict[str, int]:
    from app.core.redis import get_redis
    redis = await get_redis()
    pool = ProxyPool(redis=redis)
    return await pool.health_check()
