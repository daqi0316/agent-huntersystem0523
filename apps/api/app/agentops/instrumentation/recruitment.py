"""RecruitmentEvents — 招聘业务流程事件发射器 (P2-C Stage 9).

设计原则:
- fire-and-forget: 所有方法内部 try/except，异常只打 warning，永远不抛
- 自动关联: 通过 AgentOpsContext 继承 trace_id/span_id/user_id/session_id
- 职责明确: 每个方法接收明确的业务参数，不依赖全局状态

风险: asyncio.create_task 在 FastAPI 正常 shutdown 时会被等待，
但极端情况（SIGKILL）下事件可能丢失。丢失的是分析事件，不是业务数据。
"""
from __future__ import annotations

import logging

from app.agentops.events.emitter import get_event_emitter
from app.agentops.events.schemas import BusinessEventType

logger = logging.getLogger(__name__)

_PII_KEYS: frozenset[str] = frozenset({"name", "email", "phone", "address"})


def _strip_pii_from_domain(domain: dict) -> dict:
    return {k: v for k, v in domain.items() if k not in _PII_KEYS}


class RecruitmentEvents:
    """招聘业务事件发射器 — 静态方法，非阻塞，自动关联 trace。

    所有方法返回 None，异常只打 warning 不抛。
    """

    @staticmethod
    async def on_resume_parsed(
        candidate_id: str,
        quality_score: float,
        confidence: float,
        red_flags: list[str] | None = None,
        field_completeness: float | None = None,
        needs_human_review: bool = False,
        error: str = "",
    ) -> None:
        """简历解析完成/失败时调用。"""
        try:
            emitter = get_event_emitter()
            etype = (BusinessEventType.RESUME_PARSING_FAILED if error
                     else BusinessEventType.RESUME_PARSING_COMPLETED)
            await emitter.emit(
                event_type=etype,
                entity_type="candidate",
                entity_id=candidate_id,
                domain_fields=_strip_pii_from_domain({
                    "quality_score": quality_score,
                    "confidence": confidence,
                    "red_flags": red_flags or [],
                    "field_completeness": field_completeness or round(confidence, 2),
                    "needs_human_review": needs_human_review,
                }),
                error=error,
                tags=["resume", "bad_case"] if (red_flags or error) else ["resume"],
            )
        except Exception as exc:
            logger.warning("on_resume_parsed failed (non-blocking): %s", exc)

    @staticmethod
    async def on_screening_completed(
        candidate_id: str,
        job_id: str,
        match_score: float,
        decision: str,
        dimension_scores: dict[str, float] | None = None,
        reason_codes: list[str] | None = None,
        needs_human_review: bool = False,
    ) -> None:
        """筛选完成时调用。"""
        try:
            emitter = get_event_emitter()
            domain = _strip_pii_from_domain({
                "job_id": job_id,
                "match_score": match_score,
                "decision": decision,
                "needs_human_review": needs_human_review,
            })
            if dimension_scores:
                domain["dimension_scores"] = dimension_scores
            if reason_codes:
                domain["reason_codes"] = reason_codes
            await emitter.emit(
                event_type=BusinessEventType.SCREENING_COMPLETED,
                entity_type="candidate",
                entity_id=candidate_id,
                domain_fields=domain,
                tags=["screening"],
            )
        except Exception as exc:
            logger.warning("on_screening_completed failed (non-blocking): %s", exc)

    @staticmethod
    async def on_jd_generated(
        job_id: str,
        iteration_count: int = 1,
        final_score: float = 0.0,
        passed_threshold: bool = False,
        error: str = "",
    ) -> None:
        """JD 生成完成/失败时调用。"""
        try:
            emitter = get_event_emitter()
            etype = (BusinessEventType.JD_GENERATION_FAILED if error
                     else BusinessEventType.JD_GENERATION_COMPLETED)
            await emitter.emit(
                event_type=etype,
                entity_type="job",
                entity_id=job_id,
                domain_fields={
                    "iteration_count": iteration_count,
                    "final_score": final_score,
                    "passed_threshold": passed_threshold,
                },
                error=error,
                tags=["jd"],
            )
        except Exception as exc:
            logger.warning("on_jd_generated failed (non-blocking): %s", exc)

    @staticmethod
    async def on_interview_scheduled(
        candidate_id: str,
        job_id: str,
        schedule_success: bool,
        conflict_detected: bool = False,
        error: str = "",
    ) -> None:
        """面试安排完成/失败时调用。"""
        try:
            emitter = get_event_emitter()
            await emitter.emit(
                event_type=BusinessEventType.INTERVIEW_SCHEDULED,
                entity_type="candidate",
                entity_id=candidate_id,
                domain_fields={
                    "job_id": job_id,
                    "schedule_success": schedule_success,
                    "conflict_detected": conflict_detected,
                },
                error=error,
                tags=["interview"],
            )
        except Exception as exc:
            logger.warning("on_interview_scheduled failed (non-blocking): %s", exc)

    @staticmethod
    async def on_evaluation_completed(
        experiment_id: str,
        run_id: str,
        evaluator_name: str,
        score: float,
        comment: str = "",
        metadata: dict | None = None,
    ) -> None:
        """评估器执行完成时调用。

        entity_id 使用 experiment_id（有意义的业务标识符）。
        """
        try:
            emitter = get_event_emitter()
            await emitter.emit(
                event_type=BusinessEventType.EVALUATION_COMPLETED,
                entity_type="experiment",
                entity_id=experiment_id,
                domain_fields={
                    "run_id": run_id,
                    "evaluator": evaluator_name,
                    "score": score,
                    "comment": comment,
                    **(metadata or {}),
                },
                tags=["evaluation"],
            )
        except Exception as exc:
            logger.warning("on_evaluation_completed failed (non-blocking): %s", exc)
