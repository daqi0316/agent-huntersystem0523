"""统一 API 响应格式工具。

正返回: {"success": true, "data": T}
错误返回: {"success": false, "error": str, "details?": list}
"""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from fastapi.responses import JSONResponse

T = TypeVar("T")


def success(data: T = None) -> dict[str, bool | T]:
    """统一正返回: {"success": True, "data": T}"""
    return {"success": True, "data": data}


def ok_list(items: list[T], total: int, skip: int = 0, limit: int = 20) -> dict:
    """统一分页列表返回: {"success": True, "data": items, "total": ...}"""
    return {
        "success": True,
        "data": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


def error(message: str, status_code: int = 400, details: list | None = None) -> JSONResponse:
    """统一错误返回: {"success": False, "error": str} 并设置状态码。"""
    content: dict[str, Any] = {"success": False, "error": message}
    if details:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


def ok_or_404(result: T | None, detail: str = "资源不存在") -> T:
    """判断查询结果, None → 404, 有值 → 直接返回。"""
    if result is None:
        raise HTTPException(status_code=404, detail=detail)
    return result
