"""AuditLogger — Agent 操作审计日志。

记录: 谁 → 什么时间 → 调用哪个 Agent → 输入/输出摘要。
存储: 内存环形缓冲区 + 可选的异步持久化钩子。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

PersistHook = Callable[["AuditEntry"], Coroutine[Any, Any, None]]


@dataclass
class AuditEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    user_id: str = ""
    user_role: str = ""
    agent_name: str = ""
    action: str = ""
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def datetime_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()


class AuditLogger:
    """Agent 操作审计日志。

    用法:
        logger = AuditLogger(max_entries=5000)
        await logger.record(
            user_id="u-123",
            agent_name="screening",
            action="screen_resume",
            input_summary="candidate=c-456",
            output_summary="score=85, passed=True",
            duration_ms=1240,
        )
        recent = logger.query(agent_name="screening", limit=10)
    """

    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._persist_hooks: list[PersistHook] = []

    def add_persist_hook(self, hook: PersistHook) -> None:
        """注册异步持久化钩子（如写入 DB）。"""
        self._persist_hooks.append(hook)

    async def record(
        self,
        user_id: str = "",
        user_role: str = "",
        agent_name: str = "",
        action: str = "",
        input_summary: str = "",
        output_summary: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        tags: list[str] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            user_id=user_id,
            user_role=user_role,
            agent_name=agent_name,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            success=success,
            error=error,
            tags=tags or [],
        )

        async with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

        for hook in self._persist_hooks:
            try:
                await hook(entry)
            except Exception as e:
                logger.warning("Audit persist hook failed: %s", e)

        return entry

    def query(
        self,
        user_id: str | None = None,
        agent_name: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        tag: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按条件查询审计日志。"""
        entries = self._entries

        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if agent_name:
            entries = [e for e in entries if e.agent_name == agent_name]
        if action:
            entries = [e for e in entries if e.action == action]
        if success is not None:
            entries = [e for e in entries if e.success == success]
        if tag:
            entries = [e for e in entries if tag in e.tags]

        return [e.to_dict() for e in entries[-limit - offset:-offset or None]][-limit:]

    def stats(self) -> dict:
        """审计日志统计摘要。"""
        total = len(self._entries)
        success_count = sum(1 for e in self._entries if e.success)
        by_agent: dict[str, int] = {}
        for e in self._entries:
            by_agent[e.agent_name] = by_agent.get(e.agent_name, 0) + 1
        by_action: dict[str, int] = {}
        for e in self._entries:
            by_action[e.action] = by_action.get(e.action, 0) + 1
        return {
            "total_entries": total,
            "success_rate": round(success_count / total * 100, 1) if total > 0 else 0,
            "by_agent": by_agent,
            "by_action": by_action,
        }

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


_audit_logger_instance: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger()
    return _audit_logger_instance
