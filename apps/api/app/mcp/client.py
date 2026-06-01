"""MCP JSON-RPC 2.0 协议客户端 — streamable-http 传输。

Model Context Protocol (MCP) 规范:
  - 传输: streamable-http (HTTP POST, JSON-RPC 2.0 request/response)
  - 握手: initialize → 获取 serverInfo + capabilities
  - 工具发现: tools/list → 获取可用工具列表
  - 工具调用: tools/call → 执行指定工具
"""

import base64
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0

MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "ai-recruitment", "version": "1.0.0"},
    },
}


def _build_auth_header(auth_type: str, auth_token: str) -> str:
    """构建 HTTP Authorization header。"""
    if not auth_token:
        return ""
    if auth_type == "bearer":
        return f"Bearer {auth_token}"
    if auth_type == "basic":
        encoded = base64.b64encode(auth_token.encode()).decode()
        return f"Basic {encoded}"
    return ""


def _headers(auth_header: str) -> dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if auth_header:
        h["Authorization"] = auth_header
    return h


async def _rpc_call(
    url: str,
    body: dict[str, Any],
    auth_header: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """执行一次 JSON-RPC 2.0 请求，返回 result 或抛出异常。"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=_headers(auth_header))
        resp.raise_for_status()
        data = resp.json()

    # JSON-RPC 错误响应
    if "error" in data and data["error"] is not None:
        err = data["error"]
        msg = err.get("message", "unknown MCP error")
        code = err.get("code", -1)
        raise RuntimeError(f"MCP error [{code}]: {msg}")

    return data.get("result", {})


async def mcp_initialize(
    url: str,
    auth_header: str = "",
) -> dict[str, Any]:
    """MCP 握手：获取 server 信息和 capabilities。"""
    logger.info("MCP initialize: %s", url)
    result = await _rpc_call(url, MCP_INITIALIZE, auth_header)

    # 通知 server 初始化完成（notifications/initialized）
    notified = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=notified, headers=_headers(auth_header))
    except Exception:
        pass  # 通知失败不影响后续调用

    return result


async def mcp_list_tools(
    url: str,
    auth_header: str = "",
) -> list[dict[str, Any]]:
    """获取 MCP server 暴露的工具列表。"""
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    result = await _rpc_call(url, body, auth_header)
    return result.get("tools", [])


async def mcp_call_tool(
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
    auth_header: str = "",
) -> list[dict[str, Any]]:
    """调用 MCP server 上的一个工具。返回 content 列表。"""
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    result = await _rpc_call(url, body, auth_header)
    return result.get("content", [])


async def test_connection(
    url: str,
    auth_type: str = "none",
    auth_token: str = "",
) -> dict[str, Any]:
    """测试 MCP server 连接：握手 + 工具列表。"""
    auth_header = _build_auth_header(auth_type, auth_token)
    try:
        init_result = await mcp_initialize(url, auth_header)
        server_info = init_result.get("serverInfo", {})
        server_name = server_info.get("name", "unknown")
        server_version = server_info.get("version", "")

        tools = await mcp_list_tools(url, auth_header)

        return {
            "success": True,
            "server_name": server_name,
            "server_version": server_version,
            "tools": tools,
            "error": "",
        }
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "server_name": "",
            "server_version": "",
            "tools": [],
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except httpx.RequestError as e:
        return {
            "success": False,
            "server_name": "",
            "server_version": "",
            "tools": [],
            "error": f"连接失败: {e}",
        }
    except (json.JSONDecodeError, RuntimeError) as e:
        return {
            "success": False,
            "server_name": "",
            "server_version": "",
            "tools": [],
            "error": f"协议错误: {e}",
        }
    except Exception as e:
        logger.exception("MCP test_connection failed: %s", url)
        return {
            "success": False,
            "server_name": "",
            "server_version": "",
            "tools": [],
            "error": f"未知错误: {e}",
        }
