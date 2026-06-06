"""每日增长指标同步 cron — 计算 CAC / 转化 / 活跃, 推飞书 (P6-9 看板数据源)。

用法:
  python3 scripts/daily-growth-metrics.py
  0 9 * * * /path/to/venv/bin/python3 /path/to/scripts/daily-growth-metrics.py >> /var/log/cron.log 2>&1

指标:
  - DAU / WAU (近 1/7 天活跃)
  - 新注册 / 试用 / 付费转化
  - CAC (近 30 天付费用户获取成本 = 营销支出 / 付费用户数)
  - 老带新 referral 转化
  - 试用到期 (D-3 / D-1 提醒清单)

输出: 推飞书 webhook (FEISHU_WEBHOOK_URL, 复用 P5-7 监控告警同机器人)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daily-growth")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _days_ago(n: int) -> datetime:
    return _now_utc() - timedelta(days=n)


async def _count(db, model, where=None) -> int:
    from sqlalchemy import func, select
    q = select(func.count()).select_from(model)
    if where is not None:
        q = q.where(where)
    return int((await db.execute(q)).scalar_one())


async def main() -> None:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription
    from app.models.user import User

    today = _now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    days_30_ago = _days_ago(30)
    days_7_ago = _days_ago(7)
    days_1_ago = _days_ago(1)

    metrics: dict = {}

    async with AsyncSessionLocal() as db:
        from app.models.notification import Notification

        new_signups_30d = await _count(db, User, User.created_at >= days_30_ago)
        new_trials_30d = await _count(db, Subscription, Subscription.created_at >= days_30_ago, ) if False else 0
        from sqlalchemy import func
        new_trials_30d = int((await db.execute(
            select(func.count()).select_from(Subscription)
            .where(Subscription.created_at >= days_30_ago)
        )).scalar_one())

        paid_30d = int((await db.execute(
            select(func.count()).select_from(Subscription)
            .where(Subscription.status == "active", Subscription.created_at >= days_30_ago)
        )).scalar_one())

        total_paid = int((await db.execute(
            select(func.count()).select_from(Subscription).where(Subscription.status == "active")
        )).scalar_one())

        trials_ending_d3 = int((await db.execute(
            select(func.count()).select_from(Subscription)
            .where(
                Subscription.status == "trialing",
                Subscription.trial_end_at.is_not(None),
                Subscription.trial_end_at >= today,
                Subscription.trial_end_at <= today + timedelta(days=3),
            )
        )).scalar_one())

        recent_inapp = await _count(db, Notification, Notification.created_at >= days_7_ago)

        metrics = {
            "new_signups_30d": new_signups_30d,
            "new_trials_30d": new_trials_30d,
            "paid_30d": paid_30d,
            "total_paid": total_paid,
            "trials_ending_in_3d": trials_ending_d3,
            "inapp_notifications_7d": recent_inapp,
            "trial_to_paid_rate": (
                f"{(paid_30d / new_trials_30d * 100):.1f}%" if new_trials_30d > 0 else "N/A"
            ),
        }

    log.info("📊 增长指标: %s", metrics)

    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        log.warning("FEISHU_WEBHOOK_URL 未配置, 仅本地日志")
        return

    content_lines = [
        "**📊 每日增长指标**",
        f"• 新注册 (30d): **{metrics['new_signups_30d']}**",
        f"• 新试用 (30d): **{metrics['new_trials_30d']}**",
        f"• 新付费 (30d): **{metrics['paid_30d']}**",
        f"• 试用→付费转化率: **{metrics['trial_to_paid_rate']}**",
        f"• 活跃付费用户: **{metrics['total_paid']}**",
        f"• 试用 3 天内到期: **{metrics['trials_ending_in_3d']}**",
        f"• in-app 通知 (7d): **{metrics['inapp_notifications_7d']}**",
    ]
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 增长日报 {today.strftime('%Y-%m-%d')}"},
                "template": "blue",
            },
            "elements": [{"tag": "markdown", "content": "\n".join(content_lines)}],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(webhook, json=payload)
        log.info("✅ 飞书推送 %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("飞书推送失败: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
