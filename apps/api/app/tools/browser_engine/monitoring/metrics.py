"""
Prometheus 指标定义 — 引擎请求量 / 耗时 / 降级率
"""

from prometheus_client import Counter, Histogram, Gauge
import time

from ..manager.engine_manager import EngineManager


engine_requests_total = Counter(
    "engine_requests_total",
    "Total requests by engine and platform",
    ["engine", "platform", "status"],
)

engine_request_duration = Histogram(
    "engine_request_duration_seconds",
    "Request latency by engine and platform",
    ["engine", "platform"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

engine_fallback_total = Counter(
    "engine_fallback_total",
    "Fallback count by platform",
    ["platform", "from_engine", "to_engine"],
)

# 引擎当前状态
engine_status = Gauge(
    "engine_status",
    "Current engine status (1=available, 0=unavailable)",
    ["engine"],
)


async def monitored_fetch(
    engine_manager: EngineManager,
    url: str,
    platform_name: str,
    timeout: int = 30000,
):
    """带 Prometheus 指标采集的 fetch 包装"""
    preferred = engine_manager.get_preferred_engine(platform_name)
    start = time.monotonic()

    result = await engine_manager.fetch_with_fallback(
        url=url, platform_name=platform_name, timeout=timeout,
    )

    duration = time.monotonic() - start
    actual_engine = result.engine_used.value if result.engine_used else "none"

    engine_requests_total.labels(
        engine=actual_engine, platform=platform_name,
        status="success" if result.success else "failed",
    ).inc()
    engine_request_duration.labels(
        engine=actual_engine, platform=platform_name,
    ).observe(duration)

    if actual_engine != preferred.value:
        engine_fallback_total.labels(
            platform=platform_name,
            from_engine=preferred.value,
            to_engine=actual_engine,
        ).inc()

    return result


__all__ = [
    "engine_requests_total",
    "engine_request_duration",
    "engine_fallback_total",
    "engine_status",
    "monitored_fetch",
]
