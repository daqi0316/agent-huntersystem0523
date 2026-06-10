"""RedFlagRule 服务 — CRUD。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.red_flag_rule import RedFlagRule, RedFlagScope, RedFlagSeverity
from app.schemas.red_flag_rule import RedFlagRuleCreate, RedFlagRuleUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RedFlagRuleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: RedFlagRuleCreate) -> RedFlagRule:
        rule = RedFlagRule(
            id=str(uuid.uuid4()),
            job_profile_id=data.job_profile_id,
            name=data.name,
            description=data.description,
            scope=RedFlagScope(data.scope),
            severity=RedFlagSeverity(data.severity),
            condition_config=data.condition_config,
            is_active=data.is_active,
            order_index=data.order_index,
            created_by=data.created_by,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def list(
        self,
        scope: str | None = None,
        is_active: bool | None = None,
        job_profile_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RedFlagRule], int]:
        stmt = select(RedFlagRule)
        count_stmt = select(RedFlagRule.id)

        if scope:
            stmt = stmt.where(RedFlagRule.scope == scope)
            count_stmt = count_stmt.where(RedFlagRule.scope == scope)
        if is_active is not None:
            stmt = stmt.where(RedFlagRule.is_active == is_active)
            count_stmt = count_stmt.where(RedFlagRule.is_active == is_active)
        if job_profile_id:
            stmt = stmt.where(RedFlagRule.job_profile_id == job_profile_id)
            count_stmt = count_stmt.where(RedFlagRule.job_profile_id == job_profile_id)

        count_result = await self.db.execute(count_stmt)
        total = len(count_result.scalars().all())

        stmt = stmt.order_by(RedFlagRule.order_index, RedFlagRule.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get(self, rule_id: str) -> RedFlagRule | None:
        result = await self.db.execute(select(RedFlagRule).where(RedFlagRule.id == rule_id))
        return result.scalar_one_or_none()

    async def update(self, rule_id: str, data: RedFlagRuleUpdate) -> RedFlagRule | None:
        values = data.model_dump(exclude_unset=True)
        if not values:
            return await self.get(rule_id)
        if "severity" in values:
            values["severity"] = RedFlagSeverity(values["severity"])
        if "scope" in values:
            values["scope"] = RedFlagScope(values["scope"])
        values["updated_at"] = _now()
        result = await self.db.execute(
            update(RedFlagRule).where(RedFlagRule.id == rule_id).values(**values).returning(RedFlagRule)
        )
        await self.db.commit()
        return result.scalar_one_or_none()

    async def delete(self, rule_id: str) -> bool:
        result = await self.db.execute(delete(RedFlagRule).where(RedFlagRule.id == rule_id))
        await self.db.commit()
        return result.rowcount > 0
