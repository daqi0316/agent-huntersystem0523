"""Cross-session memory summary service.

Generates LLM-based conversation summaries, persists them in PostgreSQL,
indexes them in Qdrant for vector similarity search, and retrieves
relevant context before each agent interaction.

Supports hybrid retrieval: vector similarity (Qdrant) + keyword FTS (PostgreSQL).

Usage:
    summary_svc = SummaryService(db, llm, qdrant)
    await summary_svc.generate(user_id, session_id, messages)
    memories = await summary_svc.get_relevant(user_id, query)
    fts_results = await summary_svc.search_fts(user_id, "keyword")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models.session_summary import SessionSummary
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# ── Search mode ──

SEARCH_MODE_VECTOR = "vector"
SEARCH_MODE_FTS = "fts"
SEARCH_MODE_HYBRID = "hybrid"

# ── Constants ──

DEFAULT_TOP_K = 3
DEFAULT_SCORE_THRESHOLD = 0.65
MAX_MEMORY_TOKENS = 1500
MIN_MESSAGES_FOR_SUMMARY = 6

_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话摘要助手。请用一段简洁的中文总结以下招聘助手中的对话。"
    "聚焦用户意图、候选人信息、筛选决定、面试安排等关键信息。"
    "控制在 300 字以内。\n\n"
    "然后从对话中提取结构化洞察（信息不足则用 null 或空数组）。\n"
    '请严格按以下 JSON 格式返回（只输出 JSON，不要额外文字）：\n'
    '{\n'
    '  "summary": "摘要内容",\n'
    '  "key_insights": {\n'
    '    "preferred_skills": ["Python", "FastAPI"],\n'
    '    "salary_range": "30k-40k",\n'
    '    "screening_patterns": ["tech lead background preferred"],\n'
    '    "rejected_reasons": []\n'
    '  }\n'
    '}'
)


def _try_parse_json_summary(raw: str) -> dict | None:
    """Try to parse the LLM response as a JSON object with summary + key_insights.

    Handles both pure JSON and JSON wrapped in markdown code blocks.
    """
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Find the first { or [
        start = text.find("{")
        if start == -1:
            return None
        end = text.rfind("}")
        if end == -1:
            return None
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "summary" in parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return None


class SummaryService:
    """Cross-session memory: generate, store, retrieve, manage summaries."""

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMClient,
        qdrant: QdrantService,
    ):
        self.db = db
        self.llm = llm
        self.qdrant = qdrant

    # ── Generate & Store ──

    async def generate(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict],
    ) -> str | None:
        """Generate a summary of the conversation and persist it.

        Steps:
            1. Call LLM to summarize + extract key_insights (skip if too few messages).
            2. Embed the summary text.
            3. Ensure Qdrant collection exists.
            4. Upsert to Qdrant (vector).
            5. Upsert to PostgreSQL (metadata + key_insights).
               The tsvector search_vector is auto-updated by PG trigger
               whenever summary changes.

        Returns the summary text, or None if skipped.
        """
        if len(messages) < MIN_MESSAGES_FOR_SUMMARY:
            return None

        result = await self._call_summary_llm(messages)
        if not result:
            return None

        summary_text, key_insights = result
        if not summary_text or summary_text == "[LLM unavailable]":
            return None

        # Embed
        vector = await self.llm.embed(summary_text)
        if not vector:
            logger.warning(
                "Embedding returned empty for session %s, skipping Qdrant",
                session_id,
            )
            # Still save to PG so it appears in the memory management UI
            await self._upsert_pg(user_id, session_id, summary_text, key_insights)
            return summary_text

        # Qdrant
        vector_size = len(vector)
        await self.qdrant.ensure_collection(vector_size)
        await self.qdrant.upsert(
            point_id=session_id,
            vector=vector,
            payload={
                "user_id": user_id,
                "session_id": session_id,
                "summary": summary_text,
                "key_insights": key_insights,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # PG (search_vector auto-updated by trigger)
        await self._upsert_pg(user_id, session_id, summary_text, key_insights)

        logger.info(
            "Generated summary for session %s (user=%s, dim=%d)",
            session_id,
            user_id,
            vector_size,
        )
        return summary_text

    async def _call_summary_llm(
        self,
        messages: list[dict],
    ) -> tuple[str, dict | None] | None:
        """Call LLM to produce a summary + structured key_insights.

        Returns (summary_text, key_insights_dict_or_None) or None on failure.
        """
        recent = messages[-MIN_MESSAGES_FOR_SUMMARY:]
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in recent
            if m.get("content")
        )
        if not conversation_text.strip():
            return None

        raw = await self.llm.chat(
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        if not raw:
            return None

        # Try to parse JSON response (the prompt requests structured JSON)
        parsed = _try_parse_json_summary(raw)
        if parsed:
            return parsed.get("summary", raw), parsed.get("key_insights")

        # Fallback: treat raw as plain summary text
        return raw, None

    async def _upsert_pg(
        self,
        user_id: str,
        session_id: str,
        summary_text: str,
        key_insights: dict | None = None,
    ) -> None:
        """Upsert summary in PostgreSQL (idempotent on user_id+session_id).

        The search_vector TSVECTOR column is automatically updated by
        the PG trigger ``trg_session_summaries_search_vector`` whenever
        summary is inserted or updated — no manual vector computation needed.
        """
        stmt = select(SessionSummary).where(
            SessionSummary.user_id == user_id,
            SessionSummary.session_id == session_id,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.summary = summary_text
            existing.key_insights = key_insights
            existing.updated_at = datetime.now(timezone.utc)
        else:
            record = SessionSummary(
                user_id=user_id,
                session_id=session_id,
                summary=summary_text,
                key_insights=key_insights,
            )
            self.db.add(record)

        await self.db.commit()

    # ── Retrieve ──

    async def search_fts(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict]:
        """Full-text keyword search on session summaries via PostgreSQL FTS.

        Uses ``plainto_tsquery`` for simple keyword parsing and
        ``ts_rank`` for relevance ranking. Results are filtered
        to the given user only.

        Returns a list of dicts with keys: id, session_id, summary,
        key_insights, created_at, updated_at, rank.
        """
        if not query.strip():
            return []

        # Build tsquery from plain keywords; rank by relevance
        sql = text(
            "SELECT id, session_id, summary, key_insights, "
            "       created_at, updated_at, "
            "       ts_rank(search_vector, plainto_tsquery('simple', :q)) AS rank "
            "FROM session_summaries "
            "WHERE user_id = :user_id "
            "  AND search_vector @@ plainto_tsquery('simple', :q) "
            "ORDER BY rank DESC "
            "LIMIT :limit"
        )
        rows = await self.db.execute(
            sql,
            {"q": query, "user_id": user_id, "limit": top_k},
        )
        results = []
        for row in rows.mappings():
            item = dict(row)
            # Ensure key_insights is parsed from JSONB
            if isinstance(item.get("key_insights"), str):
                try:
                    item["key_insights"] = json.loads(item["key_insights"])
                except (json.JSONDecodeError, TypeError):
                    item["key_insights"] = None
            results.append(item)
        return results

    async def get_relevant(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        mode: str = SEARCH_MODE_VECTOR,
    ) -> list[dict]:
        """Retrieve relevant past summaries for a query.

        Supports three retrieval modes:
        - ``vector`` (default): Qdrant vector similarity search.
        - ``fts``: PostgreSQL full-text keyword search (no embedding needed).
        - ``hybrid``: vector + FTS results merged by weighted score.

        Falls back gracefully on embedding / Qdrant failures.
        """
        if not query.strip():
            return []

        # ── Pure FTS mode ──
        if mode == SEARCH_MODE_FTS:
            return await self.search_fts(user_id, query, top_k=top_k)

        # ── Vector mode (default) ──
        vector = await self.llm.embed(query)
        if not vector and mode == SEARCH_MODE_VECTOR:
            return []
        if not vector and mode == SEARCH_MODE_HYBRID:
            # Fallback: FTS-only when embedding fails
            return await self.search_fts(user_id, query, top_k=top_k)

        # Qdrant search
        qdrant_results = await self.qdrant.search(
            vector=vector,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        vector_results = [r for r in qdrant_results if r.get("user_id") == user_id]

        if mode != SEARCH_MODE_HYBRID:
            return vector_results

        # ── Hybrid: merge vector + FTS by weighted score ──
        fts_results = await self.search_fts(user_id, query, top_k=top_k)

        # Build a merged result set: interleave and deduplicate by session_id
        seen: set[str] = set()
        merged: list[dict] = []

        # Weighted scoring: vector results get 0.7 weight, FTS gets 0.3
        fts_by_session = {r["session_id"]: r for r in fts_results}

        # Start with vector results, augmenting with FTS rank if available
        for vr in vector_results:
            sid = vr.get("session_id", "")
            if sid in seen:
                continue
            seen.add(sid)

            fts_item = fts_by_session.get(sid)
            if fts_item is not None:
                vr["_fts_rank"] = fts_item.get("rank", 0)
                vr["_mode"] = "hybrid"
            else:
                vr["_fts_rank"] = 0.0
                vr["_mode"] = "vector"
            merged.append(vr)

        # Add any FTS-only results not already covered
        for fr in fts_results:
            sid = fr.get("session_id", "")
            if sid in seen:
                continue
            seen.add(sid)
            fr["score"] = fr.get("rank", 0) * 0.3  # normalize for hybrid
            fr["_fts_rank"] = fr.get("rank", 0)
            fr["_mode"] = "fts"
            merged.append(fr)

        # Sort by weighted score
        merged.sort(key=lambda x: x.get("_fts_rank", 0), reverse=True)
        return merged[:top_k]

    async def get_injection_context(
        self,
        user_id: str,
        query: str,
        max_tokens: int = MAX_MEMORY_TOKENS,
    ) -> str:
        """Build a short system-prompt snippet from relevant memories.

        Returns an empty string when no relevant memories are found,
        or when the dedup check (latest summary matches query too closely)
        returns no additional context.
        """
        memories = await self.get_relevant(user_id, query)
        if not memories:
            return ""

        # Dedup: if the top-1 memory is extremely close to the current
        # session, skip injection (avoids repetitive context)
        if len(memories) > 0 and memories[0].get("score", 0) > 0.95:
            return ""

        lines: list[str] = []
        token_est = 0
        for m in memories:
            summary = (m.get("summary") or "").strip()
            est = len(summary) * 2  # rough CJK token estimate
            if not summary or token_est + est > max_tokens:
                continue
            lines.append(f"- [{m.get('session_id', '?')[:8]}...] {summary}")
            token_est += est

        if not lines:
            return ""

        text = "\n".join(lines)
        return (
            "\n\n【历史记忆】\n"
            "以下是你与用户之前会话中的关键信息，供参考：\n"
            f"{text}\n"
            "（注意：这是过去的记忆，请根据当前对话判断是否仍然有效。）"
        )

    # ── CRUD for management UI ──

    async def list_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        """Paginated list of all summaries for a user (PG-backed)."""
        count_q = select(func.count(SessionSummary.id)).where(
            SessionSummary.user_id == user_id
        )
        total = (await self.db.execute(count_q)).scalar() or 0

        q = (
            select(SessionSummary)
            .where(SessionSummary.user_id == user_id)
            .order_by(SessionSummary.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await self.db.execute(q)).scalars().all()

        items = [
            {
                "id": r.id,
                "session_id": r.session_id,
                "summary": r.summary,
                "key_insights": r.key_insights,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
        return items, total

    async def update_summary(
        self,
        summary_id: str,
        new_summary: str,
        user_id: str,
    ) -> bool:
        """Update a summary's text (PG + re-embed in Qdrant).

        When ``summary`` changes, the PG trigger automatically
        recalculates the ``search_vector`` tsvector column.
        """
        stmt = select(SessionSummary).where(
            SessionSummary.id == summary_id,
            SessionSummary.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        record.summary = new_summary
        record.updated_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Re-embed in Qdrant
        vector = await self.llm.embed(new_summary)
        if vector and len(vector) > 0:
            await self.qdrant.ensure_collection(len(vector))
            await self.qdrant.upsert(
                point_id=record.session_id,
                vector=vector,
                payload={
                    "user_id": user_id,
                    "session_id": record.session_id,
                    "summary": new_summary,
                    "key_insights": record.key_insights,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                },
            )

        return True

    async def delete_summary(self, summary_id: str, user_id: str) -> bool:
        """Delete a summary (PG + Qdrant)."""
        stmt = select(SessionSummary).where(
            SessionSummary.id == summary_id,
            SessionSummary.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        await self.db.delete(record)
        await self.db.commit()

        # Remove from Qdrant
        await self.qdrant.delete(record.session_id)
        return True
