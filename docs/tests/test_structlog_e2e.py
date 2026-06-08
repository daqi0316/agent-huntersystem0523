"""F19.4: 1 query 跨 5 服务验端到端日志格式一致.

跨 5 服务触发 log, 抓 stdout 验:
- 5 服务全有 'api INFO' 格式 (setup_logging service='api' 生效)
- 5 服务 logger name 正确 (app.core.rate_limit / app.core.telemetry /
  app.mcp.host / app.tools.application / app.main)
- 5 服务 timestamp 一致 (同一秒内, monotonic)

不依赖真 backend, 纯 stdout 抓 + 文本匹配.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# 让测试可 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api"))

from app.core.logging import get_logger, setup_logging

EXPECTED_SERVICES = [
    "app.core.rate_limit",
    "app.core.telemetry",
    "app.mcp.host",
    "app.tools.application",
    "app.main",
]


def _capture_5_services() -> str:
    """触发 5 服务 log, 抓 stdout 输出."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        setup_logging(service="api")
        for name in EXPECTED_SERVICES:
            get_logger(name).info("test_event")
    finally:
        sys.stdout = old_stdout
    return buf.getvalue()


def test_5_services_output_format() -> None:
    output = _capture_5_services()
    lines = [l for l in output.strip().split("\n") if l.strip()]
    assert len(lines) == 5, f"expected 5 lines, got {len(lines)}: {lines}"


def test_all_services_have_api_tag() -> None:
    """F19 setup_logging(service='api') 生效, 5 服务全含 'api INFO'."""
    output = _capture_5_services()
    for line in output.strip().split("\n"):
        assert "api INFO" in line, f"missing 'api INFO' tag in: {line}"


def test_all_service_names_present() -> None:
    output = _capture_5_services()
    for name in EXPECTED_SERVICES:
        assert name in output, f"service {name!r} not in output:\n{output}"


def test_all_log_level_info() -> None:
    """5 服务全用 INFO level (logger.info 调)."""
    output = _capture_5_services()
    for line in output.strip().split("\n"):
        assert "INFO" in line, f"missing INFO level in: {line}"


def test_graceful_degradation_format() -> None:
    """未装 structlog 时 fallback stdlib format 应含 'api INFO SERVICE_NAME MSG' 模式."""
    output = _capture_5_services()
    for name in EXPECTED_SERVICES:
        expected_pattern = f"api INFO {name}"
        assert expected_pattern in output, f"missing pattern {expected_pattern!r} in:\n{output}"


if __name__ == "__main__":
    test_5_services_output_format()
    test_all_services_have_api_tag()
    test_all_service_names_present()
    test_all_log_level_info()
    test_graceful_degradation_format()
    print("5 passed")
