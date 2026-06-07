"""v1.0b.1: SENTRY_TRACES_SAMPLE_RATE typo 修 + 兼容 shim 测试."""
from __future__ import annotations

import os
import warnings
from unittest.mock import patch

import pytest


def test_traces_sample_rate_reads_no_space_key():
    """无空格 SENTRY_TRACES_SAMPLE_RATE 正确读 (v1.0b.1 改后)."""
    from app.core.sentry_setup import _traces_sample_rate

    with patch.dict(os.environ, {"SENTRY_TRACES_SAMPLE_RATE": "0.3"}, clear=False):
        os.environ.pop("SENTRY TRACES_SAMPLE_RATE", None)
        assert _traces_sample_rate() == 0.3


def test_traces_sample_rate_legacy_with_space_still_works():
    """兼容 shim: 带空格 SENTRY TRACES_SAMPLE_RATE 仍可读, warn DeprecationWarning."""
    from app.core.sentry_setup import _traces_sample_rate

    with patch.dict(os.environ, {"SENTRY TRACES_SAMPLE_RATE": "0.2"}, clear=False):
        os.environ.pop("SENTRY_TRACES_SAMPLE_RATE", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = _traces_sample_rate()
        assert value == 0.2
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1
        assert "SENTRY TRACES_SAMPLE_RATE" in str(deprecation_warnings[0].message)


def test_traces_sample_rate_default_when_no_env():
    """无任一 env 时返默认 0.1."""
    from app.core.sentry_setup import _traces_sample_rate

    with patch.dict(os.environ, {}, clear=True):
        assert _traces_sample_rate() == 0.1


def test_traces_sample_rate_no_space_key_takes_precedence():
    """无空格 key 优先级 > 带空格 (避免双重配置)."""
    from app.core.sentry_setup import _traces_sample_rate

    with patch.dict(os.environ, {
        "SENTRY_TRACES_SAMPLE_RATE": "0.7",
        "SENTRY TRACES_SAMPLE_RATE": "0.2",
    }, clear=False):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = _traces_sample_rate()
        # 无空格胜出, 不走 fallback, 不 warn
        assert value == 0.7
        assert len([w for w in caught if issubclass(w.category, DeprecationWarning)]) == 0
