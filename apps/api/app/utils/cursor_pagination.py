"""Cursor-based pagination utility for SQLAlchemy async queries.

替代 ``offset``/``limit`` 分页（大偏移量性能差），改用 keyset pagination：
- 第一页：无 cursor，按排序列取 ``page_size`` 条
- 后续页：传上一页最后一条的排序列值作为 ``cursor``
- 返回 ``next_cursor``（base64 编码）供下一页使用

用法::

    from app.utils.cursor_pagination import CursorPage, paginate_asc, paginate_desc

    # 按 created_at 降序列出候选人
    query = select(Candidate).where(Candidate.org_id == org_id)
    page = await paginate_desc(db, query, Candidate.created_at, page_size=20, cursor=cursor)
    return {"items": page.items, "next_cursor": page.next_cursor, "has_more": page.has_more}
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnExpressionArgument, asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


@dataclass
class CursorPage(Generic[T]):
    """游标分页结果。"""
    items: list[T] = field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


def encode_cursor(value: Any) -> str:
    """将游标值编码为 base64。"""
    raw = json.dumps(value, default=str)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> Any:
    """从 base64 解码游标值。"""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


async def paginate_asc(
    db: AsyncSession,
    query: Any,
    sort_column: ColumnExpressionArgument,
    page_size: int = 20,
    cursor: str | None = None,
    total: int | None = None,
) -> CursorPage[T]:
    """按升序游标分页。

    Args:
        db: AsyncSession
        query: 已附加 WHERE 条件的 select() 语句
        sort_column: 排序列（如 ``Candidate.created_at``）
        page_size: 每页条数
        cursor: 上一页返回的 next_cursor（首页为 None）
        total: 总数（可选，避免 COUNT 查询）

    Returns:
        CursorPage[T]
    """
    if cursor:
        cursor_val = decode_cursor(cursor)
        if cursor_val is not None:
            query = query.where(sort_column > cursor_val)

    query = query.order_by(asc(sort_column)).limit(page_size + 1)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    has_more = len(rows) > page_size
    items = rows[:page_size]
    next_cursor = None
    if has_more and items:
        last_val = getattr(items[-1], sort_column.name if hasattr(sort_column, "name") else "id")
        next_cursor = encode_cursor(last_val)

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more, total=total)


async def paginate_desc(
    db: AsyncSession,
    query: Any,
    sort_column: ColumnExpressionArgument,
    page_size: int = 20,
    cursor: str | None = None,
    total: int | None = None,
) -> CursorPage[T]:
    """按降序游标分页。

    Args:
        db: AsyncSession
        query: 已附加 WHERE 条件的 select() 语句
        sort_column: 排序列（如 ``Candidate.created_at``）
        page_size: 每页条数
        cursor: 上一页返回的 next_cursor（首页为 None）
        total: 总数（可选）

    Returns:
        CursorPage[T]
    """
    if cursor:
        cursor_val = decode_cursor(cursor)
        if cursor_val is not None:
            query = query.where(sort_column < cursor_val)

    query = query.order_by(desc(sort_column)).limit(page_size + 1)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    has_more = len(rows) > page_size
    items = rows[:page_size]
    next_cursor = None
    if has_more and items:
        last_val = getattr(items[-1], sort_column.name if hasattr(sort_column, "name") else "id")
        next_cursor = encode_cursor(last_val)

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more, total=total)
