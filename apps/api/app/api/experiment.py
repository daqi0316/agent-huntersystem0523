"""P6-7: A/B 测试 API — experiments CRUD + 分配 + 事件 + 显著性分析。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentEvent,
    ExperimentEvent_,
    ExperimentStatus,
    assign_variant,
    z_test_two_proportions,
)

router = APIRouter()


class CreateExperimentRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = Field(None, max_length=512)
    variants: list[dict] = Field(..., min_items=2, max_items=4)
    primary_metric: str = Field("conversion", max_length=64)
    target_url: Optional[str] = Field(None, max_length=512)


class RecordEventRequest(BaseModel):
    experiment_name: str = Field(..., max_length=64)
    event: str = Field(..., pattern=r"^(impression|conversion)$")
    meta: dict = Field(default_factory=dict)


def _serialize_experiment(e: Experiment) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "description": e.description,
        "status": e.status.value,
        "variants": e.variants,
        "primary_metric": e.primary_metric,
        "target_url": e.target_url,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "stopped_at": e.stopped_at.isoformat() if e.stopped_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.post("/experiments", status_code=201)
async def create_experiment(
    body: CreateExperimentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """admin: 创建 A/B 实验。"""
    total_pct = sum(int(v.get("traffic_pct", 0)) for v in body.variants)
    if total_pct > 100:
        raise HTTPException(400, f"variants total traffic_pct ({total_pct}) > 100")
    for v in body.variants:
        if "name" not in v or "traffic_pct" not in v:
            raise HTTPException(400, "each variant needs name + traffic_pct")

    exp = Experiment(
        name=body.name,
        description=body.description,
        variants=body.variants,
        primary_metric=body.primary_metric,
        target_url=body.target_url,
        status=ExperimentStatus.DRAFT,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return success(_serialize_experiment(exp))


@router.get("/experiments")
async def list_experiments(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    q = select(Experiment).order_by(Experiment.created_at.desc())
    if status_filter:
        try:
            q = q.where(Experiment.status == ExperimentStatus(status_filter))
        except ValueError:
            raise HTTPException(400, f"invalid status: {status_filter}")
    rows = (await db.execute(q)).scalars().all()
    return success([_serialize_experiment(r) for r in rows])


@router.get("/experiments/{name}/assign")
async def get_assignment(
    name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Query(..., description="当前 user 唯一标识"),
):
    """user 进入实验页面时调, 返分配的 variant config。"""
    exp = (await db.execute(
        select(Experiment).where(Experiment.name == name)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(404, "experiment not found")
    if exp.status != ExperimentStatus.RUNNING:
        raise HTTPException(400, f"experiment status: {exp.status.value}")

    existing = (await db.execute(
        select(ExperimentAssignment).where(
            ExperimentAssignment.experiment_id == exp.id,
            ExperimentAssignment.user_id == user_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        variant = existing.variant
    else:
        variant = assign_variant(user_id, exp.name, exp.variants)
        if variant is None:
            return success({"experiment": name, "variant": None, "in_experiment": False})
        assign = ExperimentAssignment(
            experiment_id=exp.id,
            user_id=user_id,
            variant=variant,
        )
        db.add(assign)
        await db.commit()

    config = next((v.get("config", {}) for v in exp.variants if v.get("name") == variant), {})
    return success({
        "experiment": exp.name,
        "variant": variant,
        "in_experiment": True,
        "config": config,
    })


@router.post("/experiments/events")
async def record_experiment_event(
    body: RecordEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Query(..., description="当前 user"),
):
    """前端埋点: impression / conversion。"""
    exp = (await db.execute(
        select(Experiment).where(Experiment.name == body.experiment_name)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(404, "experiment not found")
    if exp.status != ExperimentStatus.RUNNING:
        raise HTTPException(400, f"experiment not running: {exp.status.value}")

    assignment = (await db.execute(
        select(ExperimentAssignment).where(
            ExperimentAssignment.experiment_id == exp.id,
            ExperimentAssignment.user_id == user_id,
        )
    )).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(400, "user not assigned to this experiment, call /assign first")
    variant = assignment.variant

    event = ExperimentEvent_(
        experiment_id=exp.id,
        user_id=user_id,
        variant=variant,
        event=body.event,
        meta=body.meta,
    )
    db.add(event)
    await db.commit()
    return success({
        "experiment": exp.name,
        "variant": variant,
        "event": body.event,
        "recorded": True,
    })


@router.get("/experiments/{name}/results")
async def get_experiment_results(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """admin: 实验结果 + 显著性分析。"""
    exp = (await db.execute(
        select(Experiment).where(Experiment.name == name)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(404, "experiment not found")

    events = (await db.execute(
        select(ExperimentEvent_).where(ExperimentEvent_.experiment_id == exp.id)
    )).scalars().all()

    by_variant: dict = {}
    for ev in events:
        v = ev.variant
        by_variant.setdefault(v, {"impression": 0, "conversion": 0, "users": set()})
        by_variant[v][ev.event] += 1
        by_variant[v]["users"].add(ev.user_id)

    results = []
    for v_name, counts in by_variant.items():
        impressions = counts["impression"]
        conversions = counts["conversion"]
        unique_users = len(counts["users"])
        cvr = conversions / max(impressions, 1) * 100
        results.append({
            "variant": v_name,
            "impressions": impressions,
            "conversions": conversions,
            "unique_users": unique_users,
            "conversion_rate_pct": round(cvr, 2),
        })

    significance = None
    if len(results) >= 2:
        baseline = results[0]
        for r in results[1:]:
            z, p = z_test_two_proportions(
                baseline["conversions"], baseline["impressions"],
                r["conversions"], r["impressions"],
            )
            r["vs_baseline"] = {
                "z_score": round(z, 3),
                "p_value": round(p, 4),
                "significant": p < 0.05,
            }

    return success({
        "experiment": _serialize_experiment(exp),
        "results": results,
        "min_sample_size_reached": all(r["impressions"] >= 30 for r in results) if results else False,
    })


@router.post("/experiments/{name}/start")
async def start_experiment(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    exp = (await db.execute(
        select(Experiment).where(Experiment.name == name)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(404, "experiment not found")
    if exp.status != ExperimentStatus.DRAFT:
        raise HTTPException(400, f"can only start from DRAFT, got {exp.status.value}")
    exp.status = ExperimentStatus.RUNNING
    exp.started_at = datetime.now(timezone.utc)
    await db.commit()
    return success(_serialize_experiment(exp))


@router.post("/experiments/{name}/stop")
async def stop_experiment(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    exp = (await db.execute(
        select(Experiment).where(Experiment.name == name)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(404, "experiment not found")
    exp.status = ExperimentStatus.COMPLETED
    exp.stopped_at = datetime.now(timezone.utc)
    await db.commit()
    return success(_serialize_experiment(exp))
