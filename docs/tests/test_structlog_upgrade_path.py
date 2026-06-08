"""F19.5: 装 structlog 后升级路径验 (mock 模拟).

venv 没 pip 装不上 structlog. 用 unittest.mock 模拟 structlog 在 sys.modules
中, 验 _STRUCTLOG_AVAILABLE=True 路径, get_logger 返 structlog logger.

覆盖:
- _STRUCTLOG_AVAILABLE = True 时 setup_logging 调 structlog.configure
- get_logger 返 structlog.get_logger(name) (不是 stdlib fallback)
- graceful degradation: 未装时 fallback 仍工作 (F19.1 已验, 本测不重)
"""
from __future__ import annotations

import importlib
import sys
import unittest.mock as mock
from pathlib import Path

# 让测试可 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "apps" / "api"))


def _reload_logging_with_mock_structlog():
    """模拟 structlog 装着, reload app.core.logging 让 _STRUCTLOG_AVAILABLE=True."""
    fake_structlog = mock.MagicMock()
    fake_structlog.get_logger.return_value = "MOCK_STRUCTLOG_LOGGER"
    sys.modules["structlog"] = fake_structlog

    if "app.core.logging" in sys.modules:
        del sys.modules["app.core.logging"]
    import app.core.logging as logging_mod  # noqa: F401

    return fake_structlog


def _reload_logging_without_structlog():
    """恢复无 structlog 状态, reload 让 _STRUCTLOG_AVAILABLE=False."""
    if "structlog" in sys.modules:
        del sys.modules["structlog"]
    if "app.core.logging" in sys.modules:
        del sys.modules["app.core.logging"]
    import app.core.logging as logging_mod  # noqa: F401

    return logging_mod


def test_upgrade_path_uses_structlog_when_available() -> None:
    """升级路径: 装上 structlog 后, get_logger 返 structlog logger (不是 stdlib)."""
    fake = _reload_logging_with_mock_structlog()
    from app.core.logging import get_logger

    result = get_logger("test_module")
    assert result == "MOCK_STRUCTLOG_LOGGER", (
        f"expected structlog logger, got {result!r}"
    )
    fake.get_logger.assert_called_with("test_module")

    # 恢复无 structlog 状态
    _reload_logging_without_structlog()


def test_upgrade_path_setup_logging_calls_structlog_configure() -> None:
    """升级路径: setup_logging 调 structlog.configure (不是 basicConfig)."""
    fake = _reload_logging_with_mock_structlog()
    from app.core.logging import setup_logging

    setup_logging(service="api-upgrade-test")
    fake.configure.assert_called_once()

    call_kwargs = fake.configure.call_args.kwargs
    assert "processors" in call_kwargs
    assert "wrapper_class" in call_kwargs
    assert "logger_factory" in call_kwargs
    processors = call_kwargs["processors"]
    assert any(
        "TimeStamper" in str(type(p).__name__) or "timestamp" in str(p).lower()
        for p in processors
    ), f"expected TimeStamper in processors, got {processors}"

    _reload_logging_without_structlog()


def test_upgrade_path_momus_standard_fields_in_processors() -> None:
    """升级路径: structlog processors 含 momus §3.3 标准字段 (TimeStamper/add_log_level/JSONRenderer)."""
    fake = _reload_logging_with_mock_structlog()
    from app.core.logging import setup_logging

    setup_logging(service="api-momus-test")
    processors = fake.configure.call_args.kwargs["processors"]
    processor_names = [str(type(p).__name__) for p in processors]
    expected = ["TimeStamper", "add_log_level", "dict_tracebacks", "JSONRenderer"]
    for exp in expected:
        found = any(
            exp in name or exp in str(p)
            for name, p in zip(processor_names, processors)
            if not callable(p) or exp in str(p)
        )
        assert found, f"missing momus standard field processor {exp!r}, got {processor_names}"

    _reload_logging_without_structlog()


if __name__ == "__main__":
    test_upgrade_path_uses_structlog_when_available()
    test_upgrade_path_setup_logging_calls_structlog_configure()
    test_upgrade_path_momus_standard_fields_in_processors()
    print("3 passed")
