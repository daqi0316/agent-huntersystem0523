"""RedFlagRule API — 红旗规则 CRUD。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error, success
from app.schemas.red_flag_rule import RedFlagRuleCreate, RedFlagRuleUpdate
from app.services.red_flag_rule import RedFlagRuleService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", status_code=201)
async def create_red_flag_rule(data: RedFlagRuleCreate, db: AsyncSession = Depends(get_db)):
    """创建红旗规则。"""
    rule = await RedFlagRuleService(db).create(data)
    return success({
        "id": rule.id,
        "name": rule.name,
        "scope": rule.scope.value,
        "severity": rule.severity.value,
        "is_active": rule.is_active,
    })


@router.get("")
async def list_red_flag_rules(
    scope: str | None = Query(None),
    is_active: bool | None = Query(None),
    job_profile_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """查询红旗规则列表。"""
    items, total = await RedFlagRuleService(db).list(scope, is_active, job_profile_id, limit, offset)
    return success({
        "items": [{
            "id": r.id,
            "job_profile_id": r.job_profile_id,
            "name": r.name,
            "description": r.description,
            "scope": r.scope.value if r.scope else "",
            "severity": r.severity.value if r.severity else "",
            "condition_config": r.condition_config,
            "is_active": r.is_active,
            "order_index": r.order_index,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        } for r in items],
        "total": total,
    })


@router.get("/{rule_id}")
async def get_red_flag_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个红旗规则。"""
    rule = await RedFlagRuleService(db).get(rule_id)
    if rule is None:
        return error("规则不存在", status_code=404)
    return success({
        "id": rule.id,
        "job_profile_id": rule.job_profile_id,
        "name": rule.name,
        "description": rule.description,
        "scope": rule.scope.value if rule.scope else "",
        "severity": rule.severity.value if rule.severity else "",
        "condition_config": rule.condition_config,
        "is_active": rule.is_active,
        "order_index": rule.order_index,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else "",
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    })


@router.put("/{rule_id}")
async def update_red_flag_rule(rule_id: str, data: RedFlagRuleUpdate, db: AsyncSession = Depends(get_db)):
    """更新红旗规则。"""
    rule = await RedFlagRuleService(db).update(rule_id, data)
    if rule is None:
        return error("规则不存在", status_code=404)
    return success({"id": rule.id, "name": rule.name})


@router.delete("/{rule_id}")
async def delete_red_flag_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """删除红旗规则。"""
    ok = await RedFlagRuleService(db).delete(rule_id)
    if not ok:
        return error("规则不存在", status_code=404)
    return success({"deleted": True})
