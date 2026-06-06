"""MCP 域 Prometheus 指标（v3 V-5 部分落地）。

注：用 prometheus_client 全局 registry，/metrics 端点自动暴露。
不需要在 main.py 改任何代码。

指标清单：
  - mcp_calls_total{target, server, status}              Counter
  - mcp_call_duration_seconds{target, server}            Histogram
  - mcp_server_up{server_id}                              Gauge  (1=up, 0=down)
  - mcp_server_restarts_total{server_id}                  Counter
  - mcp_server_startup_duration_seconds{server_id}        Histogram
  - mcp_large_results_total{server_id}                    Counter
  - mcp_validation_errors_total{server_id, target}       Counter
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── call_tool 调用统计 ─────────────────────────────────────────────
mcp_calls_total = Counter(
    "mcp_calls_total",
    "Total MCP tool calls (target=short tool name, server=server_id)",
    labelnames=("target", "server", "status"),  # status: success | validation_error | handler_error | timeout | server_down
)

mcp_call_duration_seconds = Histogram(
    "mcp_call_duration_seconds",
    "MCP tool call latency (seconds)",
    labelnames=("target", "server"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── server 状态 ────────────────────────────────────────────────────
mcp_server_up = Gauge(
    "mcp_server_up",
    "1 if MCP server subprocess is up and connected, 0 otherwise",
    labelnames=("server_id",),
)

mcp_server_restarts_total = Counter(
    "mcp_server_restarts_total",
    "Total number of times a server subprocess has been restarted",
    labelnames=("server_id", "reason"),  # reason: crash | health_check | manual
)

mcp_server_startup_duration_seconds = Histogram(
    "mcp_server_startup_duration_seconds",
    "Time from spawn to list_tools ready (seconds)",
    labelnames=("server_id",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── 大 result / 校验错误 ──────────────────────────────────────────
mcp_large_results_total = Counter(
    "mcp_large_results_total",
    "Results >1MB that were redirected to file ref (V-2 防护)",
    labelnames=("server_id",),
)

mcp_validation_errors_total = Counter(
    "mcp_validation_errors_total",
    "Pydantic input validation errors (V-3 防护)",
    labelnames=("server_id", "target"),
)


def record_call(
    target: str,
    server: str,
    status: str,
    duration: float,
) -> None:
    """一次 tool call 完成后调一次（host.call_tool 包装层）。"""
    mcp_calls_total.labels(target=target, server=server, status=status).inc()
    mcp_call_duration_seconds.labels(target=target, server=server).observe(duration)


def record_server_up(server_id: str, up: bool) -> None:
    mcp_server_up.labels(server_id=server_id).set(1 if up else 0)


def record_restart(server_id: str, reason: str = "crash") -> None:
    mcp_server_restarts_total.labels(server_id=server_id, reason=reason).inc()


def record_startup(server_id: str, duration: float) -> None:
    mcp_server_startup_duration_seconds.labels(server_id=server_id).observe(duration)


def record_large_result(server_id: str) -> None:
    mcp_large_results_total.labels(server_id=server_id).inc()


def record_validation_error(server_id: str, target: str) -> None:
    mcp_validation_errors_total.labels(server_id=server_id, target=target).inc()
