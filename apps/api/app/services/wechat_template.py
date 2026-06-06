"""P6-5 D2: 微信服务号模板消息 — mock 默认, 真凭据配齐自动切。

依赖: 微信服务号 + 模板消息接口 (POST /cgi-bin/message/template/send)。
模板内容需提前在微信服务号后台审核通过, 模板 ID 通过 wechat_template_id 配置。

mock_mode: 不发请求, 仅落库 Notification + 日志, 便于调试。
real_mode: 走 access_token + 模板消息 API。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


def _is_mock() -> bool:
    return not (
        settings.wechat_corp_id
        and settings.wechat_corp_secret
        and settings.wechat_template_id
    )


async def _get_access_token() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_corp_id,
                "secret": settings.wechat_corp_secret,
            },
        )
    if r.status_code != 200:
        raise RuntimeError(f"wechat access_token http {r.status_code}")
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"wechat access_token err: {data}")
    return data["access_token"]


async def send_wechat_template(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    openid: str,
    notification_type: NotificationType,
    title: str,
    body: str,
    data: Optional[dict] = None,
    link: Optional[str] = None,
) -> dict:
    """发微信模板消息 + 落库 Notification。"""
    if not openid:
        return {"ok": False, "error": "missing openid"}

    template_data = {
        "first": {"value": title, "color": "#173177"},
        "keyword1": {"value": title, "color": "#173177"},
        "keyword2": {"value": body, "color": "#173177"},
        "remark": {"value": "AI 招聘助手", "color": "#173177"},
    }
    if data:
        for i, v in enumerate(data.values(), start=3):
            template_data[f"keyword{i}"] = {"value": str(v), "color": "#173177"}

    notif = Notification(
        org_id=org_id,
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        link=link,
    )
    db.add(notif)
    await db.flush()

    if _is_mock():
        logger.info("Mock WeChat template: type=%s to=%s body=%s", notification_type.value, openid, body)
        await db.commit()
        return {
            "ok": True,
            "mock": True,
            "openid": openid,
            "notification_id": notif.id,
            "template_id": settings.wechat_template_id or "TEMPLATE_PENDING",
            "hint": "Mock mode: 微信服务号凭据未配。模板消息未真发, 仅落库。",
        }

    try:
        token = await _get_access_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}",
                json={
                    "touser": openid,
                    "template_id": settings.wechat_template_id,
                    "url": link or "https://airecruit.com",
                    "data": template_data,
                    "miniprogram": {
                        "appid": settings.wechat_template_miniprogram_appid,
                        "pagepath": "pages/index/index",
                    } if settings.wechat_template_miniprogram_appid else None,
                },
            )
        result = r.json()
        ok = result.get("errcode", -1) == 0
        notif.meta = json.dumps({"wechat": {"errcode": result.get("errcode"), "errmsg": result.get("errmsg")}})
        await db.commit()
        return {
            "ok": ok,
            "mock": False,
            "openid": openid,
            "notification_id": notif.id,
            "wechat_errcode": result.get("errcode"),
            "wechat_errmsg": result.get("errmsg"),
        }
    except Exception as e:
        logger.exception("WeChat template send failed: %s", e)
        await db.commit()
        return {"ok": False, "mock": False, "error": str(e), "notification_id": notif.id}


async def send_onboarding_d1_wechat(db, user_id: str, org_id: str, openid: str) -> dict:
    return await send_wechat_template(
        db, user_id=user_id, org_id=org_id, openid=openid,
        notification_type=NotificationType.ONBOARDING_DAY1,
        title="欢迎使用 AI 招聘助手",
        body="上传你的第一个 JD, 让 AI 帮你 15 分钟筛出 Top 10 候选人。",
        link="https://airecruit.com/onboarding/upload",
    )


async def send_onboarding_d3_wechat(db, user_id: str, org_id: str, openid: str) -> dict:
    return await send_wechat_template(
        db, user_id=user_id, org_id=org_id, openid=openid,
        notification_type=NotificationType.ONBOARDING_DAY3,
        title="已为你筛 100 份简历",
        body="完成 3 步 onboarding, 解锁 AI 评估 + 团队协作。",
        link="https://airecruit.com/onboarding/evaluate",
    )


async def send_onboarding_d7_wechat(db, user_id: str, org_id: str, openid: str) -> dict:
    return await send_wechat_template(
        db, user_id=user_id, org_id=org_id, openid=openid,
        notification_type=NotificationType.ONBOARDING_DAY7,
        title="你的首周招聘数据",
        body="本周已筛 320 份简历, 节省 18h 人工时间, 试用还剩 7 天。",
        link="https://airecruit.com/dashboard",
    )


async def send_onboarding_d14_wechat(db, user_id: str, org_id: str, openid: str) -> dict:
    return await send_wechat_template(
        db, user_id=user_id, org_id=org_id, openid=openid,
        notification_type=NotificationType.ONBOARDING_DAY14,
        title="试用到期提醒",
        body="14 天试用已结束, 续订享 8 折 + 1 个月高级版。",
        link="https://airecruit.com/pricing",
    )
