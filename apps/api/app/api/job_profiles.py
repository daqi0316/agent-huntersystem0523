from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.schemas.common import ListResponse
from app.schemas.job_profile import JobProfileCreate, JobProfileRead, JobProfileUpdate, JobProfileVersionCreate
from app.services.job_profile import JobProfileService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


@router.get("", response_model=ListResponse[JobProfileRead])
async def list_job_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    level: str | None = None,
    is_active: bool | None = None,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    service = JobProfileService(db)
    items, total = await service.list(
        skip=skip,
        limit=limit,
        search=search,
        level=level,
        is_active=is_active,
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/code/{code}")
async def get_job_profile_by_code(code: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    profile = await JobProfileService(db).get_by_code(code)
    if profile is None:
        return error("岗位画像不存在", status_code=404)
    return success(profile)


@router.get("/templates/library")
async def list_job_profile_templates(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    return success(await JobProfileService(db).template_library())


@router.get("/{profile_id}")
async def get_job_profile(profile_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    profile = await JobProfileService(db).get_by_id(profile_id)
    if profile is None:
        return error("岗位画像不存在", status_code=404)
    return success(profile)


@router.post("", status_code=201)
async def create_job_profile(data: JobProfileCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = JobProfileService(db)
    existing = await service.get_by_code(data.code)
    if existing is not None:
        return error("岗位画像 code 已存在", status_code=409)
    return success(await service.create(data))


@router.put("/{profile_id}")
async def update_job_profile(
    profile_id: str,
    data: JobProfileUpdate,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    profile = await JobProfileService(db).update(profile_id, data)
    if profile is None:
        return error("岗位画像不存在", status_code=404)
    return success(profile)


@router.get("/{profile_id}/versions")
async def list_job_profile_versions(profile_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    profile = await JobProfileService(db).get_by_id(profile_id)
    if profile is None:
        return error("岗位画像不存在", status_code=404)
    return success(await JobProfileService(db).list_versions(profile_id))


@router.post("/{profile_id}/versions", status_code=201)
async def create_job_profile_version(
    profile_id: str,
    data: JobProfileVersionCreate,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    try:
        version = await JobProfileService(db).create_version(profile_id, data, created_by=org_ctx.user_id)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    if version is None:
        return error("岗位画像不存在", status_code=404)
    return success(await JobProfileService(db).version_to_dict(version))


@router.post("/{profile_id}/versions/{version_id}/activate")
async def activate_job_profile_version(profile_id: str, version_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    version = await JobProfileService(db).activate_version(profile_id, version_id, activated_by=org_ctx.user_id)
    if version is None:
        return error("岗位画像版本不存在", status_code=404)
    return success(await JobProfileService(db).version_to_dict(version))
