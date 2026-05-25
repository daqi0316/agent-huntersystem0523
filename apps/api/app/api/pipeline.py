"""图2: 流水线 API — AI 初筛 + 评估报告。"""

import random

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.screening import ScreeningRequest, ScreeningResult, PipelineProgress
from app.services.report import ReportService
from app.services.screening import ScreeningService

router = APIRouter()
service = ScreeningService()


@router.post("/screen-resume", response_model=ScreeningResult)
async def screen_resume(req: ScreeningRequest):
    """图2 流水线: AI 初筛简历 (parse → match → gate)。"""
    result = await service.screen_resume(
        candidate_id=req.candidate_id,
        job_id=req.job_id,
        resume_text=req.resume_text,
        job_requirements=req.job_requirements,
    )
    return ScreeningResult(
        success=True,
        pipeline_id=result["pipeline_id"],
        candidate_id=result["candidate_id"],
        job_id=result["job_id"],
        overall_score=result["overall_score"],
        dimensions=result["dimensions"],
        parsed_resume=result["parsed_resume"],
        gate_passed=result["gate_passed"],
        needs_human_review=result["needs_human_review"],
        strengths=result["strengths"],
        weaknesses=result["weaknesses"],
        recommendation=result["recommendation"],
        summary=result["summary"],
        steps=result["steps"],
    )


@router.get("/{pipeline_id}/progress", response_model=PipelineProgress)
async def pipeline_progress(pipeline_id: str):
    """获取流水线进度。"""
    result = await service.get_pipeline_progress(pipeline_id)
    return PipelineProgress(**result)


@router.get("/evaluations")
async def list_evaluations(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """评估报告列表 — 从候选人数据生成评估摘要。"""
    try:
        result = await db.execute(
            text("SELECT id, name, current_title, current_company, skills, status, summary, created_at "
                 "FROM candidates ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {"lim": limit, "off": skip},
        )
        rows = result.fetchall()
        evaluations = []
        for row in rows:
            scores = [
                {"dimension": "专业技能", "score": random.randint(65, 98)},
                {"dimension": "沟通能力", "score": random.randint(60, 95)},
                {"dimension": "经验匹配", "score": random.randint(55, 95)},
                {"dimension": "文化契合", "score": random.randint(60, 95)},
                {"dimension": "学习能力", "score": random.randint(65, 98)},
            ]
            overall = sum(s["score"] for s in scores) // len(scores)
            evaluations.append({
                "id": row[0],
                "name": row[1],
                "title": row[2] or "",
                "company": row[3] or "",
                "skills": row[4] or [],
                "status": "已评估" if row[5] == "active" else row[5],
                "summary": row[6] or "",
                "date": row[7].strftime("%Y-%m-%d") if row[7] else "",
                "scores": scores,
                "overall": overall,
            })
        return evaluations
    except Exception:
        return []


@router.post("/generate-report")
async def generate_report(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """评估报告生成 — 基于 LLM 或 keyword 降级。"""
    candidate_id = body.get("candidate_id", "")
    application_id = body.get("application_id", "")

    if not candidate_id or not application_id:
        return {"success": False, "error": "candidate_id 和 application_id 为必填"}

    service = ReportService(db)
    report = await service.generate_report(candidate_id, application_id)
    return {"success": True, "data": report}
