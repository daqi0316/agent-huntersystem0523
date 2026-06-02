"""User memory API — per-user USER.md read/write."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id, get_current_user
from app.core.response import success, error
from app.agents.prompts import load_user_memory, reload_prompts

router = APIRouter()


class UserMemoryResponse(BaseModel):
    content: str
    user_id: str


class UserMemoryUpdate(BaseModel):
    content: str


def _user_memory_path(user_id: str) -> Path:
    settings_dir = os.getenv("SETTINGS_DIR", "./runtime/users")
    return Path(settings_dir) / user_id / "memory.md"


@router.get("/me/memory", response_model=UserMemoryResponse)
async def get_my_memory(user_id: str = Depends(get_current_user_id)):
    """获取当前用户的 memory.md 内容。

    - 仅本人可读
    - 首次访问时自动从模板创建
    - USER_MEMORY_ENABLED=false 时返回 404
    """
    import os
    if os.getenv("USER_MEMORY_ENABLED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="USER_MEMORY_ENABLED=false")

    content = load_user_memory(user_id)
    return UserMemoryResponse(content=content, user_id=user_id)


@router.put("/me/memory", response_model=UserMemoryResponse)
async def update_my_memory(
    data: UserMemoryUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """更新当前用户的 memory.md 内容。

    - 仅本人可写
    - 写入后清除对应缓存
    - USER_MEMORY_ENABLED=false 时返回 404
    """
    import os
    if os.getenv("USER_MEMORY_ENABLED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="USER_MEMORY_ENABLED=false")

    user_file = _user_memory_path(user_id)

    # 确保目录存在
    user_file.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件
    user_file.write_text(data.content, encoding="utf-8")

    # 清除缓存（下次 load_user_memory 重新读取）
    from app.agents.prompts.cache_manager import _cache
    cache_key = f"user:{user_id}"
    _cache.invalidate(cache_key)

    return UserMemoryResponse(content=data.content, user_id=user_id)


@router.get("/{target_user_id}/memory", response_model=UserMemoryResponse)
async def get_user_memory(
    target_user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """管理员读取指定用户的 memory.md（仅读）。

    - admin 角色可读任意用户
    - 普通用户只能读自己（403）
    - USER_MEMORY_ENABLED=false 时返回 404
    """
    import os
    if os.getenv("USER_MEMORY_ENABLED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="USER_MEMORY_ENABLED=false")

    # 权限校验：本人或 admin
    role = current_user.get("role", "")
    if current_user.get("user_id") != target_user_id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅本人或 admin 可读他人 memory",
        )

    content = load_user_memory(target_user_id)
    return UserMemoryResponse(content=content, user_id=target_user_id)
