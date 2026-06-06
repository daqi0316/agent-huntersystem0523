"""A/B 灰度测试指标（v4 PR-1b 灰度切流）。

独立于 mcp/metrics.py：标 ab_ 前缀方便过滤。
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# 路由决策：哪条 path 被选中
ab_decisions_total = Counter(
    "ab_decisions_total",
    "A/B routing decisions",
    labelnames=("tool", "path", "reason"),  # path: old | new | reason: hash_bucket | allowlist | fallback
)

# 调用结果
ab_calls_total = Counter(
    "ab_calls_total",
    "A/B tool calls",
    labelnames=("tool", "path", "status"),  # status: success | error | fallback_used
)

# 延迟
ab_call_duration_seconds = Histogram(
    "ab_call_duration_seconds",
    "A/B tool call latency",
    labelnames=("tool", "path"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# 实时配置
ab_current_percent = Gauge(
    "ab_current_percent",
    "Current A/B percent for new path (0-100)",
    labelnames=("tool",),
)

ab_new_path_up = Gauge(
    "ab_new_path_up",
    "1 if new path is up and callable",
    labelnames=("tool",),
)


def record_decision(tool: str, path: str, reason: str) -> None:
    ab_decisions_total.labels(tool=tool, path=path, reason=reason).inc()


def record_call(tool: str, path: str, status: str, duration: float) -> None:
    ab_calls_total.labels(tool=tool, path=path, status=status).inc()
    ab_call_duration_seconds.labels(tool=tool, path=path).observe(duration)


def set_percent(tool: str, percent: int) -> None:
    ab_current_percent.labels(tool=tool).set(percent)


def set_new_path_up(tool: str, up: bool) -> None:
    ab_new_path_up.labels(tool=tool).set(1 if up else 0)
