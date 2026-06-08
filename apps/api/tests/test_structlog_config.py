"""F19: 验 structlog 集中日志配置 (momus §3.3 标准字段).

不依赖真 backend, 纯单元测:
- setup_logging 调不抛异常
- get_logger 返 BoundLogger
- logger.info 输出 JSON 含 ts/level/service/event
- 跨"服务" tag 可配置

如果 structlog 未装 (venv 没 pip), 测 skip 不阻断 CI.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

try:
    from app.core.logging import get_logger, setup_logging
    STRUCTLOG_AVAILABLE = True
except ModuleNotFoundError:
    STRUCTLOG_AVAILABLE = False


def test_structlog_available() -> None:
    """baseline: structlog 是否在 venv 装着."""
    if not STRUCTLOG_AVAILABLE:
        print("  ⚠️  structlog 未装, 4 测全 skip (pip install structlog 后再跑)")
        import pytest
        pytest.skip("structlog not installed")


def test_get_logger_returns_logger() -> None:
    if not STRUCTLOG_AVAILABLE:
        import pytest
        pytest.skip("structlog not installed")
    setup_logging(service="test")
    logger = get_logger("test_module")
    assert logger is not None
    assert hasattr(logger, "info")


def test_logger_outputs_json() -> None:
    if not STRUCTLOG_AVAILABLE:
        import pytest
        pytest.skip("structlog not installed")
    setup_logging(service="api")
    logger = get_logger("test")
    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.info("test_event", path="/test", status=200)
    data = json.loads(buf.getvalue().strip())
    assert data["event"] == "test_event"
    assert data["service"] == "api"
    assert "ts" in data
    assert "level" in data


def test_momus_standard_fields() -> None:
    if not STRUCTLOG_AVAILABLE:
        import pytest
        pytest.skip("structlog not installed")
    setup_logging(service="api")
    logger = get_logger("test")
    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.info("request_completed", path="/api/v1/auth/login", latency_ms=42, status=200, user_id="u-123", org_id="o-456")
    data = json.loads(buf.getvalue().strip())
    for field in ["ts", "level", "service", "event", "path", "latency_ms", "status", "user_id", "org_id"]:
        assert field in data, f"missing {field!r}"


if __name__ == "__main__":
    if not STRUCTLOG_AVAILABLE:
        print("⚠️  structlog 未装, 跳过 4 测 (pip install structlog>=24.1.0 后再跑)")
    else:
        test_get_logger_returns_logger()
        test_logger_outputs_json()
        test_momus_standard_fields()
        print("3 passed")
