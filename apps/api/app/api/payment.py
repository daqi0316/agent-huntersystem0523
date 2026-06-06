"""P5-3: 国内支付 API — 创建/查询/退款/订阅。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.payment import (
    PaymentOrder,
    PaymentPlan,
    PaymentStatus,
    PLAN_PRICING_CENTS,
    PLAN_QUOTAS,
    Subscription,
    SubscriptionStatus,
)
from app.services.payment import (
    PaymentError,
    create_order,
    downgrade_plan,
    get_order,
    get_active_subscription,
    mark_paid,
    refund_order,
    upgrade_plan,
)

router = APIRouter()


class CreateOrderRequest(BaseModel):
    plan: str = Field(..., description="pro | enterprise")
    channel: str = Field("wechat", description="wechat | alipay")
    billing_cycle: str = Field("monthly", description="monthly | yearly")


class RefundRequest(BaseModel):
    refund_amount_cents: Optional[int] = Field(None, description="不传 = 全额")
    reason: str = Field("user_request", max_length=200)


class MockPayRequest(BaseModel):
    out_trade_no: str


@router.post("/orders", status_code=201)
async def create_payment_order(
    body: CreateOrderRequest,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """创建支付订单 (PENDING, 30min 过期)。返 qr_code 给前端渲染。"""
    org_ctx, db = ctx
    try:
        plan = PaymentPlan(body.plan)
    except ValueError:
        raise HTTPException(400, f"invalid plan: {body.plan}")
    if plan == PaymentPlan.STARTER:
        raise HTTPException(400, "starter plan is free, no order needed")
    if body.channel not in ("wechat", "alipay"):
        raise HTTPException(400, f"invalid channel: {body.channel}")

    try:
        result = await create_order(
            db,
            org_id=org_ctx.org_id,
            user_id=org_ctx.user_id,
            plan=plan,
            channel=body.channel,
            billing_cycle=body.billing_cycle,
        )
    except PaymentError as e:
        raise HTTPException(400, str(e))

    return success({
        "order_id": result.order_id,
        "out_trade_no": result.out_trade_no,
        "plan": body.plan,
        "amount_cents": result.amount_cents,
        "channel": body.channel,
        "qr_code": result.qr_code,
        "prepay_id": result.prepay_id,
        "expires_at": result.expired_at.isoformat(),
        "mock": result.mock,
    })


@router.get("/orders")
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """列当前 org 的支付订单。"""
    from app.core.org_context import OrgContext as _OrgCtx
    org_ctx, db = ctx
    q = select(PaymentOrder).where(PaymentOrder.org_id == org_ctx.org_id)
    if status_filter:
        try:
            q = q.where(PaymentOrder.status == PaymentStatus(status_filter))
        except ValueError:
            raise HTTPException(400, f"invalid status: {status_filter}")
    q = q.order_by(PaymentOrder.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return success([
        {
            "id": o.id,
            "out_trade_no": o.out_trade_no,
            "plan": o.plan.value,
            "amount_cents": o.amount_cents,
            "status": o.status.value,
            "channel": o.channel,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "refunded_at": o.refunded_at.isoformat() if o.refunded_at else None,
            "created_at": o.created_at.isoformat(),
        }
        for o in rows
    ])


@router.get("/orders/{out_trade_no}")
async def get_order_status(
    out_trade_no: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查单个订单状态。"""
    org_ctx, db = ctx
    order = await get_order(db, out_trade_no)
    if order is None or order.org_id != org_ctx.org_id:
        raise HTTPException(404, "order not found")
    return success({
        "id": order.id,
        "out_trade_no": order.out_trade_no,
        "plan": order.plan.value,
        "amount_cents": order.amount_cents,
        "status": order.status.value,
        "channel": order.channel,
        "transaction_id": order.transaction_id,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "expires_at": order.expires_at.isoformat(),
        "created_at": order.created_at.isoformat(),
    })


@router.post("/orders/{out_trade_no}/refund")
async def refund_payment(
    out_trade_no: str,
    body: RefundRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """退款 (PAID → REFUNDED, 7d 内可退)。"""
    org_ctx, db = ctx
    order = await get_order(db, out_trade_no)
    if order is None or order.org_id != org_ctx.org_id:
        raise HTTPException(404, "order not found")
    try:
        result = await refund_order(db, order, body.refund_amount_cents, body.reason)
    except PaymentError as e:
        raise HTTPException(400, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.PAYMENT_REFUND,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"out_trade_no": out_trade_no, "refund_amount_cents": result["refund_amount_cents"]},
    )
    await db.commit()
    return success(result)


