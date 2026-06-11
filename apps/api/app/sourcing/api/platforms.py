"""平台配置 + 账号管理 API (P0-9)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.sourcing.platforms.base import invalidate_platform_config_cache
from app.sourcing.schemas.platform import (
    AccountCreate,
    AccountResponse,
    PlatformConfigResponse,
    PlatformConfigUpdate,
)

router = APIRouter(prefix="/platforms", tags=["sourcing/platforms"])


# ── 平台配置 ──


@router.get("")
async def list_platforms():
    from app.sourcing.models.platform_config import PlatformConfig
    from app.sourcing.platforms.base import list_adapters

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PlatformConfig))
        configs = result.scalars().all()

    adapters = {a["name"]: a for a in list_adapters()}
    data = []
    for c in configs:
        item = PlatformConfigResponse.model_validate(c).model_dump()
        meta = adapters.get(c.name, {})
        item["category"] = meta.get("category", c.category)
        item["anti_crawl_level"] = meta.get("anti_crawl_level", c.anti_crawl_level)
        data.append(item)
    return {"success": True, "data": data}


@router.get("/{platform}")
async def get_platform_config(platform: str):
    from app.sourcing.models.platform_config import PlatformConfig

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PlatformConfig).where(PlatformConfig.name == platform))
        config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="平台不存在")
    return {"success": True, "data": PlatformConfigResponse.model_validate(config).model_dump()}


@router.patch("/{platform}")
async def update_platform_config(platform: str, body: PlatformConfigUpdate):
    from app.sourcing.models.platform_config import PlatformConfig

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PlatformConfig).where(PlatformConfig.name == platform))
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="平台不存在")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
    # 热加载：使缓存失效，下次 adapter 实例化自动取新配置
    await invalidate_platform_config_cache()
    return {"success": True, "data": PlatformConfigResponse.model_validate(config).model_dump()}


# ── 账号管理 ──


@router.get("/{platform}/accounts")
async def list_accounts(platform: str):
    from app.sourcing.models.platform_account import PlatformAccount

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PlatformAccount).where(PlatformAccount.platform == platform)
        )
        accounts = result.scalars().all()
    return {
        "success": True,
        "data": [AccountResponse.model_validate(a).model_dump() for a in accounts],
    }


@router.post("/{platform}/accounts", status_code=201)
async def create_account(platform: str, body: AccountCreate):
    from app.sourcing.models.platform_account import PlatformAccount

    async with AsyncSessionLocal() as db:
        account = PlatformAccount(
            platform=platform,
            display_name=body.display_name,
            account_type=body.account_type,
            encrypted_cookies=body.encrypted_cookies,
            cookie_expires_at=body.cookie_expires_at,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
    return {"success": True, "data": AccountResponse.model_validate(account).model_dump()}
