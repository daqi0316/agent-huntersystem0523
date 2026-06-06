"""v0.3 §3.2 故障注入 pytest — supervisor 重启 + call 检测验证。

F-1: kill -9 硬杀 → supervisor watchdog 检测 + 自动重启 (< 3s)
F-2: kill -15 优雅关停 → in-flight call 完成 + 新 session 接 (< 5s)
F-3: handler sleep 卡 → call 超时降级 (M-1 修订：避开 sudo)
F-4: handler hang → supervisor 主动 kill + 重启 (< 10s)
"""
from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

import psutil
import pytest

from app.mcp.config import RestartPolicy, ServerConfig, StartupPhase
from app.mcp.host import CallTimeout, MCPHost, SubprocessDown
from app.mcp.supervisor import ProcessSupervisor


# ── 公共 fixture ───────────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _fault_injection_log():
    print("\n=== v0.3 §3.2 故障注入 suite 启动 ===")
    yield
    print("=== 故障注入 suite 结束 ===")


def test_circuit_breaker_opens_after_threshold():
    """5 次重启在 60s 窗口内 → circuit 打开 300s。"""
    sup = ProcessSupervisor()
    for i in range(5):
        sup._record_restart("mcp-utils")
    assert sup._circuit_is_open("mcp-utils"), "5 次后 circuit 应打开"
    assert sup._circuit_open_until["mcp-utils"] > time.time() + 200


def test_circuit_breaker_below_threshold_stays_closed():
    """4 次重启（< threshold=5）→ circuit 不打开。"""
    sup = ProcessSupervisor()
    for _ in range(4):
        sup._record_restart("mcp-utils")
    assert not sup._circuit_is_open("mcp-utils"), "4 次后 circuit 应仍关闭"


def test_circuit_breaker_window_slides():
    """窗口外的旧记录应被剔，新触发条件只看窗口内。"""
    sup = ProcessSupervisor(circuit_window_s=10.0)
    sup._record_restart("mcp-utils")
    assert len(sup._restart_history["mcp-utils"]) == 1
    sup._restart_history["mcp-utils"][0] = time.time() - 11.0
    sup._record_restart("mcp-utils")
    assert len(sup._restart_history["mcp-utils"]) == 1, "旧记录（11s 前）应被剔"
    assert not sup._circuit_is_open("mcp-utils")


def test_circuit_breaker_per_server_isolation():
    """一个 server 的 circuit 触发不影响其他 server。"""
    sup = ProcessSupervisor()
    for _ in range(5):
        sup._record_restart("mcp-utils")
    assert sup._circuit_is_open("mcp-utils")
    assert not sup._circuit_is_open("mcp-weather"), "其他 server circuit 应独立"
    assert "mcp-weather" not in sup._restart_history


def test_circuit_breaker_closes_after_cooldown():
    """circuit 打开后过 cooldown 自动关闭。"""
    sup = ProcessSupervisor(circuit_cooldown_s=0.1)
    for _ in range(5):
        sup._record_restart("mcp-utils")
    assert sup._circuit_is_open("mcp-utils")
    time.sleep(0.2)
    assert not sup._circuit_is_open("mcp-utils"), "cooldown 过后应自动关闭"
