"""P6-12: CSM churn 监控 service — 检测 7d 未登录 / 健康度 < 30 / 试用到期 → 飞书 + CSM 任务。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.csm import (
    CHURN_DAYS_NO_LOGIN,
    CSMTask,
    CSMTaskSeverity,
    CSMTaskStatus,
    CSMTaskType,
    LOW_HEALTH_THRESHOLD,
)
from app.models.membership import Membership, MembershipStatus
from app.models.onboarding import CustomerHealthScore, RiskLevel
from app.models.organization import Organization
from app.models.payment import Subscription, SubscriptionStatus
from app.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def detect_churn_risks(db: AsyncSession) -> list[CSMTask]:
    """扫描全 org, 建 3 类 CSM 任务:
    1. 7d 未登录 → CHURN_RISK (P2)
    2. 健康度 < 30 → LOW_HEALTH (P1)
    3. trial 3d 内到期 → TRIAL_EXPIRING (P2)
    """
    now = _now()
    seven_days_ago = now - timedelta(days=CHURN_DAYS_NO_LOGIN)
    three_days_later = now + timedelta(days=3)

    active_orgs_q = (
        select(Organization, User)
        .join(Membership, Membership.org_id == Organization.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.status == MembershipStatus.ACTIVE,
            Membership.role.in_(["owner", "hr"]),
        )
    )
    rows = (await db.execute(active_orgs_q)).all()
    new_tasks: list[CSMTask] = []

    for org, user in rows:
        if user.last_login_at is None or user.last_login_at < seven_days_ago:
            existing = (await db.execute(
                select(CSMTask).where(
                    CSMTask.org_id == org.id,
                    CSMTask.type == CSMTaskType.CHURN_RISK,
                    CSMTask.status.in_([CSMTaskStatus.PENDING, CSMTaskStatus.IN_PROGRESS]),
                )
            )).scalar_one_or_none()
            if existing is None:
                task = CSMTask(
                    id=str(uuid.uuid4()),
                    org_id=org.id,
                    type=CSMTaskType.CHURN_RISK,
                    severity=CSMTaskSeverity.P2,
                    status=CSMTaskStatus.PENDING,
                    title=f"{org.name} 7 天未登录",
                    description=f"用户 {user.name} ({user.email}) 已 {CHURN_DAYS_NO_LOGIN} 天未登录, 1-on-1 call 客户",
                    metrics={"last_login_at": user.last_login_at.isoformat() if user.last_login_at else None},
                )
                db.add(task)
                new_tasks.append(task)

    low_health_scores = (await db.execute(
        select(CustomerHealthScore).where(
            CustomerHealthScore.total_score < LOW_HEALTH_THRESHOLD,
        )
    )).scalars().all()
    for hs in low_health_scores:
        existing = (await db.execute(
            select(CSMTask).where(
                CSMTask.org_id == hs.org_id,
                CSMTask.type == CSMTaskType.LOW_HEALTH,
                CSMTask.status.in_([CSMTaskStatus.PENDING, CSMTaskStatus.IN_PROGRESS]),
            )
        )).scalar_one_or_none()
        if existing is None:
            task = CSMTask(
                id=str(uuid.uuid4()),
                org_id=hs.org_id,
                type=CSMTaskType.LOW_HEALTH,
                severity=CSMTaskSeverity.P1,
                status=CSMTaskStatus.PENDING,
                title=f"客户健康度 {hs.total_score} (高风险)",
                description=f"健康度评分 {hs.total_score} 触发 P1 升级, 1-on-1 介入, 调研流失原因",
                metrics={
                    "total_score": hs.total_score,
                    "risk_level": hs.risk_level,
                    "login_score": hs.login_score,
                    "feature_score": hs.feature_score,
                    "support_score": hs.support_score,
                    "referral_score": hs.referral_score,
                },
            )
            db.add(task)
            new_tasks.append(task)

    trial_subs = (await db.execute(
        select(Subscription).where(
            Subscription.trial_end_at.isnot(None),
            Subscription.trial_end_at > now,
            Subscription.trial_end_at < three_days_later,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )).scalars().all()
    for sub in trial_subs:
        existing = (await db.execute(
            select(CSMTask).where(
                CSMTask.org_id == sub.org_id,
                CSMTask.type == CSMTaskType.TRIAL_EXPIRING,
                CSMTask.status.in_([CSMTaskStatus.PENDING, CSMTaskStatus.IN_PROGRESS]),
            )
        )).scalar_one_or_none()
        if existing is None:
            days_left = max(0, (sub.trial_end_at - now).days)
            task = CSMTask(
                id=str(uuid.uuid4()),
                org_id=sub.org_id,
                type=CSMTaskType.TRIAL_EXPIRING,
                severity=CSMTaskSeverity.P2,
                status=CSMTaskStatus.PENDING,
                title=f"Trial {days_left} 天后到期",
                description=f"试用到期前 {days_left} 天, 主动联系客户推升级",
                metrics={"trial_end_at": sub.trial_end_at.isoformat(), "days_left": days_left},
            )
            db.add(task)
            new_tasks.append(task)

    await db.commit()
    return new_tasks


async def list_pending_csm_tasks(db: AsyncSession, limit: int = 50) -> list[CSMTask]:
    return (await db.execute(
        select(CSMTask).where(
            CSMTask.status == CSMTaskStatus.PENDING,
        ).order_by(CSMTask.severity.asc(), CSMTask.created_at.asc()).limit(limit)
    )).scalars().all()


async def mark_task_done(db: AsyncSession, task_id: str) -> Optional[CSMTask]:
    task = (await db.execute(
        select(CSMTask).where(CSMTask.id == task_id)
    )).scalar_one_or_none()
    if task is None:
        return None
    task.status = CSMTaskStatus.DONE
    task.completed_at = _now()
    await db.commit()
    return task


def format_csm_alert(tasks: list[CSMTask]) -> str:
    if not tasks:
        return "✅ 今日无新 CSM 任务"
    by_severity: dict = {"P1": [], "P2": [], "P3": []}
    for t in tasks:
        sev = t.severity.value if hasattr(t.severity, "value") else str(t.severity)
        by_severity.setdefault(sev, []).append(t)

    lines = [f"🚨 今日新增 {len(tasks)} 个 CSM 任务", ""]
    for sev, label, emoji in [
        ("P1", "🔴 P1 紧急 (1-on-1 当天)", "🔴"),
        ("P2", "🟡 P2 关注 (1-on-1 本周)", "🟡"),
        ("P3", "⚪ P3 监控", "⚪"),
    ]:
        items = by_severity.get(sev, [])
        if not items:
            continue
        lines.append(f"{emoji} {label} ({len(items)} 个)")
        for t in items[:10]:
            lines.append(f"  • [{t.type.value}] {t.title}")
        if len(items) > 10:
            lines.append(f"  ... 还有 {len(items) - 10} 个")
        lines.append("")
    return "\n".join(lines)
