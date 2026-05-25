"""设置 API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.setting import Setting
from app.schemas.setting import SettingCreate, SettingRead, SettingUpdate

router = APIRouter()


@router.get("", response_model=list[SettingRead])
async def list_settings(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取所有设置"""
    query = select(Setting)
    if user_id:
        query = query.where(Setting.user_id == user_id)
    query = query.order_by(Setting.key)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{key}", response_model=SettingRead)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """获取单个设置"""
    result = await db.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(404, detail="设置不存在")
    return setting


@router.put("/{key}", response_model=SettingRead)
async def upsert_setting(
    key: str, data: SettingUpdate, db: AsyncSession = Depends(get_db)
):
    """创建或更新设置"""
    result = await db.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = data.value
        await db.commit()
        await db.refresh(setting)
    else:
        setting = Setting(key=key, value=data.value)
        db.add(setting)
        await db.commit()
        await db.refresh(setting)

    return setting


@router.delete("/{key}")
async def delete_setting(key: str, db: AsyncSession = Depends(get_db)):
    """删除设置"""
    result = await db.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(404, detail="设置不存在")

    await db.delete(setting)
    await db.commit()
    return {"success": True, "message": "设置已删除"}
