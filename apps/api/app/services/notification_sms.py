"""P6-5 D3: 阿里云短信触达 — mock 默认, 真凭据配齐自动切。

复用 anti_abuse._send_aliyun_sms (HMAC-SHA1 签名, dysmsapi.aliyuncs.com)。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationType
from app.services.anti_abuse import _send_aliyun_sms

logger = logging.getLogger(__name__)


def _is_mock() -> bool:
    return not (settings.aliyun_access_key_id and settings.aliyun_access_key_secret)


async def send_notification_sms(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    phone: str,
    notification_type: NotificationType,
    title: str,
    body: str,
    template_code: Optional[str] = None,
) -> dict:
    """发短信并落库 (Notification type=SYSTEM / PAYMENT_* / TRIAL_EXPIRING 等)。"""
    if not phone:
        return {"ok": False, "error": "missing phone"}

    if _is_mock():
        logger.info("Mock SMS: type=%s to=%s body=%s", notification_type.value, phone, body)
        notif = Notification(
            org_id=org_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            link=None,
        )
        db.add(notif)
        await db.commit()
        return {
            "ok": True,
            "mock": True,
            "phone": phone,
            "notification_id": notif.id,
            "hint": "Mock mode: 阿里云 AccessKey 未配。短信未真发, 仅落库。",
        }

    sms_ok = _send_aliyun_sms(
        phone=phone,
        code=None,
        purpose=notification_type.value,
    )
    notif = Notification(
        org_id=org_id,
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        link=None,
    )
    db.add(notif)
    await db.commit()
    return {
        "ok": sms_ok,
        "mock": False,
        "phone": phone,
        "notification_id": notif.id,
        "sms_api_response": "OK" if sms_ok else "FAIL",
    }


async def send_trial_expiring_sms(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    phone: str,
    days_left: int,
) -> dict:
    title = f"试用还剩 {days_left} 天"
    body = (
        f"您的 AI 招聘助手试用将在 {days_left} 天后到期, "
        f"升级享 8 折: https://airecruit.com/pricing"
    )
    return await send_notification_sms(
        db,
        user_id=user_id,
        org_id=org_id,
        phone=phone,
        notification_type=NotificationType.TRIAL_EXPIRING,
        title=title,
        body=body,
    )


async def send_payment_failed_sms(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    phone: str,
    retry_url: str,
) -> dict:
    body = f"您的订阅扣款失败, 请更新支付方式: {retry_url}"
    return await send_notification_sms(
        db,
        user_id=user_id,
        org_id=org_id,
        phone=phone,
        notification_type=NotificationType.PAYMENT_FAILED,
        title="支付失败",
        body=body,
    )


async def send_onboarding_d14_sms(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    phone: str,
) -> dict:
    body = (
        "恭喜完成 14 天试用! 您可继续使用并选择订阅计划, "
        "或导出数据后停止: https://airecruit.com/pricing"
    )
    return await send_notification_sms(
        db,
        user_id=user_id,
        org_id=org_id,
        phone=phone,
        notification_type=NotificationType.ONBOARDING_DAY14,
        title="试用到期",
        body=body,
    )


async def send_appeal_resolved_sms(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    phone: str,
    appeal_id: str,
) -> dict:
    body = f"您的 AI 评估申诉 #{appeal_id[-6:]} 已处理, 详情见站内信。"
    return await send_notification_sms(
        db,
        user_id=user_id,
        org_id=org_id,
        phone=phone,
        notification_type=NotificationType.APPEAL_RESOLVED,
        title="申诉处理完成",
        body=body,
    )
