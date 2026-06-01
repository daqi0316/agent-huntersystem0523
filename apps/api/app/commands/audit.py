"""CommandAuditService — 命令执行审计写入.

设计要点：
- 不复用 OperationLog（plan §M2 修复）
- 写入失败不阻塞主流程（fire-and-forget）
- 字段完整对应 plan V.1 退出标准
- 提供 list_recent() 辅助查询,供 V.5 /debug 与前端 audit 页消费
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_audit_log import CommandAuditLog

logger = logging.getLogger(__name__)


class CommandAuditService:
    """命令审计服务.

    使用方式：
        svc = CommandAuditService(db)
        asyncio.create_task(svc.record(...))   # fire-and-forget
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    async def record(
        self,
        command_name: str,
        args: list[str] | None = None,
        flags: dict[str, Any] | None = None,
        result_code: str = "success",
        duration_ms: float | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        confirmation_token: str | None = None,
        error_message: str | None = None,
    ) -> CommandAuditLog | None:
        """写入一条审计记录.

        失败时仅记录日志,不抛异常 — 审计不应阻塞业务.
        """
        if not self.db:
            logger.warning("CommandAuditService 没有 db session,跳过写入")
            return None

        try:
            entry = CommandAuditLog(
                id=str(uuid.uuid4()),
                command_name=command_name,
                args=args or [],
                flags=flags or {},
                result_code=result_code,
                duration_ms=duration_ms,
                confirmation_token=confirmation_token,
                session_id=session_id,
                user_id=user_id,
                error_message=error_message,
            )
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)
            return entry
        except Exception as e:
            # 审计失败必须吞掉,避免污染业务结果
            try:
                await self.db.rollback()
            except Exception:
                pass
            logger.warning("CommandAuditService.record 失败: %s", e)
            return None

    async def list_recent(
        self,
        command_name: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[CommandAuditLog]:
        """按条件查询最近审计 — 给 /debug 与 audit 页用."""
        if not self.db:
            return []
        stmt = select(CommandAuditLog)
        if command_name:
            stmt = stmt.where(CommandAuditLog.command_name == command_name)
        if session_id:
            stmt = stmt.where(CommandAuditLog.session_id == session_id)
        if user_id:
            stmt = stmt.where(CommandAuditLog.user_id == user_id)
        stmt = stmt.order_by(desc(CommandAuditLog.created_at)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


def fire_and_forget(
    svc: CommandAuditService,
    command_name: str,
    args: list[str] | None = None,
    flags: dict[str, Any] | None = None,
    result_code: str = "success",
    duration_ms: float | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    confirmation_token: str | None = None,
    error_message: str | None = None,
) -> None:
    """便捷函数:把 audit 写入转成 fire-and-forget 任务.

    在 executor 的 hot path 上调用,避免审计失败阻塞主流程.
    """
    import asyncio

    coro = svc.record(
        command_name=command_name,
        args=args,
        flags=flags,
        result_code=result_code,
        duration_ms=duration_ms,
        session_id=session_id,
        user_id=user_id,
        confirmation_token=confirmation_token,
        error_message=error_message,
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # 没有运行中的 loop(测试场景),退化为同步 await
        asyncio.run(coro)
