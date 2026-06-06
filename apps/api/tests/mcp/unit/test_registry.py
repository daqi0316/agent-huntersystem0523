"""Unit tests for ToolRegistry (V-4 schema 演进) + metrics smoke。

跑法：.venv/bin/python -m pytest tests/mcp/unit/test_registry.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.mcp.registry import ToolEntry, ToolRegistry


class TestToolRegistry:
    def test_register_and_get(self):
        r = ToolRegistry()
        r.register("calc", "server-a", capability="read", version="1.0.0")
        e = r.get("calc")
        assert e is not None
        assert e.name == "calc"
        assert e.server_id == "server-a"
        assert e.capability == "read"
        assert e.version == "1.0.0"

    def test_register_conflict_different_server_raises(self):
        r = ToolRegistry()
        r.register("calc", "server-a")
        with pytest.raises(ValueError, match="conflict"):
            r.register("calc", "server-b")  # 跨 server 同名 → 拒绝

    def test_register_same_server_overwrites(self):
        r = ToolRegistry()
        r.register("calc", "server-a", version="1.0.0")
        r.register("calc", "server-a", version="1.1.0")  # 同 server → 覆盖
        e = r.get("calc")
        assert e.version == "1.1.0"

    def test_unregister_by_server(self):
        r = ToolRegistry()
        r.register("a", "s1")
        r.register("b", "s1")
        r.register("c", "s2")
        removed = r.unregister_by_server("s1")
        assert set(removed) == {"a", "b"}
        assert r.get("c") is not None

    def test_by_capability(self):
        r = ToolRegistry()
        r.register("get_x", "s1", capability="read")
        r.register("create_x", "s1", capability="write")
        r.register("delete_x", "s1", capability="destructive")
        r.register("install", "s1", capability="admin")
        assert {e.name for e in r.by_capability("read")} == {"get_x"}
        assert {e.name for e in r.by_capability("destructive")} == {"delete_x"}
        assert {e.name for e in r.by_capability("admin")} == {"install"}

    def test_deprecate(self):
        r = ToolRegistry()
        r.register("calc_v1", "s1")
        r.deprecate("calc_v1", replacement="calc_v2")
        e = r.get("calc_v1")
        assert e.deprecated is True
        assert e.replacement == "calc_v2"
        assert e.deprecated_since is not None
        assert r.is_deprecated("calc_v1") is True

    def test_deprecate_unknown_raises(self):
        r = ToolRegistry()
        with pytest.raises(KeyError, match="Unknown tool"):
            r.deprecate("nonexistent")

    def test_dump_snapshot(self, tmp_path):
        r = ToolRegistry()
        r.register("calc", "s1", capability="read", version="1.0.0")
        r.register("greet", "s1", capability="read")
        path = tmp_path / "snap.json"
        r.dump_snapshot(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["tool_count"] == 2
        assert data["server_count"] == 1
        assert {t["name"] for t in data["tools"]} == {"calc", "greet"}

    def test_get_all_schemas_mcp(self):
        r = ToolRegistry()
        r.register("calc", "s1", description="calc tool",
                   input_schema={"type": "object", "properties": {"x": {"type": "integer"}}})
        schemas = r.get_all_schemas("mcp")
        assert len(schemas) == 1
        s = schemas[0]
        assert s["name"] == "calc"
        assert s["description"] == "calc tool"
        assert s["inputSchema"]["type"] == "object"
        assert s["meta"]["capability"] == "read"

    def test_get_all_schemas_openai(self):
        r = ToolRegistry()
        r.register("calc", "s1", description="calc tool",
                   input_schema={"type": "object", "properties": {}})
        schemas = r.get_all_schemas("openai")
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "calc"
        assert schemas[0]["function"]["description"] == "calc tool"

    def test_tool_count_and_server_count(self):
        r = ToolRegistry()
        r.register("a", "s1")
        r.register("b", "s1")
        r.register("c", "s2")
        assert r.tool_count() == 3
        assert r.server_count() == 2


class TestMetricsSmoke:
    """Metrics 模块只 import + 创建 gauge，验证 prometheus 集成可用。"""

    def test_metrics_import_and_record(self):
        from app.mcp.metrics import (
            mcp_calls_total,
            mcp_server_up,
            record_call,
            record_server_up,
        )
        record_server_up("test-server", True)
        record_call("test-tool", "test-server", "success", 0.05)
        # 指标 increment 不抛异常
        assert mcp_server_up.labels(server_id="test-server")._value.get() == 1
        # mcp_calls_total 是 Counter，没法直接读 value，验证 inc 没抛
