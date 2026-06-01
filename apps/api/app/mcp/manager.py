"""MCP Server 连接管理器。

管理所有已配置的 MCP server 连接状态、工具缓存、心跳。
提供 Agent 所需的统一工具列表和 handler 路由。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.mcp.bridge import mcp_content_to_text, mcp_tool_to_openai
from app.mcp.client import (
    _build_auth_header,
    mcp_call_tool,
    mcp_list_tools,
)

logger = logging.getLogger(__name__)


class MCPServerState:
    """单个 MCP Server 的运行时状态。"""

    def __init__(
        self,
        server_id: str,
        name: str,
        url: str,
        auth_header: str,
        tools_cache: list[dict] | None = None,
    ) -> None:
        self.server_id = server_id
        self.name = name
        self.url = url
        self.auth_header = auth_header
        self.tools_cache: list[dict] = tools_cache or []
        self.last_heartbeat: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "name": self.name,
            "url": self.url,
            "tools_count": len(self.tools_cache),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }


class MCPManager:
    """MCP Server 连接管理器（全局单例）。

    职责:
      1. 维护所有已注册 MCP server 的运行时状态
      2. 缓存 server 的工具列表
      3. 为 Agent 提供统一工具列表 + handler 路由
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerState] = {}

    # ── 注册/注销 ──────────────────────────────────────────────

    async def register(
        self,
        server_id: str,
        name: str,
        url: str,
        auth_type: str = "none",
        auth_token: str = "",
        tools_cache_data: list[dict] | None = None,
    ) -> None:
        """注册或更新一个 MCP server。"""
        auth_header = _build_auth_header(auth_type, auth_token)
        existing = self._servers.get(server_id)
        if existing:
            existing.name = name
            existing.url = url
            existing.auth_header = auth_header
            if tools_cache_data is not None:
                existing.tools_cache = tools_cache_data
        else:
            self._servers[server_id] = MCPServerState(
                server_id=server_id,
                name=name,
                url=url,
                auth_header=auth_header,
                tools_cache=tools_cache_data,
            )
        logger.info("MCP server registered: %s (%s)", name, url)

    async def unregister(self, server_id: str) -> None:
        """注销一个 MCP server。"""
        self._servers.pop(server_id, None)
        logger.info("MCP server unregistered: %s", server_id)

    # ── 工具发现 ────────────────────────────────────────────────

    async def discover_tools(self, server_id: str) -> list[dict]:
        """发现某个 server 的最新工具列表，更新缓存并返回。"""
        state = self._servers.get(server_id)
        if not state:
            logger.warning("discover_tools: unknown server %s", server_id)
            return []
        try:
            tools = await mcp_list_tools(state.url, state.auth_header)
            state.tools_cache = tools
            state.last_heartbeat = datetime.now(timezone.utc)
            logger.info("Discovered %d tools from %s", len(tools), state.name)
        except Exception as e:
            logger.warning("discover_tools failed for %s: %s", state.name, e)
            tools = state.tools_cache  # 失败时返回缓存
        return tools

    # ── 工具调用 ────────────────────────────────────────────────

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """调用指定 server 上的工具。返回文本结果。"""
        state = self._servers.get(server_id)
        if not state:
            return f"错误: MCP server {server_id} 未注册"
        try:
            content = await mcp_call_tool(
                state.url, tool_name, arguments, state.auth_header,
            )
            state.last_heartbeat = datetime.now(timezone.utc)
            return mcp_content_to_text(content)
        except Exception as e:
            logger.exception("call_tool failed: %s/%s", state.name, tool_name)
            return f"工具调用失败: {e}"

    # ── Agent 集成接口 ─────────────────────────────────────────

    def get_all_tools(self) -> list[dict]:
        """聚合所有已注册 server 的工具（已转换为 OpenAI 格式）。"""
        result: list[dict] = []
        for sid, state in self._servers.items():
            for tool in state.tools_cache:
                if tool is None:
                    continue
                try:
                    result.append(mcp_tool_to_openai(tool))
                except Exception as e:
                    logger.warning("tool conversion failed %s/%s: %s", state.name, tool.get("name"), e)
        return result

    def get_handler(self, tool_name: str) -> Callable | None:
        """根据工具名称找到所属 server 并返回调用包装器。

        返回的 callable 签名: async def handler(**kwargs) -> str
        """
        for sid, state in self._servers.items():
            for tool in state.tools_cache:
                if tool.get("name") == tool_name:
                    server_id = sid
                    async def handler(**kwargs: Any) -> str:
                        return await self.call_tool(server_id, tool_name, kwargs)
                    return handler
        return None

    def get_tool_owner(self, tool_name: str) -> MCPServerState | None:
        """根据工具名称找到所属的 server state。"""
        for sid, state in self._servers.items():
            for tool in state.tools_cache:
                if tool.get("name") == tool_name:
                    return state
        return None

    # ── 管理 ────────────────────────────────────────────────────

    async def refresh_all(self) -> int:
        """重新发现所有 server 的工具列表。返回成功数。"""
        count = 0
        for sid in list(self._servers.keys()):
            try:
                tools = await self.discover_tools(sid)
                if tools:
                    count += 1
            except Exception as e:
                logger.warning("refresh %s: %s", sid, e)
        return count

    def get_server_info(self, server_id: str) -> dict | None:
        state = self._servers.get(server_id)
        return state.to_dict() if state else None

    def list_servers(self) -> list[dict]:
        return [s.to_dict() for s in self._servers.values()]


# 全局单例
mcp_manager = MCPManager()
