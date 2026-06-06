"""Evaluation tools — save feedback, generate report."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.core.database import AsyncSessionLocal, AsyncSession
from app.models.interview_evaluation import InterviewEvaluation, InterviewRound, EvaluationVerdict

logger = logging.getLogger(__name__)


async def _handle_save_evaluation(
    interview_id: str = "",
    round: str = "R1",
    overall_score: float | None = None,
    verdict: str = "consider",
    dimensions: dict | None = None,
    key_observations: str = "",
    red_flags: str = "",
    feedback: str = "",
) -> dict[str, Any]:
    """保存面试评估结果。v0.3 §7.1 / inventory §4.3 code smell 修：改走 InterviewService.save_evaluation()。"""
    from app.services.interview import InterviewService

    if not interview_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "interview_id 不能为空"}}

    try:
        round_enum = InterviewRound(round)
    except ValueError:
        round_enum = InterviewRound.R1

    try:
        verdict_enum = EvaluationVerdict(verdict)
    except ValueError:
        verdict_enum = EvaluationVerdict.CONSIDER

    async with AsyncSessionLocal() as db:
        svc = InterviewService(db)
        try:
            ev = await svc.save_evaluation(
                interview_id=interview_id,
                round=round_enum,
                overall_score=overall_score,
                verdict=verdict_enum,
                dimensions=dimensions,
                key_observations=key_observations or None,
                red_flags=red_flags or None,
                feedback=feedback or None,
            )
        except ValueError as e:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": str(e)}}

        return {
            "status": "success",
            "data": {
                "evaluation_id": ev.id,
                "interview_id": ev.interview_id,
                "round": ev.round.value if hasattr(ev.round, "value") else str(ev.round),
                "overall_score": ev.overall_score,
                "verdict": ev.verdict.value if hasattr(ev.verdict, "value") else str(ev.verdict),
            },
        }


async def _handle_generate_evaluation_report(candidate_id: str = "") -> dict[str, Any]:
    """生成候选人的面试评估汇总报告（汇总所有轮次评估）。"""
    if not candidate_id:
        return {"status": "failed", "error": {"code": "VALIDATION_ERROR", "message": "candidate_id 不能为空"}}

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models.interview import Interview
        from app.models.interview_evaluation import InterviewEvaluation
        from app.services.candidate import CandidateService

        candidate_svc = CandidateService(db)
        candidate = await candidate_svc.get_by_id(candidate_id)
        if not candidate:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}

        result = await db.execute(
            select(Interview).where(Interview.candidate_id == candidate_id)
        )
        interviews = result.scalars().all()
        interview_ids = [iv.id for iv in interviews]

        if not interview_ids:
            return {
                "status": "success",
                "data": {
                    "candidate_id": candidate_id,
                    "candidate_name": candidate.name,
                    "total_interviews": 0,
                    "rounds": [],
                    "average_score": None,
                    "overall_verdict": None,
                    "summary": "暂无面试记录",
                },
            }

        eval_result = await db.execute(
            select(InterviewEvaluation)
            .where(InterviewEvaluation.interview_id.in_(interview_ids))
            .order_by(InterviewEvaluation.created_at.desc())
        )
        evaluations = eval_result.scalars().all()

        rounds = []
        scores = []
        for ev in evaluations:
            rounds.append({
                "interview_id": ev.interview_id,
                "round": ev.round.value if hasattr(ev.round, "value") else str(ev.round),
                "overall_score": ev.overall_score,
                "verdict": ev.verdict.value if hasattr(ev.verdict, "value") else str(ev.verdict),
                "key_observations": ev.key_observations,
                "red_flags": ev.red_flags,
                "feedback": ev.feedback,
                "created_at": str(ev.created_at) if ev.created_at else None,
            })
            if ev.overall_score is not None:
                scores.append(ev.overall_score)

        avg_score = sum(scores) / len(scores) if scores else None
        all_verdicts = [e.verdict for e in evaluations]
        strongest = EvaluationVerdict.STRONG_HIRE if EvaluationVerdict.STRONG_HIRE in all_verdicts else (
            EvaluationVerdict.HIRE if EvaluationVerdict.HIRE in all_verdicts else EvaluationVerdict.CONSIDER
        )

        return {
            "status": "success",
            "data": {
                "candidate_id": candidate_id,
                "candidate_name": candidate.name,
                "total_interviews": len(interviews),
                "total_evaluations": len(evaluations),
                "rounds": rounds,
                "average_score": round(avg_score, 2) if avg_score else None,
                "overall_verdict": strongest.value if hasattr(strongest, "value") else str(strongest),
                "summary": _build_summary(candidate.name, rounds, avg_score, strongest),
            },
        }


def _build_summary(name: str, rounds: list[dict], avg_score: float | None, verdict: EvaluationVerdict) -> str:
    if not rounds:
        return f"候选人 {name} 暂无面试评估记录。"
    verdict_text = {"strong_hire": "强烈建议录用", "hire": "建议录用", "consider": "可以考虑", "pass": "不建议录用"}.get(
        verdict.value if hasattr(verdict, "value") else str(verdict), "待定"
    )
    score_text = f"平均分 {avg_score:.1f}/10" if avg_score else "暂无评分"
    return f"候选人 {name} 共完成 {len(rounds)} 轮面试，{score_text}，综合结论：{verdict_text}。"


tools = [
    {
        "type": "function",
        "function": {
            "name": "save_evaluation",
            "description": "保存面试评估结果，包含评分、结论、维度打分、关键观察和风险标记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "round": {"type": "string", "description": "面试轮次 (R1/R2/R3/R4)"},
                    "overall_score": {"type": "number", "description": "综合评分 0-10"},
                    "verdict": {"type": "string", "description": "录用结论 (strong_hire/hire/consider/pass)"},
                    "dimensions": {"type": "object", "description": "各维度评分 JSON，如 {\"技术\": 8, \"沟通\": 7}"},
                    "key_observations": {"type": "string", "description": "关键观察"},
                    "red_flags": {"type": "string", "description": "风险标记（用逗号分隔）"},
                    "feedback": {"type": "string", "description": "综合反馈"},
                },
                "required": ["interview_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_evaluation_report",
            "description": "为候选人生成面试评估汇总报告，包含所有轮次评分、平均分、综合结论。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "候选人 ID"},
                },
                "required": ["candidate_id"],
            },
        },
    },
]

handlers = {
    "save_evaluation": _handle_save_evaluation,
    "generate_evaluation_report": _handle_generate_evaluation_report,
}
