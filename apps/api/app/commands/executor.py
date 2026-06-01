"""CommandExecutor — 命令执行主流程 (4 层 dispatcher 架构).

执行顺序 (plan §M6 + V.1 退出标准):
    1. // 透传检测
    2. parse
    3. registry.get (未注册 → NOT_FOUND)
    4. check_permission (无权限 → PERMISSION_DENIED)
    5. confirm_required 路径 (need_confirm 且无 --force)
    6. Redis 分布式锁 (cmd:lock:session:{sid}, 10s)
    7. 计时 + 调用 handler
    8. fire-and-forget audit
    9. 释放锁,返回结果
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from redis.asyncio import Redis

from app.commands.audit import CommandAuditService, fire_and_forget
from app.commands.parser import parser
from app.commands.permissions import has_permission
from app.commands.registry import CommandRegistry
from app.commands.types import (
    CommandContext,
    CommandErrorCode,
    CommandResult,
    ParsedCommand,
)

logger = logging.getLogger(__name__)


class CommandExecutor:
    """命令执行器 — 所有命令的入口."""

    LOCK_KEY_TEMPLATE = "cmd:lock:session:{session_id}"
    DEFAULT_LOCK_TIMEOUT = 10  # 秒 — plan §M6 修复

    def __init__(
        self,
        registry: CommandRegistry,
        audit: CommandAuditService | None = None,
        redis: Redis | None = None,
        lock_timeout: int = DEFAULT_LOCK_TIMEOUT,
    ) -> None:
        self.registry = registry
        self.audit = audit or CommandAuditService()
        self.redis = redis
        self.lock_timeout = lock_timeout

    async def execute(
        self,
        raw_input: str,
        context: CommandContext,
    ) -> CommandResult:
        """主入口 — 同步路径,所有异步副作用通过 fire-and-forget 解耦."""
        raw = raw_input.strip()

        # 1. // 透传检测 (plan V.1 退出标准: // 透传给 LLM)
        if raw.startswith("//"):
            original = raw[2:].strip()
            return CommandResult(
                success=False,
                action="passthrough",
                error_code=CommandErrorCode.PASSTHROUGH,
                message=original,
                data={"passthrough": True, "original_input": raw},
            )

        if not raw.startswith("/"):
            return CommandResult(
                success=False,
                action="passthrough",
                error_code=CommandErrorCode.PASSTHROUGH,
                message=raw,
                data={"passthrough": True, "original_input": raw},
            )

        # 2. parse
        try:
            parsed = parser.parse(raw)
        except ValueError as e:
            result = CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"命令解析失败: {e}",
            )
            self._fire_audit(parsed=None, raw=raw, context=context, result=result)
            return result

        if parsed is None:
            result = CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"无法解析的命令: {raw!r}",
            )
            self._fire_audit(parsed=None, raw=raw, context=context, result=result)
            return result

        if not parsed.name.startswith("/"):
            parsed.name = "/" + parsed.name

        # 3. registry.get
        entry = self.registry.get(parsed.name)
        if entry is None:
            result = CommandResult.error(
                CommandErrorCode.CMD_NOT_FOUND,
                message=f"未知命令: /{parsed.name},输入 /help 查看可用命令",
            )
            self._fire_audit(parsed=parsed, raw=raw, context=context, result=result)
            return result

        # 4. permission
        perm_ok, perm_error = has_permission(
            perm=entry["permission"],
            permissions=context.permissions,
        )
        if not perm_ok:
            result = CommandResult.error(
                CommandErrorCode.PERMISSION_DENIED,
                message=perm_error or f"权限不足: 需要 {entry['permission'].name}",
            )
            self._fire_audit(parsed=parsed, raw=raw, context=context, result=result)
            return result

        # 5. confirm_required 路径
        if entry["need_confirm"] and not parsed.flags.get("force"):
            token = self._mint_token()
            result = CommandResult.confirm_required(
                token=token,
                message=f"命令 /{parsed.name} 需要确认,请使用 --force 重新执行",
            )
            self._fire_audit(
                parsed=parsed, raw=raw, context=context,
                result=result, confirmation_token=token,
            )
            return result

        # 6. Redis 分布式锁
        lock = await self._acquire_lock(context.session_id)
        if lock is None:
            result = CommandResult.error(
                CommandErrorCode.LOCK_TIMEOUT,
                message=f"会话 {context.session_id or 'default'} 正忙,请稍后重试",
            )
            self._fire_audit(parsed=parsed, raw=raw, context=context, result=result)
            return result

        # 7. 计时 + handler
        start = time.perf_counter()
        try:
            handler_result = await entry["handler"](parsed.args, parsed.flags, context)
        except Exception as e:
            logger.exception("命令 /%s 执行异常", parsed.name)
            handler_result = CommandResult.error(
                CommandErrorCode.INTERNAL_ERROR,
                message=f"命令执行异常: {e}",
            )
        duration_ms = (time.perf_counter() - start) * 1000.0

        # 8. fire-and-forget audit
        self._fire_audit(
            parsed=parsed, raw=raw, context=context,
            result=handler_result, duration_ms=duration_ms,
        )

        # 9. 释放锁
        if lock is not None and not isinstance(lock, _NoOpLock):
            try:
                await lock.release()
            except Exception as e:
                logger.warning("Redis 锁释放失败: %s", e)

        return handler_result

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    async def _acquire_lock(self, session_id: str | None) -> Any | None:
        """获取 Redis 锁;没有 redis client 视为无锁(测试场景).

        Returns:
            _NoOpLock: 成功(无锁模式)
            redis 锁对象: 成功(持有锁, 调用方负责 release)
            None: 获取失败 (返回 LOCK_TIMEOUT)
        """
        if not self.redis or not session_id:
            return _NoOpLock()
        try:
            key = self.LOCK_KEY_TEMPLATE.format(session_id=session_id)
            lock = self.redis.lock(
                name=key,
                timeout=self.lock_timeout,
                blocking=False,
            )
            acquired = await lock.acquire()
            if not acquired:
                return None
            return lock
        except Exception as e:
            logger.warning("Redis 锁初始化失败,降级为 no-op: %s", e)
            return None

    def _mint_token(self) -> str:
        """生成 confirmation token."""
        import uuid as _uuid
        return f"confirm-{_uuid.uuid4().hex[:16]}"

    def _fire_audit(
        self,
        parsed: ParsedCommand | None,
        raw: str,
        context: CommandContext,
        result: CommandResult,
        duration_ms: float | None = None,
        confirmation_token: str | None = None,
    ) -> None:
        """audit 写入 — fire-and-forget,失败不影响主结果."""
        if parsed is not None and not parsed.name.startswith("/"):
            parsed.name = "/" + parsed.name
        command_name = parsed.name if parsed else raw
        fire_and_forget(
            self.audit,
            command_name=command_name,
            args=parsed.args if parsed else [],
            flags=parsed.flags if parsed else {},
            result_code=result.error_code.value,
            duration_ms=duration_ms,
            session_id=context.session_id,
            user_id=context.user_id,
            confirmation_token=confirmation_token,
            error_message=result.message if not result.success else None,
        )


class _NoOpLock:
    """无锁场景的回退实现 — 支持 async with 协议."""

    async def __aenter__(self) -> "_NoOpLock":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None
