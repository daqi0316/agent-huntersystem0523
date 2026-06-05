"""P5-1 PR 4 — admin_db engine (BYPASSRLS role, 跨 org 操作专用)。

P1-1 修法: 应用主连接用 airecruit_app (非 superuser, RLS 强制隔离)。
admin 路径用 postgres (BYPASSRLS) — 跨 org aggregate / 平台管理 / 数据迁移。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

admin_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=2,
    max_overflow=2,
    pool_pre_ping=True,
)

AdminSessionLocal = async_sessionmaker(
    admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class AdminBase(DeclarativeBase):
    pass


async def get_admin_db() -> AsyncSession:
    """FastAPI dependency: admin 路径专用, 绕 RLS。"""
    async with AdminSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
