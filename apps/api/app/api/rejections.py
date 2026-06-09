from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.schemas.common import ListResponse
from app.schemas.rejection import (
    CandidateRejectionRecordRead,
    CandidateRejectRequest,
    RejectionReasonCreate,
    RejectionReasonRead,
)
from app.services.rejection import RejectionService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


@router.get("/reasons", response_model=ListResponse[RejectionReasonRead])
async def list_rejection_reasons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: str | None = None,
    is_active: bool | None = True,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    items, total = await RejectionService(db).list_reasons(
        skip=skip, limit=limit, category=category, is_active=is_active
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/reasons", status_code=201)
async def create_rejection_reason(data: RejectionReasonCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = RejectionService(db)
    existing = await service.get_reason_by_code(data.code)
    if existing is not None:
        return error("淘汰原因 code 已存在", status_code=409)
    return success(await service.create_reason(data))


@router.get(
    "/candidates/{candidate_id}/records",
    response_model=ListResponse[CandidateRejectionRecordRead],
)
async def list_candidate_rejection_records(candidate_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    items = await RejectionService(db).list_candidate_records(candidate_id)
    return ListResponse(items=items, total=len(items), skip=0, limit=len(items))


@router.post("/candidates/{candidate_id}/reject", status_code=201)
async def reject_candidate(
    candidate_id: str,
    data: CandidateRejectRequest,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    try:
        record = await RejectionService(db).reject_candidate(
            candidate_id=candidate_id,
            data=data,
            operator_id=org_ctx.user_id,
        )
    except LookupError as exc:
        return error(str(exc), status_code=404)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(record)


@router.get("/analytics/distribution")
async def rejection_distribution(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await RejectionService(db).analytics())


@router.get("/analytics/by-job-profile")
async def rejection_by_job_profile(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await RejectionService(db).analytics_by_job_profile())


@router.get("/analytics/by-stage")
async def rejection_by_stage(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await RejectionService(db).analytics_by_stage())


@router.get("/analytics/by-reason")
async def rejection_by_reason(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await RejectionService(db).analytics_by_reason())


@router.get("/analytics/preventable")
async def rejection_preventable(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await RejectionService(db).analytics_preventable())
