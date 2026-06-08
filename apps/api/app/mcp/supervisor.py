"""ProcessSupervisor — 进程级 supervisor（v3 V-1 启动策略 + V-2 stderr 重定向）。

职责：
  1. spawn 一个 MCP server 子进程（asyncio.create_subprocess_exec）
  2. stderr 重定向到 logs/mcp_<id>.log（避免 pipe 死锁，V-2）
  3. 后台 task 看门狗：3s 心跳检测进程，挂了自动指数退避重启
  4. 优雅关闭：SIGTERM → 5s → SIGKILL
  5. 注册 on_restart 回调（host 重建 session）

设计：
  - 每个 server 一个 SupervisorHandle
  - supervisor 不持有 session（host 持有）；supervisor 只管进程
  - macOS 部分资源限制（RLIMIT_*）走 try/except 降级
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.mcp.metrics import record_restart, record_server_up, record_startup
from app.mcp.config import ServerConfig

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── 平台资源限制（macOS 部分支持）───────────────────────────────────
def _apply_resource_limits() -> None:
    """子进程资源限制。macOS RLIMIT_AS 行为不同，容错。"""
    try:
        import resource
        # CPU 时间：60s 软限、120s 硬限
        resource.setrlimit(resource.RLIMIT_CPU, (60, 120))
    except (ImportError, ValueError, OSError) as e:
        logger.debug("RLIMIT_CPU not available: %s", e)
    try:
        import resource
        # 内存：512MB
        mem = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    except (ImportError, ValueError, OSError) as e:
        logger.debug("RLIMIT_AS not available: %s", e)
    try:
        import resource
        # 禁 core dump
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError) as e:
        logger.debug("RLIMIT_CORE not available: %s", e)


# ── 进程句柄 ─────────────────────────────────────────────────────
@dataclass
class ServerProcess:
    """单个 server 进程句柄。"""

    server_id: str
    proc: asyncio.subprocess.Process
    config: ServerConfig
    started_at: float = field(default_factory=time.time)
    restart_count: int = 0
    last_exit_code: int | None = None


# ── Supervisor ─────────────────────────────────────────────────────
OnRestartCallback = Callable[[ServerProcess], Awaitable[None]]


class ProcessSupervisor:
    """管理 N 个 server 子进程 + 看门狗。"""

    def __init__(
        self,
        log_dir: str = "logs",
        shutdown_timeout: float = 5.0,
        circuit_threshold: int = 5,
        circuit_window_s: float = 60.0,
        circuit_cooldown_s: float = 300.0,
    ) -> None:
        self._procs: dict[str, ServerProcess] = {}
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._shutdown_timeout = shutdown_timeout
        self._shutdown = asyncio.Event()
        self._on_restart: OnRestartCallback | None = None
        self._circuit_threshold = circuit_threshold
        self._circuit_window_s = circuit_window_s
        self._circuit_cooldown_s = circuit_cooldown_s
        self._restart_history: dict[str, list[float]] = {}
        self._circuit_open_until: dict[str, float] = {}

    def set_on_restart(self, cb: OnRestartCallback) -> None:
        """host 启动后注册：server 重启时 host 重建 session。"""
        self._on_restart = cb

    def _record_restart(self, server_id: str) -> None:
        """记录一次重启，更新滑动窗口 + 触发条件判 circuit。"""
        now = time.time()
        history = self._restart_history.setdefault(server_id, [])
        cutoff = now - self._circuit_window_s
        history[:] = [t for t in history if t >= cutoff]
        history.append(now)
        if len(history) >= self._circuit_threshold:
            self._circuit_open_until[server_id] = now + self._circuit_cooldown_s
            logger.error(
                "Circuit breaker TRIPPED for %s: %d restarts in %.0fs, paused %.0fs",
                server_id, len(history), self._circuit_window_s, self._circuit_cooldown_s,
            )

    def _circuit_is_open(self, server_id: str) -> bool:
        """circuit 是否仍开着（未到 cooldown）。"""
        until = self._circuit_open_until.get(server_id, 0.0)
        return time.time() < until

    # ── 拉起 / 重启 ─────────────────────────────────────────────
    async def spawn(self, cfg: ServerConfig) -> ServerProcess:
        """拉起一个 server 子进程。"""
        env = self._build_env(cfg)
        # stderr → 日志文件（避免 pipe 死锁，V-2 修复）
        stderr_log = open(self._log_dir / f"mcp_{cfg.id}.log", "ab")
        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": stderr_log,
            "env": env,
            "limit": 8 * 1024 * 1024,  # 8MB stdout buffer（V-2 修复）
        }
        # macOS 上 setsid 会断 process group；Linux 不影响
        try:
            kwargs["start_new_session"] = True
        except (KeyError, ValueError):
            pass
        # 资源限制（macOS 部分支持）
        if sys.platform != "win32":
            kwargs["preexec_fn"] = _apply_resource_limits

        cwd = cfg.cwd or os.getcwd()
        start = time.time()
        proc = await asyncio.create_subprocess_exec(
            cfg.command, *cfg.args, cwd=cwd, **kwargs
        )
        elapsed = time.time() - start
        record_startup(cfg.id, elapsed)

        handle = ServerProcess(server_id=cfg.id, proc=proc, config=cfg)
        self._procs[cfg.id] = handle
        record_server_up(cfg.id, True)
        logger.info(
            "Spawned MCP server %s (pid=%d, cwd=%s, env_keys=%d, startup=%.2fs)",
            cfg.id, proc.pid, cwd, len(cfg.env_keys), elapsed,
        )

        # 启动看门狗
        asyncio.create_task(self._watchdog(handle))
        return handle

    async def _watchdog(self, handle: ServerProcess) -> None:
        """看门狗：进程退出 → 指数退避重启，circuit breaker 抑制雪崩。"""
        while not self._shutdown.is_set():
            try:
                rc = await handle.proc.wait()
                handle.last_exit_code = rc
                record_server_up(handle.server_id, False)
                logger.warning("MCP server %s exited rc=%d", handle.server_id, rc)
                if self._shutdown.is_set():
                    break
                if handle.config.restart == "never":
                    logger.info("Server %s restart=never, won't respawn", handle.server_id)
                    break
                if handle.restart_count >= handle.config.max_restarts:
                    logger.error(
                        "Server %s exceeded max_restarts=%d, giving up",
                        handle.server_id, handle.config.max_restarts,
                    )
                    break
                if self._circuit_is_open(handle.server_id):
                    until = self._circuit_open_until[handle.server_id]
                    wait_s = max(0.0, until - time.time())
                    logger.warning(
                        "Circuit breaker OPEN for %s, waiting %.0fs before retry",
                        handle.server_id, wait_s,
                    )
                    if wait_s > 0:
                        try:
                            await asyncio.wait_for(self._shutdown.wait(), timeout=wait_s)
                        except asyncio.TimeoutError:
                            pass
                    if self._shutdown.is_set():
                        break
                backoff = min(2 ** handle.restart_count, 30)
                handle.restart_count += 1
                self._record_restart(handle.server_id)
                logger.info(
                    "Restarting %s in %.1fs (attempt %d/%d)",
                    handle.server_id, backoff, handle.restart_count, handle.config.max_restarts,
                )
                await asyncio.sleep(backoff)
                record_restart(handle.server_id, reason="crash")
                new_handle = await self.spawn(handle.config)
                if self._on_restart is not None:
                    try:
                        await self._on_restart(new_handle)
                    except Exception as e:
                        logger.exception("on_restart callback failed: %s", e)
                # 把新 handle 替换旧的（proc 已被 supervisor 接管）
                self._procs[handle.server_id] = new_handle
                return  # 旧的 watchdog 结束，新 handle 有自己的 watchdog
            except Exception as e:
                logger.exception("Watchdog %s error: %s", handle.server_id, e)
                break

    # ── 优雅关闭 ────────────────────────────────────────────────
    async def shutdown(self) -> None:
        """关闭所有子进程：SIGTERM → 5s → SIGKILL。"""
        self._shutdown.set()
        for sid, handle in list(self._procs.items()):
            try:
                if handle.proc.returncode is None:
                    handle.proc.terminate()
                    try:
                        await asyncio.wait_for(handle.proc.wait(), timeout=self._shutdown_timeout)
                    except asyncio.TimeoutError:
                        logger.warning("Server %s didn't exit in %.1fs, killing", sid, self._shutdown_timeout)
                        handle.proc.kill()
                        await handle.proc.wait()
                record_server_up(sid, False)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.exception("Shutdown %s error: %s", sid, e)
        self._procs.clear()
        logger.info("ProcessSupervisor shutdown complete")

    # ── 查询 ────────────────────────────────────────────────────
    def get(self, server_id: str) -> ServerProcess | None:
        return self._procs.get(server_id)

    def all_servers(self) -> list[str]:
        return list(self._procs.keys())

    def is_up(self, server_id: str) -> bool:
        h = self._procs.get(server_id)
        return bool(h and h.proc.returncode is None)

    # ── 工具 ────────────────────────────────────────────────────
    def _build_env(self, cfg: ServerConfig) -> dict[str, str]:
        """构建子进程 env：OS env + 注入密钥 + 静态 env。

        密钥注入在 host 层做（resolve_env），supervisor 假设 cfg.extra_env 已经有值。
        """
        env = os.environ.copy()
        # 关键：subprocess 不缓冲 stdout（避免死锁）
        env["PYTHONUNBUFFERED"] = "1"
        env["MCP_SERVER_ID"] = cfg.id
        env["MCP_SERVER_VERSION"] = cfg.version
        env["MCP_SERVER_CAPABILITY"] = cfg.capability
        # 注入密钥
        for k, v in cfg.extra_env.items():
            env[k] = v
        return env
