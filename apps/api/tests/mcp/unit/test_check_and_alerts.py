"""Unit tests for MCP CI 守门 + 告警（PR-4d）。

跑法：.venv/bin/python -m pytest tests/mcp/unit/test_check_and_alerts.py -v
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # apps/api
_REPO_ROOT = Path(__file__).resolve().parents[5]  # 仓库根（apps/api → apps → 仓库根）
_API_ROOT = _PROJECT_ROOT
_CI_SCRIPT = _REPO_ROOT / "scripts" / "check_mcp_servers.py"


# ── CI 守门脚本 ─────────────────────────────────────────────
class TestCheckMcpServersScript:
    def test_script_exists(self):
        assert _CI_SCRIPT.exists(), f"CI script missing: {_CI_SCRIPT}"

    def test_script_runs_in_venv(self):
        """CI 脚本在 venv python 下能跑（quick 模式）。"""
        venv_python = _API_ROOT / ".venv" / "bin" / "python"
        if not venv_python.exists():
            pytest.skip(".venv/bin/python not found")
        result = subprocess.run(
            [str(venv_python), str(_CI_SCRIPT), "--quick"],
            cwd=_API_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # 可能 0（pass）也可能 1（预存 fail）— 但不能 127（找不到）也不能 2（usage）
        assert result.returncode in (0, 1), f"unexpected rc={result.returncode}: {result.stderr[:500]}"
        # 输出含 MCP Server CI Check 头
        assert "MCP Server CI Check" in result.stdout

    def test_script_exits_nonzero_on_failure(self):
        """脚本应能用 --help。"""
        venv_python = _API_ROOT / ".venv" / "bin" / "python"
        if not venv_python.exists():
            pytest.skip(".venv/bin/python not found")
        result = subprocess.run(
            [str(venv_python), str(_CI_SCRIPT), "--help"],
            cwd=_API_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "MCP server CI" in result.stdout


# ── Restart 监控 ─────────────────────────────────────────────
class TestRestartTracker:
    def test_record_restart_increments(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import RestartTracker
        # 重置 alert 阈值（避免测试时真告警）
        old = alerts_mod.ALERT_RESTART_THRESHOLD
        alerts_mod.ALERT_RESTART_THRESHOLD = 100
        try:
            t = RestartTracker()
            t.record_restart("server-a")
            t.record_restart("server-a")
            assert t.count_in_window("server-a") == 2
        finally:
            alerts_mod.ALERT_RESTART_THRESHOLD = old

    def test_threshold_alert_fires(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import RestartTracker

        # 收集 _send_sentry 调用
        sent = []
        alerts_mod._send_sentry = lambda level, msg, **kw: sent.append((level, msg, kw))
        old_thr = alerts_mod.ALERT_RESTART_THRESHOLD
        alerts_mod.ALERT_RESTART_THRESHOLD = 3
        try:
            t = RestartTracker()
            for _ in range(3):
                t.record_restart("server-x")
            assert any("restarted 3" in m for _, m, _ in sent), f"no restart alert sent: {sent}"
        finally:
            alerts_mod.ALERT_RESTART_THRESHOLD = old_thr
            alerts_mod._send_sentry = lambda *a, **kw: None  # reset

    def test_reset_clears(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import RestartTracker
        old = alerts_mod.ALERT_RESTART_THRESHOLD
        alerts_mod.ALERT_RESTART_THRESHOLD = 100
        try:
            t = RestartTracker()
            t.record_restart("server-y")
            assert t.count_in_window("server-y") == 1
            t.reset("server-y")
            assert t.count_in_window("server-y") == 0
        finally:
            alerts_mod.ALERT_RESTART_THRESHOLD = old


# ── ErrorRate 监控 ───────────────────────────────────────────
class TestErrorRateTracker:
    def test_low_error_rate_no_alert(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import ErrorRateTracker
        alerts_mod._send_sentry = lambda *a, **kw: None  # mute
        old = alerts_mod.ALERT_ERROR_RATE_THRESHOLD
        alerts_mod.ALERT_ERROR_RATE_THRESHOLD = 0.05
        try:
            t = ErrorRateTracker()
            for _ in range(20):
                t.record_call("calc", True)  # 全成功
            assert t.error_rate("calc") == 0.0
        finally:
            alerts_mod.ALERT_ERROR_RATE_THRESHOLD = old

    def test_high_error_rate_alerts(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import ErrorRateTracker

        sent = []
        alerts_mod._send_sentry = lambda level, msg, **kw: sent.append((level, msg, kw))
        old_thr = alerts_mod.ALERT_ERROR_RATE_THRESHOLD
        alerts_mod.ALERT_ERROR_RATE_THRESHOLD = 0.05
        try:
            t = ErrorRateTracker()
            # 10 调用 1 错误（10%）超过 5%
            for _ in range(9):
                t.record_call("flaky", True)
            t.record_call("flaky", False)
            assert any("error rate" in m for _, m, _ in sent), f"no error alert: {sent}"
        finally:
            alerts_mod.ALERT_ERROR_RATE_THRESHOLD = old_thr
            alerts_mod._send_sentry = lambda *a, **kw: None


# ── 关键告警函数 ─────────────────────────────────────────────
class TestAlertFunctions:
    def test_alert_restart_threshold_doesnt_raise(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import alert_restart_threshold
        alerts_mod._send_sentry = lambda *a, **kw: None
        alert_restart_threshold("test", 100)  # should not raise

    def test_alert_error_rate_doesnt_raise(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import alert_error_rate
        alerts_mod._send_sentry = lambda *a, **kw: None
        alert_error_rate("test", 0.1, 5, 50)

    def test_alert_destructive_failure_doesnt_raise(self):
        from app.core import mcp_alerts as alerts_mod
        from app.core.mcp_alerts import alert_destructive_failure
        alerts_mod._send_sentry = lambda *a, **kw: None
        alert_destructive_failure("delete_x", "DB connection lost")