@router.post("/mock-pay")
async def mock_pay_order(
    body: MockPayRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """P5-3: Mock 一键支付 (仅 mock_mode 启用, 本地开发用)。"""
    from app.core.config import settings
    if not settings.payment_mock_mode:
        raise HTTPException(403, "mock pay disabled in production")

    order = await get_order(db, body.out_trade_no)
    if order is None:
        raise HTTPException(404, "order not found")
    try:
        sub = await mark_paid(
            db, order,
            transaction_id=f"mock_tx_{body.out_trade_no[:16]}",
        )
    except PaymentError as e:
        raise HTTPException(400, str(e))

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction
    await log_audit(
        db, org_id=order.org_id,
        action=AuditLogAction.PAYMENT_PAID,
        actor_user_id=order.user_id,
        request=request,
        metadata={"out_trade_no": body.out_trade_no, "mock": True, "plan": order.plan.value},
    )
    await db.commit()

    return success({
        "out_trade_no": order.out_trade_no,
        "status": "paid",
        "transaction_id": order.transaction_id,
        "plan": sub.plan.value,
        "current_period_end": sub.current_period_end.isoformat(),
    })


@router.get("/subscription")
async def get_subscription(
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查当前 org 订阅 + 计划价目表。"""
    org_ctx, db = ctx
    sub = await get_active_subscription(db, org_ctx.org_id)
    plans = []
    for p in PaymentPlan:
        price = PLAN_PRICING_CENTS[p]
        quota = PLAN_QUOTAS[p]
        plans.append({
            "plan": p.value,
            "monthly_price_cents": price,
            "monthly_price_yuan": price / 100,
            "quota": quota,
            "is_current": sub is not None and sub.plan == p and sub.status in (
                SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD,
            ),
        })

    if sub is None:
        return success({
            "subscription": None,
            "plans": plans,
        })

    return success({
        "subscription": {
            "plan": sub.plan.value,
            "status": sub.status.value,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat(),
            "grace_period_end": sub.grace_period_end.isoformat() if sub.grace_period_end else None,
            "auto_renew": sub.auto_renew,
            "pending_plan": (sub.meta or {}).get("pending_plan"),
        },
        "plans": plans,
    })


class ChangePlanRequest(BaseModel):
    new_plan: str
    channel: str = Field("wechat", description="升级时用, 降级忽略")


@router.post("/subscription/change-plan")
async def change_plan(
    body: ChangePlanRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """升级 (立即升 + 补差价) / 降级 (下周期生效, 不退钱)。"""
    org_ctx, db = ctx
    try:
        new_plan = PaymentPlan(body.new_plan)
    except ValueError:
        raise HTTPException(400, f"invalid plan: {body.new_plan}")

    sub = await get_active_subscription(db, org_ctx.org_id)
    cur_plan = sub.plan if sub else PaymentPlan.STARTER

    from app.api.audit_logs import log_audit
    from app.models.audit_log import AuditLogAction

    if PLAN_PRICING_CENTS[new_plan] > PLAN_PRICING_CENTS[cur_plan]:
        result = await upgrade_plan(
            db, org_id=org_ctx.org_id, user_id=org_ctx.user_id,
            new_plan=new_plan, channel=body.channel,
        )
        await log_audit(
            db, org_id=org_ctx.org_id,
            action=AuditLogAction.PAYMENT_UPGRADE,
            actor_user_id=org_ctx.user_id,
            request=request,
            metadata={"from": cur_plan.value, "to": new_plan.value, "out_trade_no": result.out_trade_no},
        )
        await db.commit()
        return success({
            "action": "upgrade",
            "order": {
                "out_trade_no": result.out_trade_no,
                "amount_cents": result.amount_cents,
                "qr_code": result.qr_code,
                "expires_at": result.expired_at.isoformat(),
            },
            "pending_plan": new_plan.value,
        })
    elif PLAN_PRICING_CENTS[new_plan] < PLAN_PRICING_CENTS[cur_plan]:
        sub = await downgrade_plan(db, org_ctx.org_id, new_plan)
        await log_audit(
            db, org_id=org_ctx.org_id,
            action=AuditLogAction.PAYMENT_DOWNGRADE,
            actor_user_id=org_ctx.user_id,
            request=request,
            metadata={"from": cur_plan.value, "to": new_plan.value, "effective_at": sub.current_period_end.isoformat()},
        )
        await db.commit()
        return success({
            "action": "downgrade",
            "current_plan": cur_plan.value,
            "pending_plan": new_plan.value,
            "effective_at": sub.current_period_end.isoformat(),
        })
    else:
        raise HTTPException(400, "new plan equals current plan")


@router.post("/wechat/notify")
async def wechat_pay_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """微信支付回调 (unifiedorder notify_url)。真模式需要验签。"""
    from app.core.config import settings
    if settings.payment_mock_mode:
        return success({"code": "SUCCESS", "message": "mock mode, ignore"})
    body = await request.body()
    parsed = _parse_wechat_xml_dict(body.decode("utf-8"))
    if parsed.get("return_code") != "SUCCESS":
        return {"code": "FAIL", "message": parsed.get("return_msg", "")}
    out_trade_no = parsed.get("out_trade_no", "")
    transaction_id = parsed.get("transaction_id", "")
    order = await get_order(db, out_trade_no)
    if order is None or order.status != PaymentStatus.PENDING:
        return {"code": "SUCCESS", "message": "order not pending, ignore"}
    try:
        await mark_paid(db, order, transaction_id=transaction_id)
    except PaymentError:
        return {"code": "FAIL", "message": "mark_paid failed"}
    return {"code": "SUCCESS", "message": "OK"}


@router.post("/alipay/notify")
async def alipay_pay_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """支付宝回调。真模式需要验签 (RSA2 + out_trade_no + total_amount)。"""
    from app.core.config import settings
    if settings.payment_mock_mode:
        return success({"code": "success"})
    form = await request.form()
    out_trade_no = form.get("out_trade_no", "")
    trade_no = form.get("trade_no", "")
    order = await get_order(db, out_trade_no)
    if order is None or order.status != PaymentStatus.PENDING:
        return "success"
    try:
        await mark_paid(db, order, transaction_id=trade_no)
    except PaymentError:
        return "fail"
    return "success"


def _parse_wechat_xml_dict(xml_text: str) -> dict:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    return {child.tag: (child.text or "") for child in root}
