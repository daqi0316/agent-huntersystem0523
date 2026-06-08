"""G15 T 测: MCPHost.create() factory + reset() 方法 (instance-level 重构).

背景: G15 mcp_host root cause (Momus v2 §G15) — module-level singleton
状态污染跨 event loop / 测试 / 长跑. Fix: 加 create() factory + reset()
方法, 允许 caller 显式拿独立实例或重置 state.

本 T 验 (conftest 的 _reset_mcp_host autouse fixture 已 import host +
重置 mcp_host state, 测试不需重 import):
1. MCPHost.create() 返独立实例 (state 隔离)
2. MCPHost.reset() 清 state (sessions/pids/configs/...)
3. 多个实例 reset 不互相影响
4. module-level mcp_host 仍可用 (向后兼容)
"""
from __future__ import annotations


def test_mcp_host_create_factory_independent():
    """G15 T 测 1: MCPHost.create() 返独立实例, state 隔离."""
    from app.mcp.host import MCPHost

    h1 = MCPHost.create()
    h2 = MCPHost.create()

    assert h1 is not h2, "应返不同实例 (factory 独立)"
    assert h1.registry is not h2.registry, "registry 应独立 (避免共享 state)"

    h1._started = True
    h1._sessions["test"] = "fake"
    h1._restart_counts["test"] = 5

    assert h2._started is False, "h1 改 _started 不应影响 h2"
    assert "test" not in h2._sessions, "h1 改 _sessions 不应影响 h2"
    assert h2._restart_counts == {}, "h1 改 _restart_counts 不应影响 h2"

    # 清理
    h1.reset()
    h2.reset()

    print("✅ G15 T 测 1: MCPHost.create() factory 独立实例 state 隔离")


def test_mcp_host_reset_clears_state():
    """G15 T 测 2: MCPHost.reset() 清所有 instance state."""
    from app.mcp.host import MCPHost

    h = MCPHost()
    h._started = True
    h._sessions["test"] = "fake"
    h._pids["test"] = 12345
    h._configs["test"] = "fake_config"
    h._restart_counts["test"] = 5
    h._exit_stack = "fake_stack"
    h._watch_tasks["test"] = "fake_task"
    h._start_lock = True
    h._shutdown = True

    h.reset()

    assert h._started is False
    assert h._sessions == {}
    assert h._pids == {}
    assert h._configs == {}
    assert h._restart_counts == {}
    assert h._exit_stack is None
    assert h._watch_tasks == {}
    assert h._start_lock is False
    assert h._shutdown is False

    print("✅ G15 T 测 2: MCPHost.reset() 清 9 个 state 字段")


def test_mcp_host_reset_does_not_affect_other_instances():
    """G15 T 测 3: 多实例 reset 不互相影响."""
    from app.mcp.host import MCPHost

    h1 = MCPHost.create()
    h2 = MCPHost.create()

    h1._started = True
    h1._sessions["x"] = "h1_data"
    h2._started = True
    h2._sessions["y"] = "h2_data"

    h1.reset()

    assert h1._started is False
    assert h1._sessions == {}
    assert h2._started is True, "h1.reset() 不应影响 h2._started"
    assert h2._sessions == {"y": "h2_data"}, "h1.reset() 不应影响 h2._sessions"

    h2.reset()

    print("✅ G15 T 测 3: h1.reset() 不影响 h2 独立 state")


def test_module_level_mcp_host_still_works():
    """G15 T 测 4: module-level mcp_host 仍可用 (向后兼容)."""
    from app.mcp import host

    assert hasattr(host, "mcp_host")
    assert isinstance(host.mcp_host, host.MCPHost)
    host.mcp_host.reset()
    assert host.mcp_host._started is False

    print("✅ G15 T 测 4: module-level mcp_host 向后兼容 (reset() 可调)")


if __name__ == "__main__":
    test_mcp_host_create_factory_independent()
    test_mcp_host_reset_clears_state()
    test_mcp_host_reset_does_not_affect_other_instances()
    test_module_level_mcp_host_still_works()
    print("\n=== 4/4 G15 T 测过 ===")
