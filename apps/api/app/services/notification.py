"""P5 in-app notification service + API + 触发器 (D+1/D+3/D+7/D+14 onboarding)。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.membership import Membership, MembershipStatus
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


async def send_notification(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    type_: NotificationType,
    title: str,
    body: str,
    link: Optional[str] = None,
    meta: Optional[dict] = None,
) -> Notification:
    """发站内信 (异步, 不阻塞主流程)。"""
    notif = Notification(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        link=link,
        meta=meta or {},
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    logger.info("notification sent: org=%s user=%s type=%s", org_id, user_id, type_.value)
    return notif


async def list_notifications(
    db: AsyncSession, user_id: str, org_id: str,
    limit: int = 50, unread_only: bool = False,
) -> list[Notification]:
    q = select(Notification).where(
        Notification.user_id == user_id,
        Notification.org_id == org_id,
    )
    if unread_only:
        q = q.where(Notification.read == False)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    return (await db.execute(q)).scalars().all()


async def mark_read(db: AsyncSession, notif_id: str, user_id: str) -> Optional[Notification]:
    notif = (await db.execute(
        select(Notification).where(
            Notification.id == notif_id,
            Notification.user_id == user_id,
        )
    )).scalar_one_or_none()
    if notif is None:
        return None
    if not notif.read:
        notif.read = True
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
    return notif


async def mark_all_read(db: AsyncSession, user_id: str, org_id: str) -> int:
    """一键全部标已读。"""
    from sqlalchemy import update as sa_update
    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa_update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read == False,
        )
        .values(read=True, read_at=now)
    )
    await db.commit()
    return result.rowcount or 0


async def count_unread(db: AsyncSession, user_id: str, org_id: str) -> int:
    from sqlalchemy import func as sql_func
    result = (await db.execute(
        select(sql_func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read == False,
        )
    )).scalar() or 0
    return int(result)


ONBOARDING_TEMPLATES = {
    "day1": (NotificationType.ONBOARDING_DAY1, "欢迎使用 AI Recruitment", "上传 1 份简历, 体验 AI 评估速度", "/onboarding/upload"),
    "day3": (NotificationType.ONBOARDING_DAY3, "试试智能匹配", "3 天还没创建职位? 上传职位后 AI 自动匹配候选人", "/jobs"),
    "day7": (NotificationType.ONBOARDING_DAY7, "本周使用报告", "本周你使用了 X 次 AI 评估, 节省 Y 小时", "/dashboard"),
    "day14": (NotificationType.ONBOARDING_DAY14, "试用 14 天到期", "3 天后到期, 升级 Pro 享 ¥299/月 (含智能匹配 + 50 用户)", "/settings/subscription"),
}


async def trigger_onboarding_notifications(db: AsyncSession) -> int:
    """定时 cron: 给 D+1/D+3/D+7/D+14 的用户发站内信。"""
    from app.models.user import User
    now = datetime.now(timezone.utc)
    sent = 0
    for days, (ntype, title, body, link) in ONBOARDING_TEMPLATES.items():
        target_time = now - timedelta(days=int(days[3:]))
        start_window = target_time - timedelta(minutes=30)
        end_window = target_time + timedelta(minutes=30)
        users = (await db.execute(
            select(User).where(
                User.created_at >= start_window,
                User.created_at < end_window,
            )
        )).scalars().all()
        for u in users:
            existing = (await db.execute(
                select(Notification).where(
                    Notification.user_id == u.id,
                    Notification.type == ntype,
                )
            )).scalar_one_or_none()
            if existing is not None:
                continue
            await send_notification(
                db,
                org_id="",  # 触发时无 org, 后续用户登录后补
                user_id=u.id,
                type_=ntype,
                title=title,
                body=body,
                link=link,
            )
            sent += 1
    return sent
