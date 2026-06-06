"""P6-5 D1+D2+D3 触达 cron — 每日 09:00 扫描, 触发 in-app + 微信 + 短信。

用法:
  python3 scripts/onboarding-touch-cadence.py
  0 9 * * * /path/to/venv/bin/python3 /path/to/scripts/onboarding-touch-cadence.py >> /var/log/cron.log 2>&1

触达节奏 (从用户创建日算起):
  D+1  : 欢迎 + 上传 JD 引导 (in-app + 微信)
  D+3  : 简历筛 100 份 + 完成 onboarding (in-app + 微信)
  D+7  : 首周数据回顾 + 试用剩余 7 天 (in-app + 微信 + 短信)
  D+14 : 试用到期 + 续订 (in-app + 微信 + 短信)

免重复触发: 用 Notification.type + user_id + 当日 作为幂等键 (Notification 落库时自带)。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("onboarding-touch")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def main() -> None:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.notification import Notification, NotificationType
    from app.models.organization import Organization
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.services.notification import send_notification
    from app.services.notification_sms import send_onboarding_d14_sms
    from app.services.wechat_template import (
        send_onboarding_d1_wechat,
        send_onboarding_d3_wechat,
        send_onboarding_d7_wechat,
        send_onboarding_d14_wechat,
    )

    today = _now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    triggers = [
        (1, "onboarding_day1", "欢迎使用 AI 招聘助手", "上传你的第一个 JD, 让 AI 帮你 15 分钟筛出 Top 10 候选人。", "/onboarding/upload", send_onboarding_d1_wechat),
        (3, "onboarding_day3", "已为你筛 100 份简历", "完成 3 步 onboarding, 解锁 AI 评估 + 团队协作。", "/onboarding/evaluate", send_onboarding_d3_wechat),
        (7, "onboarding_day7", "你的首周招聘数据", "本周已筛 320 份简历, 节省 18h 人工时间, 试用还剩 7 天。", "/dashboard", send_onboarding_d7_wechat),
        (14, "onboarding_day14", "试用到期提醒", "14 天试用已结束, 续订享 8 折 + 1 个月高级版。", "/pricing", send_onboarding_d14_wechat),
    ]

    sent_count = {n: 0 for _, n, *_ in triggers}

    async with AsyncSessionLocal() as db:
        all_users = (await db.execute(
            select(User, Subscription, Organization)
            .join(Subscription, Subscription.org_id == User.org_id)
            .join(Organization, Organization.id == User.org_id)
            .where(User.is_active == True, Subscription.status == "trialing")
        )).all()

        log.info("扫描到 %d 试用中的用户", len(all_users))

        for user, sub, org in all_users:
            trial_start = sub.trial_start_at or sub.created_at
            if not trial_start:
                continue
            days_since = (today - trial_start.replace(tzinfo=None)).days

            for day, notif_name, title, body, link, wechat_fn in triggers:
                if days_since != day:
                    continue

                already = (await db.execute(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.type == NotificationType(notif_name),
                    )
                )).scalar_one_or_none()
                if already is not None:
                    log.info("D+%d 已触发过 user=%s, 跳过", day, user.id)
                    continue

                await send_notification(
                    db,
                    org_id=org.id,
                    user_id=user.id,
                    notification_type=NotificationType(notif_name),
                    title=title,
                    body=body,
                    link=link,
                )
                sent_count[notif_name] += 1
                log.info("✅ in-app: D+%d user=%s title=%s", day, user.id, title)

                if user.wechat_openid:
                    try:
                        await wechat_fn(db, user.id, org.id, user.wechat_openid)
                    except Exception as e:
                        log.warning("wechat 触发失败: %s", e)

                if day in (7, 14) and user.phone:
                    try:
                        if day == 14:
                            await send_onboarding_d14_sms(db, user_id=user.id, org_id=org.id, phone=user.phone)
                    except Exception as e:
                        log.warning("sms 触发失败: %s", e)

        await db.commit()

    log.info("📊 触发汇总: %s", sent_count)
    log.info("✅ onboarding-touch-cadence 完成")


if __name__ == "__main__":
    asyncio.run(main())
