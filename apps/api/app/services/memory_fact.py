"""Structured memory fact service.

Records agent actions/decisions as structured facts and retrieves them
for system-prompt injection — giving the agent precise cross-session recall.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_fact import MemoryFact

logger = logging.getLogger(__name__)

# ── Constants ──

MAX_FACTS_PER_INJECTION = 30
FACT_RECENT_DAYS = 30  # only consider facts from the last 30 days


class MemoryFactService:
    """Record, query, and format structured memory facts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Record ──

    async def record_tool_result(
        self,
        user_id: str,
        session_id: str,
        tool_name: str,
        args: dict,
        result: object,
    ) -> list[MemoryFact]:
        """Convert a tool call result into structured facts and persist."""
        facts: list[MemoryFact] = []
        builder_fns = {
            "search_candidates": self._fact_search_candidates,
            "get_candidate": self._fact_get_candidate,
            "screen_resume": self._fact_screen_resume,
            "schedule_interview": self._fact_schedule_interview,
            "generate_jd": self._fact_generate_jd,
            "list_jobs": self._fact_list_jobs,
            "get_dashboard_stats": self._fact_viewed_dashboard,
            "search_knowledge": self._fact_search_knowledge,
            "get_evaluations": self._fact_get_evaluations,
        }
        fn = builder_fns.get(tool_name)
        if not fn:
            return []

        try:
            built = fn(user_id, session_id, args, result)
            if isinstance(built, list):
                facts.extend(built)
            else:
                facts.append(built)
        except Exception as e:
            logger.warning("Failed to build fact for %s: %s", tool_name, e)
            return []

        for fact in facts:
            self.db.add(fact)
        try:
            await self.db.commit()
        except Exception as e:
            logger.error("Failed to persist memory facts: %s", e)
            await self.db.rollback()
            return []

        return facts

    # ── Fact builders ──

    def _fact_search_candidates(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        results_list = result if isinstance(result, list) else []
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="agent_action",
            subject_type="candidate",
            verb="searched",
            object_value={
                "query": args.get("query", ""),
                "skill": args.get("skill", ""),
                "experience_min": args.get("experience_min"),
                "count": len(results_list),
            },
        )

    def _fact_get_candidate(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        cand = result if isinstance(result, dict) else {}
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="candidate_action",
            subject_type="candidate",
            subject_id=args.get("candidate_id", cand.get("id", "")),
            verb="viewed",
            object_value={
                "name": cand.get("name", ""),
                "current_title": cand.get("current_title", ""),
                "current_company": cand.get("current_company", ""),
            },
        )

    def _fact_screen_resume(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> list[MemoryFact]:
        data = result if isinstance(result, dict) else {}
        candidate_id = args.get("candidate_id", "")
        return [
            MemoryFact(
                user_id=user_id,
                session_id=session_id,
                fact_type="candidate_action",
                subject_type="candidate",
                subject_id=candidate_id,
                verb="screened",
                object_value={
                    "job_id": args.get("job_id", ""),
                    "score": data.get("overall_score", 0),
                    "passed": data.get("passed", False),
                    "summary": data.get("summary", ""),
                },
            ),
            MemoryFact(
                user_id=user_id,
                session_id=session_id,
                fact_type="decision",
                subject_type="candidate",
                subject_id=candidate_id,
                verb="passed" if data.get("passed") else "failed",
                object_value={
                    "job_id": args.get("job_id", ""),
                    "score": data.get("overall_score", 0),
                },
            ),
        ]

    def _fact_schedule_interview(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        data = result if isinstance(result, dict) else {}
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="candidate_action",
            subject_type="candidate",
            subject_id=args.get("candidate_id", ""),
            verb="scheduled_interview",
            object_value={
                "job_id": args.get("job_id", ""),
                "scheduled_time": args.get("scheduled_time", ""),
                "interview_id": data.get("id", ""),
                "notes": args.get("notes", ""),
            },
        )

    def _fact_generate_jd(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        data = result if isinstance(result, dict) else {}
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="agent_action",
            verb="generated_jd",
            object_value={
                "title": args.get("title", ""),
                "passed": data.get("passed", False),
            },
        )

    def _fact_list_jobs(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        results_list = result if isinstance(result, list) else []
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="agent_action",
            verb="listed_jobs",
            object_value={
                "status": args.get("status", "active"),
                "count": len(results_list),
            },
        )

    def _fact_viewed_dashboard(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="agent_action",
            verb="viewed_dashboard",
            object_value={},
        )

    def _fact_search_knowledge(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        data = result if isinstance(result, dict) else {}
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="agent_action",
            verb="searched_knowledge",
            object_value={
                "query": args.get("query", ""),
                "answer_preview": (data.get("answer", "") or "")[:200],
            },
        )

    def _fact_get_evaluations(
        self, user_id: str, session_id: str, args: dict, result: object
    ) -> MemoryFact:
        results_list = result if isinstance(result, list) else []
        return MemoryFact(
            user_id=user_id,
            session_id=session_id,
            fact_type="candidate_action",
            subject_type="candidate",
            subject_id=args.get("candidate_id", ""),
            verb="viewed_evaluations",
            object_value={"count": len(results_list)},
        )

    # ── Query for prompt injection ──

    async def get_structured_context(self, user_id: str) -> str:
        """Build a structured memory block for system-prompt injection.

        Returns a human-readable string like:
          【结构化记忆】
          候选人：
          - 张三 — 已查看 · 已初筛 (得分 85)
          - 李四 — 已安排面试 (周五 14:00)
          你上次的搜索：
          - 搜索 "Python" (找到 3 人)
        """
        facts = await self._recent_facts(user_id, limit=MAX_FACTS_PER_INJECTION)
        if not facts:
            return ""

        grouped = self._group_facts(facts)
        lines = ["\n【结构化记忆】"]

        # Candidate-centric facts
        candidate_groups = [g for g in grouped if g.subject_type == "candidate"]
        if candidate_groups:
            lines.append("你之前处理过的候选人：")
            for g in candidate_groups:
                label = g.label or g.subject_id or "未知"
                fact_str = " · ".join(g.facts)
                lines.append(f"  - {label} — {fact_str}")

        # Agent actions (searches, JD generation, etc.)
        agent_facts = [f for f in facts if f.fact_type == "agent_action"]
        if agent_facts:
            lines.append("你之前执行的操作：")
            seen = set()
            for f in agent_facts:
                text = self._format_agent_action(f)
                if text and text not in seen:
                    lines.append(f"  - {text}")
                    seen.add(text)

        lines.append("（以上是跨会话的长期记忆，供参考。）")
        return "\n".join(lines)

    async def _recent_facts(
        self,
        user_id: str,
        limit: int = MAX_FACTS_PER_INJECTION,
    ) -> list[MemoryFact]:
        """Fetch the most recent facts for a user."""
        stmt = (
            select(MemoryFact)
            .where(MemoryFact.user_id == user_id)
            .order_by(desc(MemoryFact.created_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _group_facts(self, facts: list[MemoryFact]) -> list["_FactGroup"]:
        """Group facts by (subject_type, subject_id) and build human-readable lines."""
        from app.schemas.memory_fact import MemoryFactGroup as FactGroup

        groups: dict[tuple[str, str | None], FactGroup] = {}
        for f in facts:
            if not f.subject_type:
                continue
            key = (f.subject_type, f.subject_id)
            if key not in groups:
                label = self._subject_label(f)
                groups[key] = FactGroup(
                    subject_type=f.subject_type,
                    subject_id=f.subject_id,
                    label=label,
                    facts=[],
                )
            line = self._format_fact(f)
            if line:
                groups[key].facts.append(line)
        return list(groups.values())

    def _subject_label(self, fact: MemoryFact) -> str:
        """Extract a human-readable label from the fact's object_value."""
        if fact.object_value:
            name = fact.object_value.get("name", "")
            if name:
                return name
        return fact.subject_id or ""

    def _format_fact(self, fact: MemoryFact) -> str:
        """Format a single fact into a human-readable string."""
        v = fact.object_value or {}
        verb_map = {
            "viewed": "已查看",
            "screened": f"已初筛 (得分 {v.get('score', '?')})",
            "scheduled_interview": f"已安排面试 ({v.get('scheduled_time', '?')[:10]})",
            "passed": "已通过初筛",
            "failed": "未通过初筛",
            "viewed_evaluations": f"已查看评估报告 ({v.get('count', 0)} 份)",
        }
        return verb_map.get(fact.verb, fact.verb)

    def _format_agent_action(self, fact: MemoryFact) -> str:
        """Format an agent_action fact into a line."""
        v = fact.object_value or {}
        if fact.verb == "searched":
            q = v.get("query", v.get("skill", ""))
            return f"搜索 \"{q}\" (找到 {v.get('count', 0)} 人)"
        if fact.verb == "generated_jd":
            return f"生成职位描述 \"{v.get('title', '')}\""
        if fact.verb == "listed_jobs":
            return f"查看职位列表 ({v.get('count', 0)} 个)"
        if fact.verb == "searched_knowledge":
            q = v.get("query", "")
            return f"搜索知识库 \"{q}\""
        if fact.verb == "viewed_dashboard":
            return "查看了招聘看板"
        return fact.verb



