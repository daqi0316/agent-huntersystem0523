"""Gen-Eval 循环 API — JD 生成、迭代优化。"""

from fastapi import APIRouter

from app.schemas.jd_generator import (
    JDGenerateRequest,
    JDGenerateResponse,
    JDImproveRequest,
    JDImproveResponse,
)
from app.services.jd_generator import JDGeneratorService

router = APIRouter()
service = JDGeneratorService()


@router.post("/jd-generate", response_model=JDGenerateResponse)
async def generate_jd(req: JDGenerateRequest):
    """图6 Gen-Eval: 生成 JD，支持多轮迭代优化。"""
    result = await service.generate_jd(
        title=req.title,
        requirements=req.requirements,
        preferences=req.preferences or "",
        auto_improve=req.auto_improve,
    )
    return JDGenerateResponse(
        success=True,
        data=result["final_output"],
        iterations=result["iterations"],
        total_iterations=result["total_iterations"],
        passed=result["passed"],
    )


@router.post("/jd-improve", response_model=JDImproveResponse)
async def improve_jd(req: JDImproveRequest):
    """根据反馈改进已有 JD。"""
    result = await service.improve_jd(
        jd_content=req.jd_content,
        feedback=req.feedback,
    )
    return JDImproveResponse(
        success=True,
        jd_content=result["jd_content"],
        original=result["original"],
    )
