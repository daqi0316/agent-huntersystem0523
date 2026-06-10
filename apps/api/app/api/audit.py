"""Audit API — 审计日志查询 + AI 决策审计写入。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.response import error, success
from app.models.operation_log import OperationLog, ErrorCategory
from app.models.ai_decision_audit import AiDecisionAudit, AiDecisionType
from app.schemas.ai_decision_audit import AiDecisionAuditConfirm, AiDecisionAuditCreate
from app.services.ai_decision_audit import AiDecisionAuditService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
async def list_audit_logs(
    agent_name: str | None = Query(None),
    error_category: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """审计日志查询。"""
    stmt = select(OperationLog)
    if agent_name:
        stmt = stmt.where(OperationLog.agent_name == agent_name)
    if error_category:
        stmt = stmt.where(OperationLog.error_category == error_category)
    if from_date:
        stmt = stmt.where(OperationLog.created_at >= from_date)
    if to_date:
        stmt = stmt.where(OperationLog.created_at <= to_date)

    count_stmt = stmt
    count_result = await db.execute(select(sa_func.count()).select_from(count_stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.order_by(desc(OperationLog.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return success({
        "items": [
            {
                "id": op.id,
                "agent_name": op.agent_name,
                "action": op.action,
                "status": op.status.value,
                "error_category": op.error_category,
                "input_summary": op.input_summary,
                "output_summary": op.output_summary,
                "error_message": op.error_message,
                "duration_ms": op.duration_ms,
                "created_at": op.created_at.isoformat() if op.created_at else "",
                "updated_at": op.updated_at.isoformat() if op.updated_at else "",
            }
            for op in items
        ],
        "total": total,
    })


@router.get("/stats")
async def audit_stats(
    db: AsyncSession = Depends(get_db),
):
    """审计摘要 — 操作频率、失败分布。"""
    from sqlalchemy import text

    total = await db.execute(text("SELECT COUNT(*) FROM operation_logs"))
    total_count = total.scalar() or 0

    by_agent = await db.execute(
        text("SELECT agent_name, COUNT(*) as cnt FROM operation_logs GROUP BY agent_name ORDER BY cnt DESC")
    )
    by_agent_list = [{"agent_name": r[0], "count": r[1]} for r in by_agent.fetchall()]

    by_error = await db.execute(
        text("SELECT error_category, COUNT(*) as cnt FROM operation_logs WHERE error_category IS NOT NULL GROUP BY error_category")
    )
    by_error_list = [{"category": r[0], "count": r[1]} for r in by_error.fetchall()]

    system_errors = await db.execute(
        text("SELECT COUNT(*) FROM operation_logs WHERE error_category = 'system'")
    )
    system_count = system_errors.scalar() or 0

    return success({
        "total_operations": total_count,
        "system_errors": system_count,
        "by_agent": by_agent_list,
        "by_error_category": by_error_list,
    })


@router.get("/ai-audits")
async def list_ai_decision_audits(
    decision_type: str | None = Query(None, description="按决策类型过滤"),
    candidate_name: str | None = Query(None, description="按候选人名称模糊搜索"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0, description="最低置信度"),
    from_date: str | None = Query(None, description="开始日期 (ISO)"),
    to_date: str | None = Query(None, description="结束日期 (ISO)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """查询 AI 决策审计记录。"""
    stmt = select(AiDecisionAudit)

    if decision_type:
        stmt = stmt.where(AiDecisionAudit.decision_type == decision_type)
    if min_confidence is not None:
        stmt = stmt.where(AiDecisionAudit.confidence >= min_confidence)
    if from_date:
        stmt = stmt.where(AiDecisionAudit.created_at >= from_date)
    if to_date:
        stmt = stmt.where(AiDecisionAudit.created_at <= to_date)

    # Count
    count_result = await db.execute(select(sa_func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.order_by(desc(AiDecisionAudit.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return success({
        "items": [
            {
                "id": item.id,
                "candidate_id": item.candidate_id,
                "application_id": item.application_id,
                "decision_type": item.decision_type.value if item.decision_type else "",
                "model_name": item.model_name,
                "prompt_version": item.prompt_version,
                "input_refs": item.input_refs,
                "output_summary": item.output_summary,
                "cited_standard_version_ids": item.cited_standard_version_ids,
                "cited_evidence_ref_ids": item.cited_evidence_ref_ids,
                "confidence": item.confidence,
                "human_confirmed": item.human_confirmed,
                "confirmed_by": item.confirmed_by,
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else "",
                "created_at": item.created_at.isoformat() if item.created_at else "",
            }
            for item in items
        ],
        "total": total,
    })


@router.post("/ai-audits", status_code=201)
async def create_ai_decision_audit(data: AiDecisionAuditCreate, db: AsyncSession = Depends(get_db)):
    """创建 AI 决策审计记录。"""
    try:
        audit = await AiDecisionAuditService(db).create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success({
        "id": audit.id,
        "candidate_id": audit.candidate_id,
        "application_id": audit.application_id,
        "decision_type": audit.decision_type.value if audit.decision_type else "",
        "model_name": audit.model_name,
        "prompt_version": audit.prompt_version,
        "confidence": audit.confidence,
        "human_confirmed": audit.human_confirmed,
        "created_at": audit.created_at.isoformat() if audit.created_at else "",
    })


@router.put("/ai-audits/{audit_id}/confirm")
async def confirm_ai_decision_audit(audit_id: str, data: AiDecisionAuditConfirm, db: AsyncSession = Depends(get_db)):
    """人工确认 AI 决策审计记录。"""
    audit = await AiDecisionAuditService(db).confirm(audit_id, data)
    if audit is None:
        return error("审计记录不存在", status_code=404)
    return success({
        "id": audit.id,
        "human_confirmed": audit.human_confirmed,
        "confirmed_by": audit.confirmed_by,
        "confirmed_at": audit.confirmed_at.isoformat() if audit.confirmed_at else "",
    })
