"""Orchestrator Session — 持久化编排器状态，支持审批后恢复执行。

当 OrchestratorAgent 因 human-in-the-loop 暂停时，当前状态
（sub_tasks, shared_context, 已完成的 results 等）被保存到 Redis。
审批通过后，可通过 session_id 恢复执行。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


_ORCH_SESSION_PREFIX = "orch:session:"
_ORCH_SESSION_APPROVAL_INDEX = "orch:approval_session:"  # approval_id → session_id
_SESSION_TTL = 86400  # 24h


class OrchestratorSession:
    """存储编排器在 human-in-the-loop 暂停点的完整状态。

    Fields:
        session_id: 唯一会话 ID
        task: 原始任务文本
        context: 原始上下文 dict
        sub_tasks: 子任务定义列表
        levels: DAG 分层（每层为索引列表）
        results: 各子任务结果（None 表示未执行）
        shared_context: shared_context dict
        paused_at_level: 暂停时所在的 DAG 层级索引
        approval_ids: 属于该会话的审批 ID 列表（按暂停顺序）
        status: paused / resumed / completed
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"os_{uuid.uuid4().hex[:12]}"
        self.task: str = ""
        self.context: dict[str, Any] = {}
        self.sub_tasks: list[dict] = []
        self.levels: list[list[int]] = []
        self.results: list[dict | None] = []
        self.shared_context: dict[str, Any] = {}
        self.paused_at_level: int = -1
        self.approval_ids: list[str] = []
        self.status: str = "paused"

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "context": self.context,
            "sub_tasks": self.sub_tasks,
            "levels": self.levels,
            "results": _clean_results(self.results),
            "shared_context": self.shared_context,
            "paused_at_level": self.paused_at_level,
            "approval_ids": self.approval_ids,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OrchestratorSession:
        s = cls(session_id=data.get("session_id", ""))
        s.task = data.get("task", "")
        s.context = data.get("context", {})
        s.sub_tasks = data.get("sub_tasks", [])
        s.levels = data.get("levels", [])
        s.results = data.get("results", [])
        s.shared_context = data.get("shared_context", {})
        s.paused_at_level = data.get("paused_at_level", -1)
        s.approval_ids = data.get("approval_ids", [])
        s.status = data.get("status", "paused")
        return s

    # ── Redis 持久化 ──

    async def _redis(self) -> Any:
        from app.agents.shared_memory import RedisBackend
        from app.core.redis import get_redis

        client = await get_redis()
        if client is not None:
            return RedisBackend(client)
        return None

    async def save(self) -> None:
        redis = await self._redis()
        if redis is None:
            logger.warning("Redis unavailable, session %s not persisted", self.session_id)
            return
        raw = json.dumps(self.to_dict(), ensure_ascii=False, default=str).encode()
        await redis.set(self._session_key(), raw, ttl=_SESSION_TTL)
        for aid in self.approval_ids:
            await redis.set(
                _ORCH_SESSION_APPROVAL_INDEX + aid,
                self.session_id.encode(),
                ttl=_SESSION_TTL,
            )
        logger.info("Session %s saved (%d sub_tasks, approval_ids=%s)",
                     self.session_id, len(self.sub_tasks), self.approval_ids)

    async def delete(self) -> None:
        redis = await self._redis()
        if redis is None:
            return
        await redis.delete(self._session_key())
        for aid in self.approval_ids:
            await redis.delete(_ORCH_SESSION_APPROVAL_INDEX + aid)

    def _session_key(self) -> str:
        return _ORCH_SESSION_PREFIX + self.session_id

    @classmethod
    async def load(cls, session_id: str) -> OrchestratorSession | None:
        from app.agents.shared_memory import RedisBackend
        from app.core.redis import get_redis

        client = await get_redis()
        if client is None:
            return None
        redis = RedisBackend(client)
        raw = await redis.get(_ORCH_SESSION_PREFIX + session_id)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning("Failed to load session %s: %s", session_id, e)
            return None

    @classmethod
    async def find_by_approval_id(cls, approval_id: str) -> OrchestratorSession | None:
        from app.agents.shared_memory import RedisBackend
        from app.core.redis import get_redis

        client = await get_redis()
        if client is None:
            return None
        redis = RedisBackend(client)
        raw = await redis.get(_ORCH_SESSION_APPROVAL_INDEX + approval_id)
        if raw is None:
            return None
        session_id = raw.decode() if isinstance(raw, bytes) else raw
        return await cls.load(session_id)


def _clean_results(results: list[dict | None]) -> list[dict | None]:
    """Remove non-serializable entries (e.g. Exception objects) from results."""
    cleaned: list[dict | None] = []
    for r in results:
        if r is None:
            cleaned.append(None)
        elif isinstance(r, dict):
            cleaned.append(r)
        else:
            cleaned.append({"status": "unknown", "summary": str(r)[:100]})
    return cleaned
