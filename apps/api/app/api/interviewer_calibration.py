"""面试官校准 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, ok_list, success
from app.schemas.interviewer_calibration import CalibrationMetricComputeRequest
from app.services.interviewer_calibration import InterviewerCalibrationService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _metric_dict(m) -> dict:
    return {
        "id": m.id,
        "interviewer_id": m.interviewer_id,
        "period_start": m.period_start.isoformat() if m.period_start else None,
        "period_end": m.period_end.isoformat() if m.period_end else None,
        "sample_size": m.sample_size,
        "avg_score": m.avg_score,
        "score_stddev": m.score_stddev,
        "severity_bias": m.severity_bias,
        "correlation_with_probation": m.correlation_with_probation,
        "false_positive_rate": m.false_positive_rate,
        "false_negative_rate": m.false_negative_rate,
        "strict_rate": m.strict_rate,
        "lenient_rate": m.lenient_rate,
        "pass_rate": m.pass_rate,
        "computed_at": m.computed_at.isoformat() if m.computed_at else None,
    }


@router.post("/calibration/compute")
async def compute_calibration(
    data: CalibrationMetricComputeRequest | None = None,
    od=ORG_SCOPED_DEP,
):
    """计算面试官校准指标（可指定面试官和时间范围）。"""
    _, db = od
    req = data or CalibrationMetricComputeRequest()
    try:
        metrics = await InterviewerCalibrationService(db).compute(
            interviewer_id=req.interviewer_id,
            period_start=req.period_start,
            period_end=req.period_end,
        )
    except Exception as exc:
        return error(str(exc), status_code=500)
    return success([_metric_dict(m) for m in metrics])


@router.get("/calibration/metrics")
async def list_calibration_metrics(
    interviewer_id: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    od=ORG_SCOPED_DEP,
):
    """查询面试官校准指标列表。"""
    _, db = od
    items, total = await InterviewerCalibrationService(db).list(
        interviewer_id=interviewer_id, skip=skip, limit=limit,
    )
    return ok_list([_metric_dict(i) for i in items], total, skip, limit)


@router.get("/calibration/metrics/{interviewer_id}")
async def get_latest_calibration(interviewer_id: str, od=ORG_SCOPED_DEP):
    """获取某个面试官的最新校准指标。"""
    _, db = od
    metric = await InterviewerCalibrationService(db).get_latest(interviewer_id)
    if metric is None:
        return error("暂无数据", status_code=404)
    return success(_metric_dict(metric))
