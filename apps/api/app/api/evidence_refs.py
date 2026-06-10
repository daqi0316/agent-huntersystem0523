"""统一证据协议 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, ok_list, success
from app.schemas.evidence_ref import EvidenceRefCreate
from app.services.evidence_ref import EvidenceRefService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _ref_dict(r) -> dict:
    return {
        "id": r.id,
        "candidate_id": r.candidate_id,
        "application_id": r.application_id,
        "source_type": r.source_type.value if hasattr(r.source_type, "value") else r.source_type,
        "source_id": r.source_id,
        "quote": r.quote,
        "normalized_claim": r.normalized_claim,
        "confidence": r.confidence,
        "created_by_type": r.created_by_type.value if hasattr(r.created_by_type, "value") else r.created_by_type,
        "created_by_id": r.created_by_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("", status_code=201)
async def create_evidence_ref(data: EvidenceRefCreate, od=ORG_SCOPED_DEP):
    """创建证据引用。"""
    _, db = od
    try:
        ref = await EvidenceRefService(db).create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(_ref_dict(ref))


@router.get("")
async def list_evidence_refs(
    candidate_id: str | None = Query(None),
    application_id: str | None = Query(None),
    source_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    od=ORG_SCOPED_DEP,
):
    """查询证据引用列表。"""
    _, db = od
    items, total = await EvidenceRefService(db).list(
        candidate_id=candidate_id,
        application_id=application_id,
        source_type=source_type,
        skip=skip,
        limit=limit,
    )
    return ok_list([_ref_dict(i) for i in items], total, skip, limit)


@router.get("/{ref_id}")
async def get_evidence_ref(ref_id: str, od=ORG_SCOPED_DEP):
    """获取单个证据引用。"""
    _, db = od
    ref = await EvidenceRefService(db).get(ref_id)
    if ref is None:
        return error("证据不存在", status_code=404)
    return success(_ref_dict(ref))


@router.delete("/{ref_id}")
async def delete_evidence_ref(ref_id: str, od=ORG_SCOPED_DEP):
    """删除证据引用。"""
    _, db = od
    deleted = await EvidenceRefService(db).delete(ref_id)
    if not deleted:
        return error("证据不存在", status_code=404)
    return success(True)


@router.delete("/by-candidate/{candidate_id}")
async def delete_evidence_refs_by_candidate(candidate_id: str, od=ORG_SCOPED_DEP):
    """删除候选人的所有证据引用。"""
    _, db = od
    count = await EvidenceRefService(db).delete_by_candidate(candidate_id)
    return success({"deleted": count})
