"""图4: Aggregator API — 多维度并行评估 + 数据聚合。"""

from fastapi import APIRouter

from app.core.response import error, success
from app.schemas.screening import MultiEvaluateRequest, MultiEvaluateResponse
from app.services.screening import ScreeningService

router = APIRouter()
service = ScreeningService()


@router.post("/multi-evaluate", response_model=MultiEvaluateResponse)
async def multi_evaluate(req: MultiEvaluateRequest):
    """图4 Aggregator: 多维度并行评估候选人。"""
    result = await service.multi_evaluate(
        candidate_info=req.candidate_info,
        dimensions=req.dimensions,
    )
    return MultiEvaluateResponse(
        success=True,
        dimension_results=result.get("dimension_results", []),
        consensus=result.get("consensus", {}),
        total_dimensions=result.get("total_dimensions", 0),
    )


@router.post("/data-aggregate")
async def data_aggregate(body: dict):
    """图4: 数据聚合 — 聚合多维度评估分数。

    输入: {"dimension_results": [{"name": "专业技能", "score": 85}, ...]}
    输出: {
        "success": true,
        "data": {
            "average_score": 78.5,
            "max_score": 95,
            "min_score": 60,
            "dimensions": {"专业技能": 85, ...},
            "distribution": {"90-100": 1, "80-89": 2, ...},
            "total_dimensions": 8,
        }
    }
    """
    dimension_results = body.get("dimension_results", [])
    if not dimension_results:
        return error("dimension_results 为必填")

    scores = {}
    total = 0
    count = 0

    for dim in dimension_results:
        name = dim.get("name", "")
        score = dim.get("score", 0)
        if name:
            scores[name] = score
            total += score
            count += 1

    if count == 0:
        return error("无可聚合的维度数据")

    avg = total / count
    max_score = max(scores.values())
    min_score = min(scores.values())

    # Distribution
    distribution = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
    for s in scores.values():
        if s >= 90:
            distribution["90-100"] += 1
        elif s >= 80:
            distribution["80-89"] += 1
        elif s >= 70:
            distribution["70-79"] += 1
        elif s >= 60:
            distribution["60-69"] += 1
        else:
            distribution["<60"] += 1

    return success({
        "average_score": round(avg, 1),
        "max_score": max_score,
        "min_score": min_score,
        "dimensions": scores,
        "distribution": distribution,
        "total_dimensions": count,
    })
