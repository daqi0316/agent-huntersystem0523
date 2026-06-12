"""LLM 管理 API — 多模型接入配置管理。

端点前缀: /api/v1/admin/llm
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal, get_db
from app.llm.admin.crypto import decrypt_api_key, encrypt_api_key, mask_api_key
from app.llm.models.llm_provider import LlmProvider, LlmProviderType
from app.llm.router import get_model_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/llm", tags=["llm-admin"])


# ── Schemas ──


class ProviderCreate(BaseModel):
    name: str = Field(..., max_length=100, description="展示名")
    provider_type: str = Field(..., description="openai_compat / anthropic")
    base_url: str = Field(..., max_length=1024, description="API 端点地址")
    model_name: str = Field(..., max_length=200, description="API 用的模型名")
    api_key: str | None = Field(None, description="API Key（写入时使用）")
    timeout_seconds: int = Field(30, ge=1, le=300)
    max_retries: int = Field(2, ge=0, le=10)
    capabilities: dict = Field(default_factory=lambda: {
        "chat": True, "function_calling": True, "streaming": False,
        "embedding": False, "vision": False,
        "max_context_window": 128000, "max_output_tokens": 4096,
    })
    sort_order: int = Field(100, ge=0)


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    capabilities: dict | None = None
    sort_order: int | None = None
    notes: str | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    model_name: str
    api_key: str | None = None  # 永远 mask
    timeout_seconds: int
    max_retries: int
    capabilities: dict
    is_primary: bool
    is_fallback: bool
    is_active: bool
    sort_order: int
    notes: str | None = None

    model_config = {"from_attributes": True}


class PresetResponse(BaseModel):
    name: str
    provider_type: str
    base_url: str
    model_name: str
    capabilities: dict


# ── 预设列表 ──

PRESETS: list[dict[str, Any]] = [
    {
        "name": "本地 OMLX",
        "provider_type": "openai_compat",
        "base_url": "http://localhost:8000/v1",
        "model_name": "Qwen3.6-35B-A3B-4bit",
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": False,
                         "max_context_window": 128000, "max_output_tokens": 4096},
    },
    {
        "name": "DeepSeek V3",
        "provider_type": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": False, "vision": False,
                         "max_context_window": 128000, "max_output_tokens": 8192},
    },
    {
        "name": "GPT-4o",
        "provider_type": "openai_compat",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": True,
                         "max_context_window": 128000, "max_output_tokens": 16384},
    },
    {
        "name": "Claude Sonnet",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model_name": "claude-sonnet-4-20250514",
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": False, "vision": True,
                         "max_context_window": 200000, "max_output_tokens": 8192},
    },
    {
        "name": "通义千问 Max",
        "provider_type": "openai_compat",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-max",
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": True,
                         "max_context_window": 128000, "max_output_tokens": 8192},
    },
]


# ── 辅助 ──


def _mask_row(row: LlmProvider) -> dict:
    """将 DB 行转为响应 dict（Key 脱敏）。"""
    d = {
        "id": row.id,
        "name": row.name,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "model_name": row.model_name,
        "api_key": mask_api_key(decrypt_api_key(row.api_key_enc)) if row.api_key_enc else None,
        "api_key_configured": row.api_key_enc is not None,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "capabilities": row.capabilities or {},
        "is_primary": row.is_primary,
        "is_fallback": row.is_fallback,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    return d


async def _invalidate_cache():
    """主动失效 Router 缓存。"""
    try:
        router = get_model_router()
        router.invalidate_cache()
    except Exception:
        pass


# ── CRUD 端点 ──


@router.get("/providers")
async def list_providers(db=Depends(get_db)):
    """列出所有 LLM 提供者配置（含预设种子）。"""
    result = await db.execute(
        select(LlmProvider).order_by(LlmProvider.sort_order, LlmProvider.name)
    )
    rows = result.scalars().all()
    return {"providers": [_mask_row(r) for r in rows], "total": len(rows)}


@router.post("/providers", status_code=201)
async def create_provider(data: ProviderCreate, db=Depends(get_db)):
    """新增 LLM 提供者配置。"""
    api_key_enc = encrypt_api_key(data.api_key) if data.api_key else None
    import uuid

    row = LlmProvider(
        id=str(uuid.uuid4()),
        name=data.name,
        provider_type=data.provider_type,
        base_url=data.base_url,
        model_name=data.model_name,
        api_key_enc=api_key_enc,
        key_updated_at=__import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("UTC")) if data.api_key else None,
        timeout_seconds=data.timeout_seconds,
        max_retries=data.max_retries,
        capabilities=data.capabilities,
        sort_order=data.sort_order,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _invalidate_cache()
    return _mask_row(row)


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, data: ProviderUpdate, db=Depends(get_db)):
    """编辑 LLM 提供者配置。"""
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        if update_data["api_key"]:
            row.api_key_enc = encrypt_api_key(update_data["api_key"])
            row.key_salt = None  # 简化：新 Key 对应新 salt
            row.key_updated_at = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("UTC"))
        else:
            row.api_key_enc = None
            row.key_updated_at = None
        del update_data["api_key"]

    for field, value in update_data.items():
        if value is not None:
            setattr(row, field, value)

    await db.commit()
    await db.refresh(row)
    await _invalidate_cache()
    return _mask_row(row)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, db=Depends(get_db)):
    """删除 LLM 提供者配置。"""
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(row)
    await db.commit()
    await _invalidate_cache()


# ── 主备切换 ──


@router.post("/providers/{provider_id}/primary")
async def set_primary(provider_id: str, db=Depends(get_db)):
    """设为主模型。自动取消旧的 primary。"""
    # 检查目标存在
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 事务内操作
    # 1. 取消旧的 primary
    await db.execute(
        update(LlmProvider)
        .where(LlmProvider.is_primary == True)
        .values(is_primary=False)
    )
    # 2. 设置新的 primary
    row.is_primary = True
    # 3. 如果之前是 fallback，取消
    if row.is_fallback:
        row.is_fallback = False

    await db.commit()
    await _invalidate_cache()
    return _mask_row(row)


@router.post("/providers/{provider_id}/fallback")
async def set_fallback(provider_id: str, db=Depends(get_db)):
    """设为备用模型。自动取消旧的 fallback。"""
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.execute(
        update(LlmProvider)
        .where(LlmProvider.is_fallback == True)
        .values(is_fallback=False)
    )
    row.is_fallback = True
    if row.is_primary:
        row.is_primary = False

    await db.commit()
    await _invalidate_cache()
    return _mask_row(row)


@router.post("/providers/{provider_id}/unset")
async def unset_role(provider_id: str, db=Depends(get_db)):
    """取消主/备标记。"""
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    row.is_primary = False
    row.is_fallback = False
    await db.commit()
    await _invalidate_cache()
    return _mask_row(row)


# ── 测试 + 健康 ──


@router.post("/providers/{provider_id}/test")
async def test_connection(provider_id: str, db=Depends(get_db)):
    """测试指定模型的连通性 + Key 有效性。"""
    result = await db.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = decrypt_api_key(row.api_key_enc) if row.api_key_enc else None
    router = get_model_router()
    result = await router.check_connection(
        provider_type=row.provider_type,
        model_name=row.model_name,
        api_key=api_key,
        base_url=row.base_url,
    )
    return result


@router.get("/health")
async def health_check(db=Depends(get_db)):
    """检查所有 active 模型的健康状态。"""
    result = await db.execute(
        select(LlmProvider).where(LlmProvider.is_active == True)
    )
    rows = result.scalars().all()
    router = get_model_router()
    statuses = []
    for row in rows:
        api_key = decrypt_api_key(row.api_key_enc) if row.api_key_enc else None
        try:
            status = await router.check_connection(
                provider_type=row.provider_type,
                model_name=row.model_name,
                api_key=api_key,
                base_url=row.base_url,
            )
        except Exception as e:
            status = {"success": False, "error": str(e)}
        statuses.append({
            "id": row.id,
            "name": row.name,
            "role": "primary" if row.is_primary else "fallback" if row.is_fallback else "inactive",
            **status,
        })
    return {"providers": statuses}


# ── 预设 ──


@router.get("/presets")
async def list_presets():
    """返回可选的预设模板列表。"""
    return {"presets": PRESETS}
