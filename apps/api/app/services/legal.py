"""P5-9: 法务协议 — 模板查询 + 接受记录 + 必勾校验。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    CURRENT_VERSIONS,
    AgreementType,
    LegalAcceptance,
)

import logging
logger = logging.getLogger(__name__)


class LegalError(Exception):
    pass


def get_current_version(agreement_type: AgreementType) -> str:
    return CURRENT_VERSIONS[agreement_type]


def get_required_agreements(user_context: Optional[dict] = None) -> list[dict]:
    """返回必勾的协议清单 (注册时 ToS + PP 必勾, DPA 仅跨境/企业客户必勾)。"""
    items = [
        {
            "type": AgreementType.TERMS_OF_SERVICE.value,
            "version": CURRENT_VERSIONS[AgreementType.TERMS_OF_SERVICE],
            "title": "服务条款 (ToS)",
            "url": "/legal/terms-of-service",
            "required": True,
        },
        {
            "type": AgreementType.PRIVACY_POLICY.value,
            "version": CURRENT_VERSIONS[AgreementType.PRIVACY_POLICY],
            "title": "隐私政策 (PP)",
            "url": "/legal/privacy-policy",
            "required": True,
        },
    ]
    is_cross_border = user_context and user_context.get("cross_border", False)
    is_enterprise = user_context and user_context.get("enterprise", False)
    if is_cross_border or is_enterprise:
        items.append({
            "type": AgreementType.DATA_PROCESSING_AGREEMENT.value,
            "version": CURRENT_VERSIONS[AgreementType.DATA_PROCESSING_AGREEMENT],
            "title": "数据处理协议 (DPA)",
            "url": "/legal/data-processing-agreement",
            "required": True,
        })
    return items


async def record_acceptance(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: str,
    agreement_type: AgreementType,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> LegalAcceptance:
    """记录用户接受协议 (用当前版本)。"""
    version = CURRENT_VERSIONS[agreement_type]
    existing = (await db.execute(
        select(LegalAcceptance).where(
            LegalAcceptance.user_id == user_id,
            LegalAcceptance.agreement_type == agreement_type,
            LegalAcceptance.version == version,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    acc = LegalAcceptance(
        org_id=org_id,
        user_id=user_id,
        agreement_type=agreement_type,
        version=version,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(acc)
    await db.flush()
    return acc


async def get_user_acceptances(db: AsyncSession, user_id: str) -> list[LegalAcceptance]:
    rows = (await db.execute(
        select(LegalAcceptance)
        .where(LegalAcceptance.user_id == user_id)
        .order_by(LegalAcceptance.accepted_at.desc())
    )).scalars().all()
    return list(rows)


async def has_required_acceptances(
    db: AsyncSession,
    user_id: str,
    required_types: list[AgreementType],
) -> dict:
    """检查用户是否接受了所有必勾协议。"""
    accepted = set()
    rows = (await db.execute(
        select(LegalAcceptance.agreement_type, LegalAcceptance.version)
        .where(LegalAcceptance.user_id == user_id)
    )).all()
    for row in rows:
        atype, ver = row[0], row[1]
        if ver == CURRENT_VERSIONS.get(atype):
            accepted.add(atype)
    missing = [t for t in required_types if t not in accepted]
    return {
        "all_accepted": len(missing) == 0,
        "accepted": [t.value for t in accepted],
        "missing": [t.value for t in missing],
        "required": [t.value for t in required_types],
    }


def serialize_acceptance(acc: LegalAcceptance) -> dict:
    return {
        "id": acc.id,
        "agreement_type": acc.agreement_type.value,
        "version": acc.version,
        "accepted_at": acc.accepted_at.isoformat() if acc.accepted_at else None,
        "ip_address": acc.ip_address,
    }
