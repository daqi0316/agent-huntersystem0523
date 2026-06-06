"""P5-15: 客户 onboarding runbook service — 批量导入 + 健康度算法。"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.candidate import Candidate
from app.models.job_position import JobPosition
from app.models.onboarding import (
    BatchImportRequest,
    BatchImportStatus,
    CustomerHealthScore,
    RiskLevel,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


REQUIRED_CANDIDATE_COLS = ["name", "email"]
REQUIRED_JOB_COLS = ["title"]


@dataclass
class ImportResult:
    total: int
    imported: int
    failed: int
    errors: list


def _classify_risk(total: float) -> str:
    if total < 0 or total > 100:
        return RiskLevel.UNKNOWN
    if total < 50:
        return RiskLevel.HIGH_RISK
    if total < 70:
        return RiskLevel.AT_RISK
    if total >= 70:
        return RiskLevel.HEALTHY
    return RiskLevel.UNKNOWN


async def import_candidates_csv(
    db: AsyncSession, org_id: str, user_id: str, csv_text: str
) -> tuple[BatchImportRequest, ImportResult]:
    """CSV 格式: name, email, phone?, location?, source?"""
    batch = BatchImportRequest(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        entity_type="candidate",
        status=BatchImportStatus.PROCESSING,
        started_at=_now(),
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    reader = csv.DictReader(io.StringIO(csv_text))
    errors: list = []
    imported = 0
    failed = 0
    total = 0
    for row_num, row in enumerate(reader, start=2):
        total += 1
        try:
            missing = [c for c in REQUIRED_CANDIDATE_COLS if not row.get(c)]
            if missing:
                raise ValueError(f"missing required columns: {missing}")
            cand = Candidate(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=row["name"].strip(),
                email=row["email"].strip(),
                phone=(row.get("phone") or "").strip() or None,
                location=(row.get("location") or "").strip() or None,
                source=(row.get("source") or "csv_import").strip(),
            )
            db.add(cand)
            imported += 1
        except Exception as e:
            failed += 1
            errors.append({"row": row_num, "error": str(e), "data": dict(row)})

    await db.commit()

    batch.total_rows = total
    batch.imported_rows = imported
    batch.failed_rows = failed
    batch.errors = errors[:100]
    batch.completed_at = _now()
    batch.status = (
        BatchImportStatus.COMPLETED if failed == 0
        else BatchImportStatus.PARTIAL if imported > 0
        else BatchImportStatus.FAILED
    )
    await db.commit()
    await db.refresh(batch)
    return batch, ImportResult(total=total, imported=imported, failed=failed, errors=errors)


async def import_jobs_csv(
    db: AsyncSession, org_id: str, user_id: str, csv_text: str
) -> tuple[BatchImportRequest, ImportResult]:
    """CSV 格式: title, department?, location?, description?, requirements?"""
    batch = BatchImportRequest(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        entity_type="job_position",
        status=BatchImportStatus.PROCESSING,
        started_at=_now(),
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    reader = csv.DictReader(io.StringIO(csv_text))
    errors: list = []
    imported = 0
    failed = 0
    total = 0
    for row_num, row in enumerate(reader, start=2):
        total += 1
        try:
            missing = [c for c in REQUIRED_JOB_COLS if not row.get(c)]
            if missing:
                raise ValueError(f"missing required columns: {missing}")
            job = JobPosition(
                id=str(uuid.uuid4()),
                org_id=org_id,
                title=row["title"].strip(),
                department=(row.get("department") or "").strip() or None,
                location=(row.get("location") or "").strip() or None,
                description=(row.get("description") or "").strip() or None,
                requirements=(row.get("requirements") or "").strip() or None,
            )
            db.add(job)
            imported += 1
        except Exception as e:
            failed += 1
            errors.append({"row": row_num, "error": str(e), "data": dict(row)})

    await db.commit()

    batch.total_rows = total
    batch.imported_rows = imported
    batch.failed_rows = failed
    batch.errors = errors[:100]
    batch.completed_at = _now()
    batch.status = (
        BatchImportStatus.COMPLETED if failed == 0
        else BatchImportStatus.PARTIAL if imported > 0
        else BatchImportStatus.FAILED
    )
    await db.commit()
    await db.refresh(batch)
    return batch, ImportResult(total=total, imported=imported, failed=failed, errors=errors)


async def compute_health_score(db: AsyncSession, org_id: str) -> CustomerHealthScore:
    """4 维度 40/30/20/10 权重:
    - 登录频次 40%: 过去 7d 该 org 有登录的用户数 / 总用户数
    - 功能使用 30%: 过去 7d 该 org 的 audit_log 条数 / 7d
    - 工单数 20%: 反向, 工单越少分越高
    - 推荐行为 10%: 过去 30d 邀请数 (cap 5)
    """
    from app.models.user import User
    from app.models.audit_log import AuditLog
    from app.models.invitation import Invitation
    from app.models.membership import Membership, MembershipStatus

    now = _now()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_users_q = select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.org_id == org_id,
        Membership.status == MembershipStatus.ACTIVE,
    )
    total_users = (await db.execute(total_users_q)).scalars().all()
    total_count = len(total_users)
    if total_count == 0:
        total_count = 1

    active_users = sum(1 for u in total_users if u.last_login_at and u.last_login_at > seven_days_ago)
    login_ratio = active_users / total_count
    login_score = min(100, login_ratio * 100 * 1.5)

    audit_7d = (await db.execute(
        select(AuditLog).where(
            AuditLog.org_id == org_id,
            AuditLog.created_at > seven_days_ago,
        )
    )).scalars().all()
    feature_count = len(audit_7d)
    feature_score = min(100, feature_count * 2)

    invite_30d = (await db.execute(
        select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.invited_at > thirty_days_ago,
        )
    )).scalars().all()
    invite_count = min(5, len(invite_30d))
    referral_score = invite_count * 20

    support_score = 80.0

    total = (
        login_score * 0.40
        + feature_score * 0.30
        + support_score * 0.20
        + referral_score * 0.10
    )

    risk = _classify_risk(total)

    existing = (await db.execute(
        select(CustomerHealthScore).where(CustomerHealthScore.org_id == org_id)
    )).scalar_one_or_none()
    if existing is None:
        existing = CustomerHealthScore(org_id=org_id)
        db.add(existing)

    existing.login_score = round(login_score, 2)
    existing.feature_score = round(feature_score, 2)
    existing.support_score = round(support_score, 2)
    existing.referral_score = round(referral_score, 2)
    existing.total_score = round(total, 2)
    existing.risk_level = risk
    existing.metrics_snapshot = {
        "total_users": total_count,
        "active_users_7d": active_users,
        "audit_events_7d": feature_count,
        "invites_30d": invite_count,
    }
    existing.computed_at = now
    await db.commit()
    await db.refresh(existing)
    return existing


async def get_health_score(db: AsyncSession, org_id: str) -> Optional[CustomerHealthScore]:
    return (await db.execute(
        select(CustomerHealthScore).where(CustomerHealthScore.org_id == org_id)
    )).scalar_one_or_none()


async def list_all_health_scores(db: AsyncSession) -> list[CustomerHealthScore]:
    return (await db.execute(
        select(CustomerHealthScore).order_by(CustomerHealthScore.total_score.asc())
    )).scalars().all()
