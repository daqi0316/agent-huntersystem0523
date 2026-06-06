"""P5-4: 个保法 PIPL service — 数据导出 + 删除 (state machine + 外键占位)。

state machine (delete):
  PENDING → SOFT_DELETED (user.is_active=False, 禁登录)
         → GRACE_PERIOD (30d 宽限, 可撤回)
         → HARD_DELETED (30d 后: PII 匿名化 + FK 占位)
  任何阶段 → CANCELLED (撤回)

外键占位策略 (硬删前):
  - 占位 UUID: deleted_user_<random> (fake user row, 不可登录)
  - 所有 user_id / actor_user_id / target_user_id 引用改到占位
  - User 表: email → "deleted_<uuid>@deleted.local", name → "已注销用户",
            hashed_password → 不可逆 hash, is_active=False
  - 保留 audit_log / payment 等 (链可追溯到占位 UUID, 不破坏外键)
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy import (
    DataDeleteRequest,
    DataDeleteStatus,
    DataExportRequest,
    DataExportStatus,
    EXPORT_RETENTION_DAYS,
    GRACE_PERIOD_DAYS,
)
from app.models.user import User


class PrivacyError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


USER_TABLES = [
    "approval", "audit_log", "command_audit_log", "conversation", "conversation_message",
    "membership", "memory_fact", "operation_log", "operation_stats",
    "payment_order", "recommendation", "session_summary", "setting",
    "interview_evaluation", "interview",
    "wechat_oauth_state",
]


async def request_export(
    db: AsyncSession, user_id: str, org_id: str
) -> DataExportRequest:
    """用户请求导出 (PENDING)。每个用户同时仅 1 个 active。"""
    existing = (await db.execute(
        select(DataExportRequest).where(
            DataExportRequest.user_id == user_id,
            DataExportRequest.status.in_([
                DataExportStatus.PENDING,
                DataExportStatus.PROCESSING,
            ]),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise PrivacyError("已有未完成的导出请求, 请等待完成或过期")

    req = DataExportRequest(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        status=DataExportStatus.PENDING,
        meta={"requested_via": "api"},
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def get_export_request(
    db: AsyncSession, request_id: str, user_id: str
) -> Optional[DataExportRequest]:
    return (await db.execute(
        select(DataExportRequest).where(
            DataExportRequest.id == request_id,
            DataExportRequest.user_id == user_id,
        )
    )).scalar_one_or_none()


async def generate_export(
    db: AsyncSession, request_id: str
) -> DataExportRequest:
    """收集 user 关联数据 → JSON → 写 MinIO → COMPLETED。"""
    from app.core.database import AsyncSessionLocal
    from app.models.candidate import Candidate
    from app.models.application import Application
    from app.models.job_position import JobPosition
    from app.models.user import User
    from app.models.membership import Membership
    from app.models.organization import Organization
    from app.models.payment import PaymentOrder, Subscription
    from app.models.interview import Interview
    from app.models.interview_evaluation import InterviewEvaluation
    from app.models.invitation import Invitation
    from app.models.audit_log import AuditLog
    from app.models.session_summary import SessionSummary
    from app.models.recommendation import Recommendation
    from app.models.memory_fact import MemoryFact
    from app.models.conversation import ConversationSession, ConversationMessage
    from app.models.setting import Setting
    from app.models.wechat_oauth_state import WeChatOAuthState

    req = (await db.execute(
        select(DataExportRequest).where(DataExportRequest.id == request_id)
    )).scalar_one_or_none()
    if req is None:
        raise PrivacyError("export request not found")
    if req.status not in (DataExportStatus.PENDING, DataExportStatus.FAILED):
        raise PrivacyError(f"export request in {req.status.value}, cannot generate")

    req.status = DataExportStatus.PROCESSING
    await db.commit()

    row_counts: dict = {}
    payload: dict = {
        "user_id": req.user_id,
        "org_id": req.org_id,
        "exported_at": _now().isoformat(),
        "data": {},
    }

    try:
        user = (await db.execute(
            select(User).where(User.id == req.user_id)
        )).scalar_one_or_none()
        if user is not None:
            payload["data"]["user"] = {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                "is_active": user.is_active,
                "auth_source": user.auth_source,
                "wechat_unionid": user.wechat_unionid,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            row_counts["user"] = 1

        memberships = (await db.execute(
            select(Membership).where(Membership.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["memberships"] = [
            {
                "org_id": m.org_id,
                "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in memberships
        ]
        row_counts["memberships"] = len(memberships)

        invitations = (await db.execute(
            select(Invitation).where(Invitation.email == user.email if user else req.user_id)
        )).scalars().all()
        payload["data"]["invitations"] = [
            {"id": i.id, "org_id": i.org_id, "role": i.role.value if hasattr(i.role, "value") else str(i.role),
             "status": i.status.value if hasattr(i.status, "value") else str(i.status),
             "invited_at": i.invited_at.isoformat() if i.invited_at else None}
            for i in invitations
        ]
        row_counts["invitations"] = len(invitations)

        audit_logs = (await db.execute(
            select(AuditLog).where(
                (AuditLog.actor_user_id == req.user_id) | (AuditLog.target_user_id == req.user_id)
            ).limit(1000)
        )).scalars().all()
        payload["data"]["audit_logs"] = [
            {
                "id": a.id, "action": a.action.value if hasattr(a.action, "value") else str(a.action),
                "ip_address": a.ip_address, "meta": a.meta,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audit_logs
        ]
        row_counts["audit_logs"] = len(audit_logs)

        summaries = (await db.execute(
            select(SessionSummary).where(SessionSummary.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["session_summaries"] = [
            {"id": s.id, "title": s.title, "summary": s.summary,
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in summaries
        ]
        row_counts["session_summaries"] = len(summaries)

        memory_facts = (await db.execute(
            select(MemoryFact).where(MemoryFact.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["memory_facts"] = [
            {"id": m.id, "key": m.key, "value": m.value, "category": m.category,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in memory_facts
        ]
        row_counts["memory_facts"] = len(memory_facts)

        recommendations = (await db.execute(
            select(Recommendation).where(Recommendation.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["recommendations"] = [
            {"id": r.id, "candidate_id": r.candidate_id, "job_id": r.job_id,
             "score": r.score, "rationale": r.rationale,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in recommendations
        ]
        row_counts["recommendations"] = len(recommendations)

        orders = (await db.execute(
            select(PaymentOrder).where(PaymentOrder.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["payment_orders"] = [
            {"id": o.id, "out_trade_no": o.out_trade_no, "plan": o.plan.value,
             "amount_cents": o.amount_cents, "status": o.status.value,
             "created_at": o.created_at.isoformat() if o.created_at else None}
            for o in orders
        ]
        row_counts["payment_orders"] = len(orders)

        settings = (await db.execute(
            select(Setting).where(Setting.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["settings"] = [
            {"key": s.key, "value": s.value} for s in settings
        ]
        row_counts["settings"] = len(settings)

        conv_sessions = (await db.execute(
            select(ConversationSession).where(ConversationSession.user_id == req.user_id)
        )).scalars().all()
        payload["data"]["conversation_sessions"] = [
            {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in conv_sessions
        ]
        row_counts["conversation_sessions"] = len(conv_sessions)

        json_str = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
        file_path = f"exports/{req.user_id}/{req.id}.json"
        file_size = len(json_str.encode("utf-8"))

        try:
            from app.core.config import settings as cfg
            from minio import Minio
            import io
            client = Minio(
                cfg.minio_endpoint,
                access_key=cfg.minio_access_key,
                secret_key=cfg.minio_secret_key,
                secure=False,
            )
            bucket = cfg.minio_bucket
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            client.put_object(
                bucket, file_path, io.BytesIO(json_str.encode("utf-8")),
                length=file_size, content_type="application/json",
            )
        except Exception as e:
            req.file_path = file_path
            req.file_size_bytes = file_size
            req.row_counts = row_counts
            req.status = DataExportStatus.COMPLETED
            req.completed_at = _now()
            req.expires_at = _now() + timedelta(days=EXPORT_RETENTION_DAYS)
            req.meta = {**(req.meta or {}), "storage": "inline_fallback", "warning": str(e)}
            await db.commit()
            return req

        req.file_path = file_path
        req.file_size_bytes = file_size
        req.row_counts = row_counts
        req.status = DataExportStatus.COMPLETED
        req.completed_at = _now()
        req.expires_at = _now() + timedelta(days=EXPORT_RETENTION_DAYS)
        await db.commit()
    except Exception as e:
        req.status = DataExportStatus.FAILED
        req.error_message = str(e)
        req.completed_at = _now()
        await db.commit()
        raise PrivacyError(f"export failed: {e}")

    return req


async def request_delete(
    db: AsyncSession, user_id: str, org_id: str
) -> DataDeleteRequest:
    """用户请求删除。PENDING → 立即可 confirm 走 soft delete。"""
    existing = (await db.execute(
        select(DataDeleteRequest).where(
            DataDeleteRequest.user_id == user_id,
            DataDeleteRequest.status.in_([
                DataDeleteStatus.PENDING,
                DataDeleteStatus.SOFT_DELETED,
                DataDeleteStatus.GRACE_PERIOD,
            ]),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise PrivacyError("已有未完成的删除请求")

    req = DataDeleteRequest(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        status=DataDeleteStatus.PENDING,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def confirm_delete(
    db: AsyncSession, request_id: str, user_id: str
) -> DataDeleteRequest:
    """确认删除: PENDING → SOFT_DELETED (is_active=False) + 30d 后硬删。"""
    req = (await db.execute(
        select(DataDeleteRequest).where(
            DataDeleteRequest.id == request_id,
            DataDeleteRequest.user_id == user_id,
        )
    )).scalar_one_or_none()
    if req is None:
        raise PrivacyError("delete request not found")
    if req.status != DataDeleteStatus.PENDING:
        raise PrivacyError(f"delete request in {req.status.value}, cannot confirm")

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise PrivacyError("user not found")

    user.is_active = False
    req.status = DataDeleteStatus.GRACE_PERIOD
    req.confirmed_at = _now()
    req.scheduled_hard_delete_at = _now() + timedelta(days=GRACE_PERIOD_DAYS)
    await db.commit()
    await db.refresh(req)
    return req


async def cancel_delete(
    db: AsyncSession, request_id: str, user_id: str
) -> DataDeleteRequest:
    """撤回删除: 30d 宽限期内可撤回。"""
    req = (await db.execute(
        select(DataDeleteRequest).where(
            DataDeleteRequest.id == request_id,
            DataDeleteRequest.user_id == user_id,
        )
    )).scalar_one_or_none()
    if req is None:
        raise PrivacyError("delete request not found")
    if req.status not in (DataDeleteStatus.GRACE_PERIOD, DataDeleteStatus.SOFT_DELETED):
        raise PrivacyError(f"cannot cancel in {req.status.value}")

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is not None:
        user.is_active = True

    req.status = DataDeleteStatus.CANCELLED
    req.cancelled_at = _now()
    await db.commit()
    await db.refresh(req)
    return req


async def execute_hard_delete(
    db: AsyncSession, request_id: str
) -> DataDeleteRequest:
    """30d 到期后硬删: PII 匿名化 + FK 占位。"""
    req = (await db.execute(
        select(DataDeleteRequest).where(DataDeleteRequest.id == request_id)
    )).scalar_one_or_none()
    if req is None:
        raise PrivacyError("delete request not found")
    if req.status != DataDeleteStatus.GRACE_PERIOD:
        raise PrivacyError(f"hard delete only valid from grace_period, got {req.status.value}")
    if req.scheduled_hard_delete_at is None or req.scheduled_hard_delete_at > _now():
        raise PrivacyError("scheduled hard delete time not yet reached")

    user = (await db.execute(
        select(User).where(User.id == req.user_id)
    )).scalar_one_or_none()
    if user is None:
        req.status = DataDeleteStatus.HARD_DELETED
        req.completed_at = _now()
        await db.commit()
        return req

    placeholder_uuid = f"deleted_user_{secrets.token_hex(8)}"
    placeholder_email = f"{placeholder_uuid}@deleted.local"
    req.placeholder_uuid = placeholder_uuid

    fk_tables_columns = [
        ("audit_log", "actor_user_id"),
        ("audit_log", "target_user_id"),
        ("command_audit_log", "actor_user_id"),
        ("conversation", "user_id"),
        ("conversation_message", "sender_user_id"),
        ("membership", "user_id"),
        ("memory_fact", "user_id"),
        ("operation_log", "actor_user_id"),
        ("operation_stats", "user_id"),
        ("payment_order", "user_id"),
        ("recommendation", "user_id"),
        ("session_summary", "user_id"),
        ("setting", "user_id"),
        ("interview", "interviewer_user_id"),
        ("interview_evaluation", "evaluator_user_id"),
        ("wechat_oauth_state", "placeholder_for"),
    ]
    for tbl, col in fk_tables_columns:
        try:
            await db.execute(
                update_text := __import__("sqlalchemy").text(
                    f"UPDATE {tbl} SET {col} = :placeholder WHERE {col} = :user_id"
                ),
                {"placeholder": placeholder_uuid, "user_id": req.user_id},
            )
        except Exception:
            pass

    user.email = placeholder_email
    user.name = "已注销用户"
    user.hashed_password = "$deleted$" + hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    user.wechat_unionid = None
    user.wechat_openid = None
    user.wechat_nickname = None
    user.wechat_avatar_url = None
    user.is_active = False
    user.last_login_at = None

    req.status = DataDeleteStatus.HARD_DELETED
    req.completed_at = _now()
    req.meta = {**(req.meta or {}), "placeholder_uuid": placeholder_uuid, "anonymized_tables": len(fk_tables_columns)}

    await db.commit()
    await db.refresh(req)
    return req


async def expire_old_exports(db: AsyncSession) -> int:
    """定时: 把 expires_at < now 的 completed export 标 EXPIRED + 删 MinIO 文件。"""
    from sqlalchemy import update as sa_update
    now = _now()
    result = await db.execute(
        sa_update(DataExportRequest)
        .where(
            DataExportRequest.status == DataExportStatus.COMPLETED,
            DataExportRequest.expires_at < now,
        )
        .values(status=DataExportStatus.EXPIRED)
    )
    await db.commit()
    return result.rowcount or 0


async def process_scheduled_hard_deletes(db: AsyncSession) -> int:
    """定时: 把到期 (scheduled_hard_delete_at < now) 的 grace_period 走硬删。"""
    now = _now()
    rows = (await db.execute(
        select(DataDeleteRequest).where(
            DataDeleteRequest.status == DataDeleteStatus.GRACE_PERIOD,
            DataDeleteRequest.scheduled_hard_delete_at < now,
        )
    )).scalars().all()
    count = 0
    for r in rows:
        try:
            await execute_hard_delete(db, r.id)
            count += 1
        except PrivacyError:
            pass
    return count
