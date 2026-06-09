from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.schemas.common import ListResponse
from app.schemas.scorecard import (
    InterviewScorecardSubmissionCreate,
    ScorecardFromJobProfileRequest,
    ScorecardTemplateCreate,
)
from app.services.scorecard import ScorecardService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


@router.get("/templates", response_model=ListResponse)
async def list_scorecard_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    job_profile_id: str | None = None,
    round_type: str | None = None,
    status: str | None = None,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    items, total = await ScorecardService(db).list_templates(
        skip=skip,
        limit=limit,
        job_profile_id=job_profile_id,
        round_type=round_type,
        status=status,
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/templates", status_code=201)
async def create_scorecard_template(data: ScorecardTemplateCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    try:
        template = await ScorecardService(db).create_template(data, created_by=org_ctx.user_id)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(await ScorecardService(db).to_template_dict(template))


@router.get("/templates/{template_id}")
async def get_scorecard_template(template_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = ScorecardService(db)
    template = await service.get_template(template_id)
    if template is None:
        return error("评分卡模板不存在", status_code=404)
    return success(await service.to_template_dict(template))


@router.post("/templates/from-job-profile/{profile_id}", status_code=201)
async def create_scorecard_from_job_profile(
    profile_id: str,
    data: ScorecardFromJobProfileRequest,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    try:
        template = await ScorecardService(db).create_from_job_profile(
            profile_id=profile_id,
            round_type=data.round_type,
            name=data.name,
            status=data.status,
            created_by=org_ctx.user_id,
        )
    except ValueError as exc:
        return error(str(exc), status_code=400)
    if template is None:
        return error("岗位画像不存在或缺少考察维度", status_code=404)
    return success(await ScorecardService(db).to_template_dict(template))


@router.get("/interviews/{interview_id}/scorecard")
async def get_interview_scorecard(interview_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    template = await ScorecardService(db).get_template_for_interview(interview_id)
    if template is None:
        return error("面试不存在或暂无可用评分卡", status_code=404)
    return success(template)


@router.post("/interviews/{interview_id}/submissions", status_code=201)
async def submit_interview_scorecard(
    interview_id: str,
    data: InterviewScorecardSubmissionCreate,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    service = ScorecardService(db)
    try:
        submission = await service.submit_for_interview(interview_id, data, interviewer_id=org_ctx.user_id)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    if submission is None:
        return error("面试不存在", status_code=404)
    return success(await service.to_submission_dict(submission))


@router.get("/candidates/{candidate_id}/submissions")
async def list_candidate_scorecard_submissions(candidate_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await ScorecardService(db).list_submissions_for_candidate(candidate_id))
