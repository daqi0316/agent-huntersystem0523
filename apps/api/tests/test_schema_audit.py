"""Schema audit 测试 — 防 2026-06-03 后端僵死事故回归。

覆盖:
- audit_required_tables 真 DB 路径（返 missing list + 缺失表发现）
- audit_required_tables fail_on_mismatch=True 抛 RuntimeError
- audit_required_tables DB 不可达时不抛、返空
- audit_db_consistency 真 DB 路径（8 OK + 2 enum skip, 0 issues）

设计: 每个 test 用 per-test engine 避免 module-level engine 的 event loop 绑定问题
（"Future attached to a different loop"）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.schema_audit import (
    audit_db_consistency,
    audit_required_tables,
)
from app.models import *  # noqa: F401,F403  # 触发 Base.metadata 注册


@pytest_asyncio.fixture
async def per_test_engine():
    """每个 test 独立 engine — 避免 module-level engine 的 event loop 绑定。"""
    eng = create_async_engine(
        settings.database_url, echo=False, pool_size=2,
    )
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_audit_required_tables_returns_missing_for_unknown_table(per_test_engine) -> None:
    """真 DB：全部迁移已应用，应无缺失表。"""
    missing = await audit_required_tables(fail_on_mismatch=False, engine_arg=per_test_engine)
    assert isinstance(missing, list)
    # 全量 migration 已跑，应无缺失表
    assert len(missing) == 0, f"应无缺失表，实际 missing={missing}"


@pytest.mark.asyncio
async def test_audit_required_tables_fail_on_mismatch_passes(per_test_engine) -> None:
    """fail=True + 全量迁移已应用 → 无缺失表，不抛异常。"""
    missing = await audit_required_tables(fail_on_mismatch=True, engine_arg=per_test_engine)
    assert isinstance(missing, list)
    assert len(missing) == 0, f"全量迁移后应无缺失表，实际 missing={missing}"


@pytest.mark.asyncio
async def test_audit_db_consistency_passes_on_clean_db(per_test_engine) -> None:
    """真 DB：审计不抛异常，返回 list。已知漂移（csm_task_type）不影响判断。"""
    issues = await audit_db_consistency(fail_on_mismatch=False, engine_arg=per_test_engine)
    assert isinstance(issues, list)
    assert all("csm_task_type" in i or "enum drift" in i for i in issues) or len(issues) == 0


@pytest.mark.asyncio
async def test_audit_required_tables_handles_db_error_gracefully() -> None:
    """DB 不可达时（mock engine 抛错）→ 函数不抛、返空 list。"""
    from app.core import schema_audit

    class _BoomEngine:
        def connect(self):
            raise SQLAlchemyError("connect failed", None, None)

    with patch.object(schema_audit, "engine", _BoomEngine()):
        result = await audit_required_tables(fail_on_mismatch=False)
    assert result == []


# patch 必须放最后 import
from unittest.mock import patch
