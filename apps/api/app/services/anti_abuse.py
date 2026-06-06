"""P5-11: 反垃圾/反滥用 service — 短信 + 1手机1号 + 邀请防刷 + LLM 熔断。"""
from __future__ import annotations

import hashlib
import os
import random
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.anti_abuse import (
    SMS_CODE_LENGTH,
    SMS_CODE_TTL_MINUTES,
    SMS_MAX_ATTEMPTS,
    DeviceFingerprint,
    SmsPurpose,
    SmsVerification,
)
from app.models.user import User


class AntiAbuseError(Exception):
    pass


PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone))


def compute_device_fingerprint(user_agent: str, ip: str) -> str:
    """生成设备指纹: UA + IP + 一个静态 salt 哈希。"""
    salt = "ai-recruitment-device-fp-v1"
    raw = f"{user_agent}|{ip}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def send_sms_code(
    db: AsyncSession,
    phone: str,
    purpose: str = SmsPurpose.REGISTER,
    ip_address: Optional[str] = None,
) -> SmsVerification:
    """发短信验证码 (mock 模式返固定 code, 真模式调阿里云)。"""
    if not validate_phone(phone):
        raise AntiAbuseError("invalid phone format")

    recent = (await db.execute(
        select(SmsVerification).where(
            SmsVerification.phone == phone,
            SmsVerification.purpose == purpose,
            SmsVerification.created_at > _now() - timedelta(minutes=1),
        )
    )).scalars().all()
    if len(recent) >= 3:
        raise AntiAbuseError("1 分钟内最多发 3 条短信, 请稍后再试")

    code = "".join(random.choices("0123456789", k=SMS_CODE_LENGTH)) if settings.sms_mock_mode else None

    if not settings.sms_mock_mode:
        if not (settings.aliyun_access_key_id and settings.aliyun_access_key_secret):
            raise AntiAbuseError("aliyun sms credentials not configured")
        ok = await _send_aliyun_sms(phone, code, purpose)
        if not ok:
            raise AntiAbuseError("aliyun sms send failed")

    verification = SmsVerification(
        id=str(uuid.uuid4()),
        phone=phone,
        code=code or "000000",
        purpose=purpose,
        expires_at=_now() + timedelta(minutes=SMS_CODE_TTL_MINUTES),
        ip_address=ip_address,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


async def verify_sms_code(
    db: AsyncSession,
    phone: str,
    code: str,
    purpose: str,
) -> SmsVerification:
    """验短信码。成功 → 标记 used_at; 失败 → attempts++。"""
    if not validate_phone(phone):
        raise AntiAbuseError("invalid phone")

    record = (await db.execute(
        select(SmsVerification).where(
            SmsVerification.phone == phone,
            SmsVerification.purpose == purpose,
            SmsVerification.used_at.is_(None),
        ).order_by(SmsVerification.created_at.desc())
    )).scalars().first()
    if record is None:
        raise AntiAbuseError("no active verification code")
    if record.expires_at < _now():
        raise AntiAbuseError("verification code expired")
    if record.attempts >= SMS_MAX_ATTEMPTS:
        raise AntiAbuseError("too many attempts, request a new code")
    if record.code != code:
        record.attempts += 1
        await db.commit()
        raise AntiAbuseError("invalid code")

    record.used_at = _now()
    await db.commit()
    return record


async def bind_phone_to_user(
    db: AsyncSession, user: User, phone: str
) -> User:
    """绑手机到 user (1 手机 1 账号)。"""
    if not validate_phone(phone):
        raise AntiAbuseError("invalid phone")

    existing = (await db.execute(
        select(User).where(User.phone == phone, User.id != user.id)
    )).scalar_one_or_none()
    if existing is not None:
        raise AntiAbuseError("手机号已被其他账号绑定")

    user.phone = phone
    user.phone_verified = True
    user.phone_verified_at = _now()
    await db.commit()
    return user


async def check_invite_rate_limit(
    db: AsyncSession,
    org_id: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> tuple[bool, str]:
    """检查邀请频率: 同 IP 24h ≤ N, 同设备 24h ≤ M。返 (allowed, reason)。"""
    if not ip_address:
        return True, "no_ip"

    fp_hash = compute_device_fingerprint(user_agent or "", ip_address)
    since = _now() - timedelta(hours=24)

    from app.models.anti_abuse import DeviceFingerprint
    from sqlalchemy import update as sa_update

    fp_record = (await db.execute(
        select(DeviceFingerprint).where(
            DeviceFingerprint.org_id == org_id,
            DeviceFingerprint.fingerprint_hash == fp_hash,
        )
    )).scalar_one_or_none()

    if fp_record is None:
        new_fp = DeviceFingerprint(
            id=str(uuid.uuid4()),
            org_id=org_id,
            user_id=None,
            fingerprint_hash=fp_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(new_fp)
        await db.commit()
        return True, "first_seen"

    from app.models.invitation import Invitation, InvitationStatus
    from app.models.membership import Membership
    invites_24h = (await db.execute(
        select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.invited_by == fp_record.user_id,
            Invitation.invited_at > since,
        ) if fp_record.user_id else select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.invited_at > since,
        )
    )).scalars().all()
    if len(invites_24h) >= settings.invite_max_per_device_24h:
        return False, f"device_invite_limit_exceeded ({len(invites_24h)})"

    fp_record.last_seen_at = _now()
    fp_record.invite_count = (fp_record.invite_count or 0) + 1
    await db.commit()
    return True, "ok"


async def check_llm_circuit_breaker(
    db: AsyncSession, org_id: str, plan: str
) -> tuple[bool, int, int]:
    """LLM token 超 100% 熔断。返 (allowed, remaining, limit)。"""
    from app.core.rate_limit import PLAN_QUOTAS_TOKENS, QuotaTracker
    tracker = QuotaTracker()
    return await tracker.check_and_consume(org_id, plan, tokens=0)


async def _send_aliyun_sms(phone: str, code: Optional[str], purpose: str) -> bool:
    """真模式: 调阿里云短信 API (dysmsapi.aliyuncs.com)。"""
    if code is None:
        return False
    import hmac
    import base64
    from urllib.parse import quote

    params = {
        "PhoneNumbers": phone,
        "SignName": settings.aliyun_sms_sign_name,
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": json.dumps({"code": code}),
        "AccessKeyId": settings.aliyun_access_key_id,
        "Timestamp": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": secrets.token_hex(16),
        "Action": "SendSms",
        "Version": "2017-05-25",
        "RegionId": settings.aliyun_sms_region,
    }
    sorted_params = "&".join(
        f"{quote(k, safe='')}={quote(str(v), safe='')}"
        for k, v in sorted(params.items())
    )
    string_to_sign = f"GET&%2F&{quote(sorted_params, safe='')}"
    h = hmac.new(
        f"{settings.aliyun_access_key_secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    )
    signature = base64.b64encode(h.digest()).decode("utf-8")
    params["Signature"] = signature
    query_parts = []
    for k, v in params.items():
        query_parts.append(f"{k}={quote(str(v), safe='')}")
    url = "https://dysmsapi.aliyuncs.com/?" + "&".join(query_parts)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        import json
        body = resp.json()
        return body.get("Code") == "OK"
    except Exception:
        return False


import json  # noqa: E402
