"""AI 决策审计服务 — 创建、确认审计记录。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_decision_audit import AiDecisionAudit, AiDecisionType
from app.schemas.ai_decision_audit import AiDecisionAuditConfirm, AiDecisionAuditCreate


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AiDecisionAuditService:
    """AI 决策审计管理。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: AiDecisionAuditCreate) -> AiDecisionAudit:
        audit = AiDecisionAudit(
            id=str(uuid.uuid4()),
            candidate_id=data.candidate_id,
            application_id=data.application_id,
            decision_type=AiDecisionType(data.decision_type),
            model_name=data.model_name,
            prompt_version=data.prompt_version,
            input_refs=data.input_refs,
            output_summary=data.output_summary,
            cited_standard_version_ids=data.cited_standard_version_ids,
            cited_evidence_ref_ids=data.cited_evidence_ref_ids,
            confidence=data.confidence,
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(audit)
        return audit

    async def confirm(
        self, audit_id: str, data: AiDecisionAuditConfirm,
    ) -> AiDecisionAudit | None:
        result = await self.db.execute(
            select(AiDecisionAudit).where(AiDecisionAudit.id == audit_id)
        )
        audit = result.scalar_one_or_none()
        if audit is None:
            return None
        audit.human_confirmed = True
        audit.confirmed_by = data.confirmed_by
        audit.confirmed_at = data.confirmed_at or _now()
        await self.db.commit()
        await self.db.refresh(audit)
        return audit

    async def get(self, audit_id: str) -> AiDecisionAudit | None:
        result = await self.db.execute(
            select(AiDecisionAudit).where(AiDecisionAudit.id == audit_id)
        )
        return result.scalar_one_or_none()
