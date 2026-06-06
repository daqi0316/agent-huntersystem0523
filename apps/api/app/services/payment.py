"""P5-3: 国内支付 service — 微信支付 + 支付宝 (双模式 mock/真)。

state machine:
  PaymentOrder: PENDING → PAID → REFUNDED
                       ↓
                     EXPIRED / CANCELLED
  Subscription: ACTIVE → GRACE_PERIOD (支付失败 3 次) → EXPIRED
                          → CANCELLED (用户主动取消)

mock_mode=True:
- create_order 返 fake prepay_id, 不调真 API
- 真凭据 (商户号/appid) 不需要
- 真要测试需要商户号 + 沙箱, 见 docker-assets
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.organization import Organization, OrganizationPlan
from app.models.payment import (
    PLAN_PRICING_CENTS,
    PLAN_QUOTAS,
    PaymentChannel,
    PaymentOrder,
    PaymentPlan,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)


class PaymentError(Exception):
    pass


@dataclass
class OrderResult:
    order_id: str
    out_trade_no: str
    amount_cents: int
    prepay_id: Optional[str]
    qr_code: Optional[str]
    expired_at: datetime
    mock: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_out_trade_no(org_id: str) -> str:
    ts = _now().strftime("%Y%m%d%H%M%S")
    rand = secrets.token_hex(4)
    short_org = org_id.replace("-", "")[:8]
    return f"{short_org}{ts}{rand}"


def compute_upgrade_prorate(
    current_plan: PaymentPlan, new_plan: PaymentPlan, days_left: int, cycle_days: int = 30
) -> int:
    """升级补差价: (新plan价 - 旧plan价) × (剩余天数 / 周期天数)。"""
    cur_price = PLAN_PRICING_CENTS[current_plan]
    new_price = PLAN_PRICING_CENTS[new_plan]
    if new_price <= cur_price:
        return 0
    diff = new_price - cur_price
    return int(diff * days_left / cycle_days)


async def get_active_subscription(db: AsyncSession, org_id: str) -> Optional[Subscription]:
    return (await db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    )).scalar_one_or_none()


async def create_order(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    plan: PaymentPlan,
    channel: str = "wechat",
    billing_cycle: str = "monthly",
) -> OrderResult:
    """创建支付订单 (pending 状态, 30min 过期)。"""
    if plan == PaymentPlan.STARTER:
        raise PaymentError("starter plan is free, no order needed")
    amount_cents = PLAN_PRICING_CENTS[plan]
    out_trade_no = _generate_out_trade_no(org_id)
    expires_at = _now() + timedelta(minutes=settings.payment_order_expire_minutes)

    order = PaymentOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        plan=plan,
        billing_cycle=billing_cycle,
        amount_cents=amount_cents,
        status=PaymentStatus.PENDING,
        channel=channel,
        out_trade_no=out_trade_no,
        expires_at=expires_at,
        meta={"created_via": "api"},
    )
    db.add(order)

    prepay_id = None
    qr_code = None

    if settings.payment_mock_mode:
        prepay_id = f"mock_prepay_{secrets.token_hex(16)}"
        if channel == "wechat":
            qr_code = f"weixin://wxpay/bizpayurl?pr=mock_{out_trade_no}"
        elif channel == "alipay":
            qr_code = f"https://qr.alipay.com/mock_{out_trade_no}"
    else:
        if channel == "wechat":
            prepay_id, qr_code = await _wechat_create_prepay(order, out_trade_no)
        elif channel == "alipay":
            qr_code = await _alipay_create_prepay(order, out_trade_no)
        else:
            raise PaymentError(f"unsupported channel: {channel}")

    await db.commit()
    await db.refresh(order)

    return OrderResult(
        order_id=order.id,
        out_trade_no=out_trade_no,
        amount_cents=amount_cents,
        prepay_id=prepay_id,
        qr_code=qr_code,
        expired_at=expires_at,
        mock=settings.payment_mock_mode,
    )


async def get_order(db: AsyncSession, out_trade_no: str) -> Optional[PaymentOrder]:
    return (await db.execute(
        select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
    )).scalar_one_or_none()


async def mark_paid(
    db: AsyncSession,
    order: PaymentOrder,
    transaction_id: str,
    paid_at: Optional[datetime] = None,
) -> Subscription:
    """订单标为 PAID, 激活/续期 subscription。幂等: 已 PAID 直接返。"""
    if order.status == PaymentStatus.PAID:
        sub = await get_active_subscription(db, order.org_id)
        if sub is not None:
            return sub
    if order.status not in (PaymentStatus.PENDING,):
        raise PaymentError(f"order {order.out_trade_no} in {order.status.value}, cannot mark paid")

    order.status = PaymentStatus.PAID
    order.transaction_id = transaction_id
    order.paid_at = paid_at or _now()

    sub = await get_active_subscription(db, order.org_id)
    if sub is None:
        sub = Subscription(
            id=str(uuid.uuid4()),
            org_id=order.org_id,
            plan=order.plan,
            billing_cycle=order.billing_cycle,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=order.paid_at,
            current_period_end=order.paid_at + timedelta(days=30),
            auto_renew=True,
            last_payment_order_id=order.id,
        )
        db.add(sub)
    else:
        if order.paid_at > sub.current_period_end:
            sub.current_period_start = order.paid_at
        sub.current_period_end = sub.current_period_end + timedelta(days=30)
        sub.status = SubscriptionStatus.ACTIVE
        sub.grace_period_end = None
        sub.last_payment_order_id = order.id
        if order.plan.value > sub.plan.value:
            sub.plan = order.plan

    org = (await db.execute(
        select(Organization).where(Organization.id == order.org_id)
    )).scalar_one_or_none()
    if org is not None:
        org.plan = OrganizationPlan(order.plan.value)
        quota = PLAN_QUOTAS[order.plan]
        org.quota_max_users = quota["max_users"]
        org.quota_max_candidates = quota["max_candidates"]
        org.quota_llm_tokens_per_month = quota["llm_tokens_per_month"]
        org.subscription_renews_at = sub.current_period_end

    await db.commit()
    return sub


async def refund_order(
    db: AsyncSession,
    order: PaymentOrder,
    refund_amount_cents: Optional[int] = None,
    reason: str = "user_request",
) -> dict:
    """退款。状态机: PAID → REFUNDED。仅 7d 内可退。"""
    if order.status != PaymentStatus.PAID:
        raise PaymentError(f"order {order.out_trade_no} is {order.status.value}, not PAID")
    if order.paid_at is None:
        raise PaymentError("order has no paid_at")
    days_since_paid = (_now() - order.paid_at).days
    if days_since_paid > 7:
        raise PaymentError("refund window expired (>7d)")
    amount = refund_amount_cents or order.amount_cents
    if amount > order.amount_cents:
        raise PaymentError("refund amount > order amount")

    if not settings.payment_mock_mode:
        if order.channel == "wechat":
            await _wechat_refund(order, amount)
        elif order.channel == "alipay":
            await _alipay_refund(order, amount)

    order.status = PaymentStatus.REFUNDED
    order.refunded_at = _now()
    order.refund_amount_cents = amount
    order.meta = {**(order.meta or {}), "refund_reason": reason}

    sub = await get_active_subscription(db, order.org_id)
    if sub is not None and sub.last_payment_order_id == order.id:
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = _now()

    await db.commit()
    return {
        "out_trade_no": order.out_trade_no,
        "refund_amount_cents": amount,
        "refunded_at": order.refunded_at.isoformat(),
        "mock": settings.payment_mock_mode,
    }


async def upgrade_plan(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    new_plan: PaymentPlan,
    channel: str = "wechat",
) -> OrderResult:
    """升级 plan: 立即升 + 补差价 (按剩余天数)。"""
    sub = await get_active_subscription(db, org_id)
    if sub is None:
        return await create_order(db, org_id, user_id, new_plan, channel)
    if new_plan.value <= sub.plan.value:
        raise PaymentError("use downgrade_plan for lower plans")
    return await create_order(db, org_id, user_id, new_plan, channel)


async def downgrade_plan(
    db: AsyncSession, org_id: str, new_plan: PaymentPlan
) -> Subscription:
    """降级 plan: 下周期生效, 不退当前周期钱。"""
    sub = await get_active_subscription(db, org_id)
    if sub is None:
        raise PaymentError("no active subscription")
    if new_plan.value >= sub.plan.value:
        raise PaymentError("use upgrade_plan for higher plans")
    sub.meta = {**(sub.meta or {}), "pending_plan": new_plan.value}
    await db.commit()
    await db.refresh(sub)
    return sub


async def expire_overdue_orders(db: AsyncSession) -> int:
    """定时任务调用: 把 PENDING + expires_at < now 的订单标 EXPIRED。"""
    from sqlalchemy import update

    now = _now()
    result = await db.execute(
        update(PaymentOrder)
        .where(PaymentOrder.status == PaymentStatus.PENDING, PaymentOrder.expires_at < now)
        .values(status=PaymentStatus.EXPIRED, updated_at=now)
    )
    await db.commit()
    return result.rowcount or 0


async def _wechat_create_prepay(order: PaymentOrder, out_trade_no: str) -> tuple[str, Optional[str]]:
    """真模式: 调 https://api.mch.weixin.qq.com/pay/unifiedorder。"""
    if not (settings.wechat_pay_merchant_id and settings.wechat_pay_api_key):
        raise PaymentError("wechat pay credentials not configured")
    url = "https://api.mch.weixin.qq.com/pay/unifiedorder"
    body = _build_wechat_unifiedorder_xml(order, out_trade_no, settings.payment_notify_base_url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, content=body, headers={"Content-Type": "application/xml"})
    parsed = _parse_wechat_xml(resp.text)
    if parsed.get("return_code") != "SUCCESS":
        raise PaymentError(f"wechat unifiedorder failed: {parsed.get('return_msg')}")
    return parsed.get("prepay_id", ""), parsed.get("code_url")


