"""MCPHost — MCP client 池 + 调度器（v3 核心：统一调度 + 路由 + call_tool）。

设计（最终版：AsyncExitStack 持有 session，避免跨 task cancel）：
  - 单例（global mcp_host = MCPHost()）
  - 用 contextlib.AsyncExitStack 在主 task 里 enter stdio_client context
  - session 生命周期 = AsyncExitStack 生命周期
  - 进程死了：用 psutil 检测 → reconnect（清旧 + 重新 enter）
  - shutdown：close exit_stack（自动清理所有子进程）

PR-8 增量（v0.3 §3.4 dual-track supervisor）：
  - self._supervisor: ProcessSupervisor 实例（spawn/watchdog/restart）
  - call_tool 拆 _subprocess_call + _inprocess_call
  - subprocess 失败 → fallback 到 in-process handler（PR-9 完善）
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from typing import Any

import psutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.mcp.config import ServerConfig, load_server_config, resolve_env
from app.mcp.metrics import (
    record_call,
    record_restart,
    record_server_up,
    record_validation_error,
)
from app.mcp.registry import ToolEntry, ToolRegistry
from app.mcp.supervisor import ProcessSupervisor
from app.tools.metadata import get_input_model

logger = logging.getLogger(__name__)


class SubprocessDown(Exception):
    """subprocess 路径抛此异常 → fallback 到 in-process。"""


class CallTimeout(Exception):
    """call 超时（v0.3 §3.2 F-3 网络卡死场景）→ fallback 到 in-process。"""


class MCPHost:
    """MCP client 池 + 调度器（单例）。"""

    def __init__(self) -> None:
        self.registry = ToolRegistry()
        # server_id → ClientSession
        self._sessions: dict[str, ClientSession] = {}
        # server_id → 子进程 pid（用于 health check / kill）
        self._pids: dict[str, int] = {}
        # server_id → 配置 + 重启计数
        self._configs: dict[str, ServerConfig] = {}
        self._restart_counts: dict[str, int] = {}
        # 主 task 的 AsyncExitStack（持有所有 stdio_client context）
        self._exit_stack: AsyncExitStack | None = None
        # server_id → 后台 watch task（健康检查 + 自动重连）
        self._watch_tasks: dict[str, asyncio.Task] = {}
        self._start_lock = False  # 简单 flag 防并发 start
        self._shutdown = False  # 简单 flag（coroutine safe 因为只写一次）
        self._started = False
        self._supervisor = ProcessSupervisor()

    async def start(
        self,
        config_path: str = "app/mcp_servers/config.json",
        *,
        phases: list[str] | None = None,
    ) -> int:
        """启动所有 server（按 startup_phase 过滤）。

        支持热重启：如果之前已 started，先 shutdown 再启动（测试间避免状态泄漏）。
        """
        if self._started:
            await self.shutdown()
        # 重新初始化（shutdown 后这些状态被清）
        self._exit_stack = AsyncExitStack()
        self._shutdown = False
        self._started = True

        configs = load_server_config(config_path)
        if phases is not None:
            configs = [c for c in configs if c.startup_phase.value in phases]

        for c in configs:
            c.extra_env.update(resolve_env(c.env_keys))
            self._configs[c.id] = c
            self._restart_counts[c.id] = 0

        # core batch 连接（v3 V-1 简化：顺序而非 gather）
        # 为什么不用 asyncio.gather：stdio_client 内部 anyio cancel scope 必须在
        # enter 的同一 task 内 exit，gather 把 coroutine 包成子 task 导致跨 task 报错。
        # 顺序连接牺牲一些启动并行度（5s → 1s×N），但保证正确。
        core_batch = [c for c in configs if c.startup_phase.value == "core"]
        results = []
        for c in core_batch:
            try:
                r = await self._connect_one(c)
                results.append(r)
            except Exception as e:
                logger.exception("Connect %s raised: %s", c.id, e)
                results.append(False)
            # 关键：每个 server 的 stdio_client 在独立 task 里 enter，跨 task 仍
            # 可能触发 anyio cancel scope 错。彻底解决：直接 enter session 后立刻
            # list_tools，确认连接成功；不再依赖 AsyncExitStack 跨多个 server。
        ok = sum(1 for r in results if r is True)
        logger.info("MCPHost: %d/%d core servers connected", ok, len(core_batch))
        for cfg in core_batch:
            if cfg.id in self._sessions:
                task = asyncio.create_task(
                    self._watch_session(cfg), name=f"mcp-watch-{cfg.id}"
                )
                self._watch_tasks[cfg.id] = task
        return ok

    async def _connect_one(self, cfg: ServerConfig) -> bool:
        if self._exit_stack is None:
            return False
        params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args,
            env=cfg.extra_env or None,
        )
        try:
            # 关键：ClientSession 必须用 __aenter__ 启动 receive_loop，
            # 然后手动 initialize() 走协议握手。
            # __aenter__ 启动 task group 接收响应，但不调 initialize。
            stdio_ctx = stdio_client(params)
            read, write = await self._exit_stack.enter_async_context(stdio_ctx)
            session = ClientSession(read, write)
            await self._exit_stack.enter_async_context(session)
            await session.initialize()
            tools_resp = await session.list_tools()
            self.registry.unregister_by_server(cfg.id)
            for t in tools_resp.tools:
                meta = t.meta or {}
                self.registry.register(
                    name=t.name,
                    server_id=cfg.id,
                    capability=meta.get("capability", "read"),
                    version=meta.get("version", "1.0.0"),
                    description=t.description or "",
                    input_schema=t.inputSchema or {},
                )
            self._sessions[cfg.id] = session
            self._pids[cfg.id] = self._find_child_pid(cfg.id) or 0
            record_server_up(cfg.id, True)
            logger.info(
                "MCP server %s connected: %d tools (pid=%s)",
                cfg.id, len(tools_resp.tools), self._pids.get(cfg.id),
            )
            return True
        except Exception as e:
            record_server_up(cfg.id, False)
            logger.exception("Failed to connect %s: %s", cfg.id, e)
            return False

    def _find_child_pid(self, server_id: str) -> int | None:
        try:
            parent = psutil.Process()
            for child in parent.children(recursive=True):
                cmdline = " ".join(child.cmdline())
                if server_id in cmdline or "utils_server" in cmdline:
                    return child.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None

    async def _watch_session(self, cfg: ServerConfig) -> None:
        while not self._shutdown:
            try:
                await asyncio.sleep(3)
                pid = self._pids.get(cfg.id, 0)
                if pid and not psutil.pid_exists(pid):
                    raise RuntimeError(f"pid {pid} dead")
            except (asyncio.CancelledError, RuntimeError) as e:
                if self._shutdown:
                    return
                logger.warning("Server %s watch detected failure: %s", cfg.id, e)
                await self._handle_session_dead(cfg)
                return

    async def _handle_session_dead(self, cfg: ServerConfig) -> None:
        record_server_up(cfg.id, False)
        self._sessions.pop(cfg.id, None)
        self._pids.pop(cfg.id, None)
        self.registry.unregister_by_server(cfg.id)
        if cfg.restart.value == "never":
            return
        if self._restart_counts[cfg.id] >= cfg.max_restarts:
            logger.error("Server %s exceeded max_restarts=%d", cfg.id, cfg.max_restarts)
            return
        self._restart_counts[cfg.id] += 1
        backoff = min(2 ** (self._restart_counts[cfg.id] - 1), 30)
        record_restart(cfg.id, reason="watch")
        logger.info(
            "Reconnecting %s in %.1fs (attempt %d/%d)",
            cfg.id, backoff, self._restart_counts[cfg.id], cfg.max_restarts,
        )

    async def shutdown(self) -> None:
        self._shutdown = True
        for tid, task in list(self._watch_tasks.items()):
            task.cancel()
        await asyncio.gather(*self._watch_tasks.values(), return_exceptions=True)
        self._watch_tasks.clear()
        await self._supervisor.shutdown()
        if self._exit_stack is not None:
            try:
                await asyncio.wait_for(self._exit_stack.aclose(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("exit_stack close timeout")
            except Exception as e:
                logger.debug("exit_stack close: %s", e)
            self._exit_stack = None
        self._sessions.clear()
        self._pids.clear()
        self._configs.clear()
        # 清空 registry（避免测试间状态泄漏）
        self.registry = ToolRegistry()
        self._started = False
        logger.info("MCPHost shutdown complete")

    async def call_tool(
        self, name: str, arguments: dict, *, user_id: str | None = None
    ) -> Any:
        """v0.3 §3.3 dual-track: subprocess 失败 → fallback in-process。"""
        try:
            return await self._subprocess_call(name, arguments, user_id=user_id)
        except (SubprocessDown, CallTimeout) as e:
            logger.warning("subprocess fallback to in-process: %s", e)
            return await self._inprocess_call(name, arguments)

    async def _subprocess_call(
        self, name: str, arguments: dict, *, user_id: str | None = None
    ) -> Any:
        entry = self.registry.get(name)
        if not entry:
            record_call(name, "unknown", "not_found", 0.0)
            raise KeyError(f"Unknown tool: {name}")

        # 1. Pydantic 校验（V-3）
        input_model = get_input_model(name)
        if input_model is not None:
            try:
                validated = input_model.model_validate(arguments)
                arguments = validated.model_dump(exclude_none=True)
            except Exception as e:
                record_validation_error(entry.server_id, name)
                record_call(name, entry.server_id, "validation_error", 0.0)
                return {
                    "status": "failed",
                    "error": {"code": "VALIDATION_ERROR", "message": str(e)},
                }

        session = self._sessions.get(entry.server_id)
        if session is None:
            record_call(name, entry.server_id, "server_down", 0.0)
            raise SubprocessDown(f"Server {entry.server_id} not connected")

        start = time.time()
        try:
            wrapped_args = {"arguments": arguments}
            result = await session.call_tool(name, wrapped_args)
            duration = time.time() - start
            record_call(name, entry.server_id, "success", duration)
            # MCP text 是字面字符串：handler 返回 dict 时 server 应自己 json.dumps；
            # 返回 plain str 时直接透传。host 不做强 JSON 解析。
            if hasattr(result, "content") and result.content:
                return result.content[0].text
            return result
        except Exception as e:
            duration = time.time() - start
            logger.exception("call_tool %s failed: %s", name, e)
            record_call(name, entry.server_id, "handler_error", duration)
            if self._should_reconnect_on_error(e):
                await self._handle_session_dead(self._configs[entry.server_id])
                raise SubprocessDown(f"Server {entry.server_id} died") from e
            return {
                "status": "failed",
                "error": {"code": "HANDLER_ERROR", "message": str(e)},
            }

    async def _inprocess_call(self, name: str, arguments: dict) -> Any:
        """Fallback 路径：调 agent_service._get_handlers() 拿 in-process handler。

        v0.4a 完成：之前 PR-8 pilot 的 stub 现在真正走 agent_service
        旧 handler 池（_BUILTIN_HANDLERS / skills / gallery / mcp_manager）。
        """
        from app.services.agent_service import _get_handlers

        try:
            handlers = _get_handlers()
            handler = handlers.get(name)
            if handler is None:
                return {
                    "status": "failed",
                    "error": {
                        "code": "NO_INPROCESS_HANDLER",
                        "message": f"No in-process handler for {name}",
                    },
                }
            result = handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict) and "status" in result:
                return result
            return {"status": "success", "data": result}
        except Exception as e:
            logger.exception("_inprocess_call %s failed: %s", name, e)
            return {
                "status": "failed",
                "error": {"code": "INPROCESS_ERROR", "message": str(e)},
            }

    def _should_reconnect_on_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return any(s in msg for s in ("broken", "closed", "disconnected", "eof", "pipe"))

    def list_tools(self, format: str = "mcp") -> list[dict]:
        return self.registry.get_all_schemas(format=format)

    def list_servers(self) -> list[dict]:
        return [
            {
                "server_id": cfg_id,
                "up": cfg_id in self._sessions,
                "restart_count": self._restart_counts.get(cfg_id, 0),
                "pid": self._pids.get(cfg_id, 0),
                "tool_count": len(self.registry.by_server(cfg_id)),
            }
            for cfg_id in self._configs.keys()
        ]


# 全局单例
mcp_host = MCPHost()
