"""FeedbackService — 反馈业务逻辑层。

职责:
  1. 接收并校验 FeedbackCreate 请求
  2. 持久化到 DB（通过 FeedbackStore）
  3. 通过 EventEmitter 发射反馈事件（进入 agentops event stream）
  4. 自动导出 ScoreEvent 到 Langfuse（通过 provider.record_score）
  5. 提供查询和聚合统计接口
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agentops.core.schemas import ScoreEvent
from app.agentops.core.context import get_context
from app.agentops.events.emitter import get_event_emitter
from app.agentops.events.schemas import BusinessEventType
from app.agentops.feedback.models import AgentFeedbackModel, FeedbackStore
from app.agentops.feedback.schemas import (
    FeedbackCategory,
    FeedbackCreate,
    FeedbackResponse,
    FeedbackSource,
    FeedbackStats,
    FeedbackUpdate,
)
from app.agentops.runtime import get_agentops_provider
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 自动导出为 Langfuse Score 的 category
_SCORE_EXPORT_CATEGORIES: frozenset[str] = frozenset({
    FeedbackCategory.RELEVANCE,
    FeedbackCategory.ACCURACY,
    FeedbackCategory.COMPLETENESS,
    FeedbackCategory.QUALITY,
})


class FeedbackService:
    """反馈业务服务 — 无状态，线程安全。"""

    def __init__(self, db: AsyncSession | None = None):
        self._store = FeedbackStore(db=db)
        self._db = db

    async def create_feedback(
        self,
        req: FeedbackCreate,
        user_id: str = "",
    ) -> AgentFeedbackModel | None:
        """创建一条反馈。

        1. 持久化到 DB
        2. 发射 BusinessEvent
        3. 导出 Langfuse Score

        返回 AgentFeedbackModel，None 表示失败。
        """
        feedback_id = str(uuid4())
        now = datetime.now(UTC)
        ctx = get_context()

        tags_json = json.dumps(req.tags, ensure_ascii=False) if req.tags else None
        effective_user_id = user_id or (ctx.user_id if ctx else "")
        effective_trace_id = req.target.trace_id or (ctx.trace_id if ctx else "")
        effective_session_id = req.target.session_id or (ctx.session_id if ctx else "")

        model = AgentFeedbackModel(
            id=feedback_id,
            category=req.category.value,
            source=req.source.value,
            score=req.score,
            reason=req.reason,
            trace_id=effective_trace_id or None,
            span_id=req.target.span_id or None,
            message_id=req.target.message_id or None,
            session_id=effective_session_id or None,
            target_entity_type=req.target.entity_type or None,
            target_entity_id=req.target.entity_id or None,
            user_id=effective_user_id or None,
            tags=tags_json,
            metadata_json=req.metadata or None,
            created_at=now,
            updated_at=now,
        )

        try:
            saved = await self._store.save(model)
            if saved is None:
                return None
        except Exception as exc:
            logger.error("FeedbackService: DB save failed: %s", exc)
            return None

        # 发射业务事件（非阻塞）
        await self._emit_feedback_event(model)

        # 导出 Langfuse Score（非阻塞）
        await self._export_score(model)

        return saved

    async def get_feedback(self, feedback_id: str) -> AgentFeedbackModel | None:
        """按 ID 查询。"""
        return await self._store.get(feedback_id)

    async def list_feedback(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentFeedbackModel], int]:
        """条件查询。"""
        return await self._store.list(
            category=category,
            source=source,
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    async def get_stats(
        self,
        *,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> FeedbackStats:
        """聚合统计。"""
        return await self._store.stats(
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
        )

    # ── 内部 ──

    async def _emit_feedback_event(self, model: AgentFeedbackModel) -> None:
        """发射反馈业务事件。"""
        try:
            emitter = get_event_emitter()
            domain: dict[str, Any] = {
                "feedback_id": model.id,
                "category": model.category,
                "source": model.source,
                "score": model.score,
            }
            if model.reason:
                domain["reason"] = model.reason

            # 确定 entity_type / entity_id (优先用 target_entity，其次 trace_id)
            entity_type = model.target_entity_type or ""
            entity_id_val = model.target_entity_id or ""

            # 自动为标注/规则类反馈标记 bad_case 标签
            tags: list[str] = []
            if model.tags:
                tags = json.loads(model.tags) if isinstance(model.tags, str) else model.tags or []
            if model.source in (FeedbackSource.ANNOTATOR, FeedbackSource.AUTO_RULE, FeedbackSource.AUTO_EVALUATOR):
                if "bad_case" not in tags:
                    tags.append("bad_case")

            await emitter.emit(
                event_type=BusinessEventType.FEEDBACK_SUBMITTED,
                entity_type=entity_type,
                entity_id=entity_id_val,
                domain_fields=domain,
                user_id=model.user_id or "",
                session_id=model.session_id or "",
                tags=tags,
            )
        except Exception as exc:
            logger.debug("FeedbackService: event emit failed (non-blocking): %s", exc)

    async def _export_score(self, model: AgentFeedbackModel) -> None:
        """如果 category 在导出白名单中，同步写入 Langfuse Score。"""
        if not model.trace_id:
            return
        if model.category not in _SCORE_EXPORT_CATEGORIES:
            return

        try:
            provider = get_agentops_provider()
            await provider.record_score(ScoreEvent(
                name=f"feedback.{model.category}",
                trace_id=model.trace_id,
                value=model.score,
                comment=model.reason or "",
                source=model.source,
                tags=[model.category],
            ))
        except Exception as exc:
            logger.debug("FeedbackService: score export failed (non-blocking): %s", exc)