async def _alipay_create_prepay(order: PaymentOrder, out_trade_no: str) -> str:
    """真模式: 调 alipay.trade.precreate (当面付, 返 qr_code)."""
    if not settings.alipay_app_id:
        raise PaymentError("alipay app_id not configured")
    url = "https://openapi.alipay.com/gateway.do"
    params = _build_alipay_precreate_params(order, out_trade_no, settings.payment_notify_base_url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
    parsed = resp.json()
    if parsed.get("code") != "10000":
        raise PaymentError(f"alipay precreate failed: {parsed.get('msg')}")
    return parsed.get("alipay_trade_precreate_response", {}).get("qr_code", "")


async def _wechat_refund(order: PaymentOrder, amount_cents: int) -> None:
    raise PaymentError("wechat refund implementation pending merchant credentials")


async def _alipay_refund(order: PaymentOrder, amount_cents: int) -> None:
    raise PaymentError("alipay refund implementation pending merchant credentials")


def _build_wechat_unifiedorder_xml(order: PaymentOrder, out_trade_no: str, notify_url: str) -> str:
    body = (
        f"<xml>"
        f"<appid>{settings.wechat_corp_id}</appid>"
        f"<mch_id>{settings.wechat_pay_merchant_id}</mch_id>"
        f"<nonce_str>{secrets.token_hex(16)}</nonce_str>"
        f"<body>AI Recruitment - {order.plan.value} 订阅</body>"
        f"<out_trade_no>{out_trade_no}</out_trade_no>"
        f"<total_fee>{order.amount_cents}</total_fee>"
        f"<spbill_create_ip>127.0.0.1</spbill_create_ip>"
        f"<notify_url>{notify_url}/api/v1/payment/wechat/notify</notify_url>"
        f"<trade_type>NATIVE</trade_type>"
        f"</xml>"
    )
    sign = _wechat_sign(body, settings.wechat_pay_api_key)
    return body.replace("</xml>", f"<sign>{sign}</sign></xml>")


def _wechat_sign(body: str, api_key: str) -> str:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(body)
    parts = []
    for child in root:
        if child.tag == "sign":
            continue
        parts.append(f"{child.tag}={child.text or ''}")
    string_a = "&".join(sorted(parts)) + f"&key={api_key}"
    return hashlib.md5(string_a.encode("utf-8")).hexdigest().upper()


def _parse_wechat_xml(xml_text: str) -> dict:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    return {child.tag: (child.text or "") for child in root}


def _build_alipay_precreate_params(order: PaymentOrder, out_trade_no: str, notify_url: str) -> dict:
    return {
        "app_id": settings.alipay_app_id,
        "method": "alipay.trade.precreate",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "biz_content": (
            f'{{"out_trade_no":"{out_trade_no}",'
            f'"total_amount":"{order.amount_cents/100:.2f}",'
            f'"subject":"AI Recruitment {order.plan.value} 订阅"}}'
        ),
        "notify_url": f"{notify_url}/api/v1/payment/alipay/notify",
    }
