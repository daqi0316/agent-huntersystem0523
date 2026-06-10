"""P2-2: 公司专属招聘知识库 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, ok_list, success
from app.schemas.company_knowledge import (
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
)
from app.services.company_knowledge import CompanyKnowledgeService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _item_dict(item) -> dict:
    return {
        "id": item.id,
        "org_id": item.org_id,
        "job_profile_id": item.job_profile_id,
        "knowledge_type": item.knowledge_type.value if hasattr(item.knowledge_type, "value") else item.knowledge_type,
        "status": item.status.value if hasattr(item.status, "value") else item.status,
        "title": item.title,
        "content": item.content,
        "source": item.source,
        "confidence": item.confidence,
        "effective_from": item.effective_from.isoformat() if item.effective_from else None,
        "effective_to": item.effective_to.isoformat() if item.effective_to else None,
        "tags": item.tags or [],
        "embedding_id": item.embedding_id,
        "version": item.version,
        "auto_generated": item.auto_generated,
        "created_by": item.created_by,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.post("/items", status_code=201)
async def create_knowledge_item(data: KnowledgeItemCreate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        item = await CompanyKnowledgeService(db).create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(_item_dict(item))


@router.get("/items")
async def list_knowledge_items(
    org_id: str = Query(..., min_length=1),
    knowledge_type: str | None = Query(None),
    status: str | None = Query(None),
    job_profile_id: str | None = Query(None),
    only_active: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    od=ORG_SCOPED_DEP,
):
    _, db = od
    items, total = await CompanyKnowledgeService(db).list(
        org_id=org_id,
        knowledge_type=knowledge_type,
        status=status,
        job_profile_id=job_profile_id,
        only_active=only_active,
        skip=skip,
        limit=limit,
    )
    return ok_list([_item_dict(i) for i in items], total, skip, limit)


@router.get("/items/{item_id}")
async def get_knowledge_item(item_id: str, od=ORG_SCOPED_DEP):
    _, db = od
    item = await CompanyKnowledgeService(db).get(item_id)
    if item is None:
        return error("知识条目不存在", status_code=404)
    return success(_item_dict(item))


@router.put("/items/{item_id}")
async def update_knowledge_item(item_id: str, data: KnowledgeItemUpdate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        item = await CompanyKnowledgeService(db).update(item_id, data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    if item is None:
        return error("知识条目不存在", status_code=404)
    return success(_item_dict(item))


@router.delete("/items/{item_id}")
async def delete_knowledge_item(item_id: str, od=ORG_SCOPED_DEP):
    _, db = od
    deleted = await CompanyKnowledgeService(db).delete(item_id)
    if not deleted:
        return error("知识条目不存在", status_code=404)
    return success(True)


@router.post("/items/{item_id}/activate")
async def activate_knowledge_item(item_id: str, reviewed_by: str = Query(...), od=ORG_SCOPED_DEP):
    _, db = od
    item = await CompanyKnowledgeService(db).activate(item_id, reviewed_by)
    if item is None:
        return error("知识条目不存在", status_code=404)
    return success(_item_dict(item))


@router.post("/expire-old")
async def expire_old_knowledge(od=ORG_SCOPED_DEP):
    _, db = od
    count = await CompanyKnowledgeService(db).expire_old_items()
    return success({"expired_count": count})


@router.get("/active-for-ai")
async def get_active_knowledge_for_ai(org_id: str = Query(...), od=ORG_SCOPED_DEP):
    _, db = od
    items = await CompanyKnowledgeService(db).get_active_for_ai(org_id)
    return success([_item_dict(i) for i in items])
