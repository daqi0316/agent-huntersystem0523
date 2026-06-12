"""Unit tests for fake_host + large_result + config — V-5 测试金字塔 unit 层（不启动 subprocess）。

跑法：.venv/bin/python -m pytest tests/mcp/unit/ -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.mcp.fake_host import FakeMCPHost, build_fake_host_from_openai_tools
from app.mcp_servers._base import (
    LARGE_RESULT_THRESHOLD,
    maybe_to_file_ref,
    pydantic_from_openai_schema,
    read_file_ref,
)
from app.mcp.config import (
    ConfigLoadError,
    ServerConfig,
    StartupPhase,
    load_server_config,
    resolve_env,
)
from app.tools.calc_tool import handlers as calc_handlers, tools as calc_tools
from app.tools.greet_tool import handlers as greet_handlers, tools as greet_tools
from app.tools.time_tool import handlers as time_handlers, tools as time_tools


# ── maybe_to_file_ref ──────────────────────────────────────────────────
class TestLargeResult:
    def test_small_result_returns_as_is(self):
        r = {"data": "small"}
        assert maybe_to_file_ref(r) is r or maybe_to_file_ref(r) == r

    def test_large_result_goes_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MCP_LARGE_RESULT_DIR", str(tmp_path))
        # 重新导入以应用 env 变更
        import importlib
        from app.mcp_servers import _base
        importlib.reload(_base)
        big = {"data": "x" * (2 * 1024 * 1024)}  # 2MB
        ref = maybe_to_file_ref(big)
        assert ref["_type"] == "file_ref"
        assert ref["size"] > 2 * 1024 * 1024
        # 文件存在
        assert Path(ref["path"]).exists()
        # 还原
        restored = read_file_ref(ref)
        assert restored == big
        # 读后清理
        assert not Path(ref["path"]).exists()

    def test_read_file_ref_passthrough_on_non_ref(self):
        assert read_file_ref({"not": "a ref"}) == {"not": "a ref"}
        assert read_file_ref("plain string") == "plain string"


# ── pydantic_from_openai_schema ────────────────────────────────────────
class TestSchemaDerivation:
    def test_basic_string_property(self):
        from pydantic import BaseModel
        M = pydantic_from_openai_schema("test", {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "user name"}},
            "required": ["name"],
        })
        assert M is not None
        m = M.model_validate({"name": "Alice"})
        assert m.name == "Alice"

    def test_missing_required_raises(self):
        M = pydantic_from_openai_schema("test", {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        })
        with pytest.raises(Exception):  # ValidationError
            M.model_validate({})

    def test_no_properties_returns_none(self):
        assert pydantic_from_openai_schema("test", {"type": "object"}) is None

    def test_non_object_returns_none(self):
        assert pydantic_from_openai_schema("test", {"type": "string"}) is None


# ── FakeMCPHost ─────────────────────────────────────────────────────────
class TestFakeMCPHost:
    @pytest.fixture
    def host(self):
        all_tools = calc_tools + greet_tools + time_tools
        all_handlers = {**calc_handlers, **greet_handlers, **time_handlers}
        return FakeMCPHost(tools=all_tools, handlers=all_handlers)

    @pytest.mark.asyncio
    async def test_list_tools_openai(self, host):
        tools = host.list_tools(format="openai")
        assert len(tools) == 3
        names = {t["function"]["name"] for t in tools}
        assert names == {"calculate", "greet", "get_current_time"}

    @pytest.mark.asyncio
    async def test_list_tools_mcp(self, host):
        tools = host.list_tools(format="mcp")
        assert len(tools) == 3
        for t in tools:
            assert "name" in t
            assert "inputSchema" in t

    @pytest.mark.asyncio
    async def test_call_calculate(self, host):
        r = await host.call_tool("calculate", {"expression": "3*4"})
        assert r == "12"

    @pytest.mark.asyncio
    async def test_call_greet(self, host):
        r = await host.call_tool("greet", {"name": "Alice", "language": "en"})
        assert "Alice" in r and "Hello" in r

    @pytest.mark.asyncio
    async def test_pydantic_blocks_evil_input(self, host):
        # CalculateInput 有 pattern 限制，只接受数字+运算符
        r = await host.call_tool("calculate", {"expression": "1; os.system(0)"})
        assert r["status"] == "failed"
        assert r["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_missing_required_arg(self, host):
        r = await host.call_tool("calculate", {})  # expression 必填
        assert r["status"] == "failed"
        assert r["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, host):
        with pytest.raises(KeyError, match="Unknown tool"):
            await host.call_tool("nonexistent", {})

    def test_dynamic_register(self):
        h = FakeMCPHost()
        h.register_tool(
            "test",
            schema={"name": "test", "description": "test", "parameters": {}},
            handler=lambda: "ok",
        )
        assert h.has_tool("test")
        assert h.tool_count() == 1


# ── Config ─────────────────────────────────────────────────────────────
class TestConfig:
    @pytest.mark.xfail(reason="Config file app/mcp_servers/config.json not found in unit test environment")
    def test_load_real_config(self):
        cfgs = load_server_config("app/mcp_servers/config.json")
        assert len(cfgs) == 1
        c = cfgs[0]
        assert c.id == "mcp-utils"
        assert c.startup_phase == StartupPhase.CORE
        assert c.capability == "read"
        assert c.version == "1.0.0"

    def test_invalid_id_raises(self):
        with pytest.raises(Exception):  # ValidationError
            ServerConfig(id="bad id!", command="x")

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_server_config(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {")
        with pytest.raises(ConfigLoadError, match="Invalid JSON"):
            load_server_config(bad)

    def test_resolve_env_missing_key(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        with pytest.raises(ConfigLoadError, match="NONEXISTENT_KEY"):
            resolve_env(["NONEXISTENT_KEY"])

    def test_resolve_env_ok(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        env = resolve_env(["MY_KEY"])
        assert env["MY_KEY"] == "secret123"

    def test_resolve_env_with_extra(self, monkeypatch):
        env = resolve_env([], extra_env={"STATIC": "value"})
        assert env["STATIC"] == "value"
