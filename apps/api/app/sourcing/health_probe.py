"""P3-3: 平台健康探测定时任务 + P3-1 代理健康探测"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sourcing.models.platform_config import PlatformConfig
from app.sourcing.platforms.base import get_adapter, list_adapters

logger = logging.getLogger(__name__)


async def probe_platform_health(db: AsyncSession) -> dict[str, dict]:
    probes = list_adapters()
    results: dict[str, dict] = {}

    for info in probes:
        platform = info["name"]
        try:
            adapter_cls = get_adapter(platform)
            check_url = getattr(adapter_cls, "health_check_url", None)
            if not check_url:
                continue
            import httpx
            start = datetime.now(timezone.utc)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(check_url)
            latency = (datetime.now(timezone.utc) - start).total_seconds()
            is_alive = resp.status_code < 500

            new_status = "healthy" if is_alive else "degraded"
            result = await db.execute(
                select(PlatformConfig).where(PlatformConfig.name == platform)
            )
            config = result.scalar_one_or_none()
            if config:
                config.health_status = new_status
                config.health_checked_at = datetime.now(timezone.utc)

            results[platform] = {
                "status": new_status,
                "http_status": resp.status_code,
                "latency_s": round(latency, 2),
            }
            logger.info("Health probe %s: %s (%.2fs, HTTP %d)", platform, new_status, latency, resp.status_code)
        except Exception as e:
            results[platform] = {"status": "down", "error": str(e)}
            result = await db.execute(
                select(PlatformConfig).where(PlatformConfig.name == platform)
            )
            config = result.scalar_one_or_none()
            if config:
                config.health_status = "down"
                config.health_checked_at = datetime.now(timezone.utc)
            logger.warning("Health probe %s failed: %s", platform, e)

    await db.commit()
    return results
