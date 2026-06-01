"""ApprovalService — DB 持久化的审批管理。

替代 HumanLoopAgent 的内存 pending_approvals，确保重启不丢失。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, desc, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalStatus
from app.services.operation_service import event_bus

logger = logging.getLogger(__name__)

DEFAULT_EXPIRY_HOURS = 48


class ApprovalService:
    """审批服务 — DB 持久化。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: str,
        action_type: str,
        proposal: dict,
        params: dict | None = None,
        target_type: str = "",
        target_id: str = "",
        candidate_email: str = "",
        expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    ) -> Approval:
        now = datetime.now(timezone.utc)
        approval = Approval(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action_type=action_type,
            target_type=target_type or None,
            target_id=target_id or None,
            status=ApprovalStatus.PENDING,
            proposal=proposal,
            params=params or {},
            candidate_email=candidate_email or None,
            created_at=now,
            expires_at=now + timedelta(hours=expiry_hours),
            updated_at=now,
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)

        event_bus.publish("approval.created", {
            "approval_id": approval.id,
            "action_type": approval.action_type,
            "status": approval.status.value,
            "expires_at": approval.expires_at.isoformat() if approval.expires_at else "",
        })
        return approval

    async def resolve(
        self,
        approval_id: str,
        resolver_id: str,
        approved: bool,
        resolution: str = "",
    ) -> Approval | None:
        stmt = select(Approval).where(
            and_(Approval.id == approval_id, Approval.status == ApprovalStatus.PENDING),
        )
        result = await self.db.execute(stmt)
        approval = result.scalar_one_or_none()
        if not approval:
            return None

        now = datetime.now(timezone.utc)
        approval.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        approval.resolver_id = resolver_id
        approval.resolution = resolution or None
        approval.resolved_at = now
        approval.updated_at = now
        await self.db.commit()
        await self.db.refresh(approval)

        event_bus.publish("approval.resolved", {
            "approval_id": approval.id,
            "action_type": approval.action_type,
            "status": approval.status.value,
            "resolver_id": resolver_id,
        })
        return approval

    async def expire_pending(self) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Approval)
            .where(and_(
                Approval.status == ApprovalStatus.PENDING,
                Approval.expires_at < now,
            ))
            .values(status=ApprovalStatus.EXPIRED, updated_at=now)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        expired = result.rowcount or 0
        if expired:
            logger.info("Auto-expired %d pending approvals", expired)
            event_bus.publish("approval.expired", {"count": expired})
        return expired

    async def list_pending(self, user_id: str = "") -> list[dict]:
        await self.expire_pending()
        stmt = (
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .order_by(desc(Approval.created_at))
        )
        result = await self.db.execute(stmt)
        approvals = list(result.scalars().all())
        return [
            {
                "approval_id": a.id,
                "action_type": a.action_type,
                "status": a.status.value,
                "proposal": a.proposal,
                "params": a.params,
                "candidate_email": a.candidate_email,
                "created_at": a.created_at.isoformat() if a.created_at else "",
                "expires_at": a.expires_at.isoformat() if a.expires_at else "",
            }
            for a in approvals
        ]

    async def list_history(self, user_id: str = "", limit: int = 50) -> list[dict]:
        stmt = (
            select(Approval)
            .where(Approval.status != ApprovalStatus.PENDING)
            .order_by(desc(Approval.resolved_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        approvals = list(result.scalars().all())
        return [
            {
                "approval_id": a.id,
                "action_type": a.action_type,
                "status": a.status.value,
                "resolution": a.resolution,
                "created_at": a.created_at.isoformat() if a.created_at else "",
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else "",
            }
            for a in approvals
        ]

    async def get(self, approval_id: str) -> Approval | None:
        from sqlalchemy import select as sa_select
        result = await self.db.execute(sa_select(Approval).where(Approval.id == approval_id))
        return result.scalar_one_or_none()
