"""Screening Agent API — 统一初筛入口。

POST   /screen         单候选人初筛
POST   /screen/batch   批量候选人初筛对比
GET    /screen/{candidate_id}/result  查询初筛结果
POST   /screen/evaluate  多维度并行评估
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user_id
from app.services.screening import ScreeningService

router = APIRouter()


class ScreenRequest(BaseModel):
    candidate_id: str = Field(..., description="候选人 ID")
    job_id: str = Field(..., description="职位 ID")
    resume_text: str = Field(..., description="简历文本")
    job_requirements: str = Field(..., description="职位要求")


class BatchScreenRequest(BaseModel):
    candidates: list[dict] = Field(..., description="候选人列表，每项含 candidate_id/job_id/resume_text/job_requirements")


class EvaluateRequest(BaseModel):
    candidate_info: str = Field(..., description="候选人信息")
    dimensions: list[str] | None = Field(None, description="评估维度列表，默认全 6 维")


@router.post("")
async def screen_candidate(
    req: ScreenRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """单候选人 AI 初筛。"""
    service = ScreeningService()
    result = await service.screen(
        candidate_id=req.candidate_id,
        job_id=req.job_id,
        resume_text=req.resume_text,
        job_requirements=req.job_requirements,
    )
    return {"success": True, "data": result}


@router.post("/batch")
async def batch_screen(
    req: BatchScreenRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """批量候选人初筛对比。"""
    agent = ScreeningService().screening_agent
    result = await agent.batch_screen(req.candidates)
    return {"success": True, "data": result}


@router.get("/{candidate_id}/result")
async def get_screen_result(
    candidate_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """查询候选人的初筛结果（stub — 需结合 DB 实现）。"""
    return {
        "success": True,
        "data": {
            "candidate_id": candidate_id,
            "message": "完整初筛结果查询需要 DB 集成",
        },
    }


@router.post("/evaluate")
async def evaluate_candidate(
    req: EvaluateRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """6 维度并行评估。"""
    agent = ScreeningService().screening_agent
    result = await agent.multi_evaluate(
        candidate_info=req.candidate_info,
        dimensions=req.dimensions,
    )
    return {"success": True, "data": result}
