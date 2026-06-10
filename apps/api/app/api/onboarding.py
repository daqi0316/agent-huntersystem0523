"""P5-15: 客户 onboarding runbook API — 批量导入 + 健康度查询。"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.onboarding import BatchImportRequest
from app.services.onboarding import (
    compute_health_score,
    get_health_score,
    import_candidates_csv,
    import_jobs_csv,
    list_all_health_scores,
    list_imports,
)

router = APIRouter()


CANDIDATE_CSV_TEMPLATE = "name,email,phone,location,source\n张三,zhang@x.com,13800138000,北京,linkedin\n李四,li@x.com,,上海,referral\n"
JOB_CSV_TEMPLATE = "title,department,location,description,requirements\n高级 Python 工程师,工程,北京,负责核心服务,5 年 Python 经验\n"


@router.get("/onboarding/csv-template/{entity_type}")
async def get_csv_template(entity_type: str):
    if entity_type == "candidate":
        return success({
            "entity_type": "candidate",
            "required_columns": ["name", "email"],
            "optional_columns": ["phone", "location", "source"],
            "template": CANDIDATE_CSV_TEMPLATE,
        })
    if entity_type == "job_position":
        return success({
            "entity_type": "job_position",
            "required_columns": ["title"],
            "optional_columns": ["department", "location", "description", "requirements"],
            "template": JOB_CSV_TEMPLATE,
        })
    raise HTTPException(400, f"unknown entity_type: {entity_type}")


@router.post("/onboarding/import/candidates")
async def import_candidates(
    file: UploadFile = File(..., description="CSV file"),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("gbk", errors="ignore")
    batch, result = await import_candidates_csv(db, org_ctx.org_id, org_ctx.user_id, csv_text)
    return success({
        "batch_id": batch.id,
        "status": batch.status.value,
        "total": result.total,
        "imported": result.imported,
        "failed": result.failed,
        "errors": result.errors[:10],
    })


@router.post("/onboarding/import/jobs")
async def import_jobs(
    file: UploadFile = File(..., description="CSV file"),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("gbk", errors="ignore")
    batch, result = await import_jobs_csv(db, org_ctx.org_id, org_ctx.user_id, csv_text)
    return success({
        "batch_id": batch.id,
        "status": batch.status.value,
        "total": result.total,
        "imported": result.imported,
        "failed": result.failed,
        "errors": result.errors[:10],
    })


@router.get("/onboarding/imports")
async def import_history(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
    limit: int = Query(50, ge=1, le=200),
):
    org_ctx, db = ctx
    rows = await list_imports(db, org_ctx.org_id, limit)
    return success([
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "status": r.status.value,
            "file_name": r.file_name,
            "total": r.total_rows,
            "imported": r.imported_rows,
            "failed": r.failed_rows,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ])


@router.get("/onboarding/import/{batch_id}")
async def get_import_status(
    batch_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    batch = (await db.execute(
        __import__("sqlalchemy").select(BatchImportRequest).where(
            BatchImportRequest.id == batch_id,
            BatchImportRequest.org_id == org_ctx.org_id,
        )
    )).scalar_one_or_none()
    if batch is None:
        raise HTTPException(404, "batch not found")
    return success({
        "id": batch.id,
        "entity_type": batch.entity_type,
        "status": batch.status.value,
        "total": batch.total_rows,
        "imported": batch.imported_rows,
        "failed": batch.failed_rows,
        "errors": batch.errors[:10],
        "started_at": batch.started_at.isoformat() if batch.started_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
    })


@router.get("/onboarding/health-score")
async def my_health_score(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    score = await get_health_score(db, org_ctx.org_id)
    if score is None:
        score = await compute_health_score(db, org_ctx.org_id)
    return success({
        "org_id": score.org_id,
        "total_score": score.total_score,
        "risk_level": score.risk_level,
        "breakdown": {
            "login": score.login_score,
            "feature": score.feature_score,
            "support": score.support_score,
            "referral": score.referral_score,
        },
        "metrics": score.metrics_snapshot,
        "computed_at": score.computed_at.isoformat(),
    })


@router.post("/onboarding/health-score/refresh")
async def refresh_health_score(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    score = await compute_health_score(db, org_ctx.org_id)
    return success({
        "org_id": score.org_id,
        "total_score": score.total_score,
        "risk_level": score.risk_level,
    })


@router.get("/onboarding/health-scores/all")
async def all_health_scores(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    rows = await list_all_health_scores(db)
    return success([
        {
            "org_id": r.org_id,
            "total_score": r.total_score,
            "risk_level": r.risk_level,
            "computed_at": r.computed_at.isoformat(),
        }
        for r in rows[:limit]
    ])
