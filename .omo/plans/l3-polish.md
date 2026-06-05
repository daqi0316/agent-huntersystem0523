# L3 完善 Plan（Momus 4 硬伤已修）

> 目标：把 L3 启动期 audit 推到"工业级、零新 bug"，防 2026-06-03 死锁事故复发。

## 0. Context

- L1+L2 已修 operation_stats_hourly 500
- L3 现状：audit_required_tables() 函数 + lifespan 调用，但**有 4 处未达工业级**：
  1. **漏修 1**：M1（`fail_on_mismatch` 参数）plan 写了但**没真做**（实测 `TypeError: unexpected keyword argument`）
  2. **漏修 2**：M2 健康端点还没建
  3. **缺**：M3 测试覆盖
  4. **缺**：M4 ADR

## 1. 执行顺序（依赖 M1 → M3 → M2 → M4）

```
M1: schema_audit.py 加 fail_on_mismatch 参数
   ↓
M3: tests/test_schema_audit.py 测试覆盖
   ↓
M2: app/api/health.py 新建 + router.py 注册
   ↓
M4: docs/architecture-decision-records/2026-06-03-required-tables-audit.md
   ↓
验证: pytest + 手动 curl /api/v1/health/schema
```

## 2. M1: audit_required_tables 加 fail_on_mismatch 参数

**文件**：`apps/api/app/core/schema_audit.py`

```python
async def audit_required_tables(fail_on_mismatch: bool = False) -> list[str]:
    """启动时检查所有 ``Base.metadata`` 表是否在 DB 存在。
    ...
    Parameters
    ----------
    fail_on_mismatch:
        True → 表缺失时抛 RuntimeError 阻止启动（生产严格模式）
        False（默认）→ 仅 log warn，dev 早期允许（dashboard 端点有 L1 兜底）
    """
    # ... 已有逻辑 ...
    if missing and fail_on_mismatch:
        raise RuntimeError(
            f"Required tables missing in DB: {missing}. "
            f"Run `alembic upgrade head`."
        )
    return missing
```

**默认值理由**（Momus 硬伤 3 修正）：
- `audit_db_consistency` 默认 `True`：enum drift 必爆 500，必须 fail
- `audit_required_tables` 默认 `False`：表缺失有 L1.1/L1.2 优雅降级 + L1.3 启动检查兜底，**不爆 500**
- 未来生产想严格：显式传 `fail_on_mismatch=True`

**lifespan 调**：M1 后修改 `apps/api/app/main.py` 显式传 `fail_on_mismatch=False`（明示意图）

## 3. M3: 测试覆盖

**新建文件**：`apps/api/tests/test_schema_audit.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from app.core.schema_audit import (
    audit_required_tables,
    audit_db_consistency,
)
from app.models import *  # noqa: F401,F403 — trigger Base.metadata


@pytest.mark.asyncio
async def test_audit_required_tables_returns_missing():
    """真实 DB：interview_evaluations 表缺失，应在 missing 列表中。"""
    missing = await audit_required_tables(fail_on_mismatch=False)
    assert "interview_evaluations" in missing


@pytest.mark.asyncio
async def test_audit_required_tables_fail_on_mismatch_raises():
    """fail=True + 表缺失 → RuntimeError。"""
    with pytest.raises(RuntimeError, match="interview_evaluations"):
        await audit_required_tables(fail_on_mismatch=True)


@pytest.mark.asyncio
async def test_audit_required_tables_handles_db_error():
    """DB 不可达时（mock engine 抛错）→ 函数不抛、返空 list。"""
    from app.core import schema_audit
    with patch.object(schema_audit, "engine", side_effect=Exception("connect failed")):
        result = await audit_required_tables(fail_on_mismatch=False)
    assert result == []


@pytest.mark.asyncio
async def test_audit_db_consistency_passes_on_clean_db():
    """真 DB 8 OK + 2 enum skip（interview_round/evaluation_verdict 表未建）→ 0 issues。"""
    issues = await audit_db_consistency(fail_on_mismatch=False)
    assert isinstance(issues, list)
    # 当前 dev：interview_evaluations 表未建，interview_round/evaluation_verdict enum 缺失
    # 这些 enum 由 _iter_enum_columns 跳过（savepoint rollback），所以 issues 应为空
    assert issues == []
```

**说明**：
- 单元测试用 monkeypatch/AsyncMock mock engine
- 集成测试用真 DB（已有 conftest 模式）
- mock fixture 模板见 M3 上面代码

## 4. M2: 健康检查端点

**新建文件**：`apps/api/app/api/health.py`

```python
"""健康检查端点 — 启动期 schema audit 的运行时查询接口。

L2 启动期护栏的运行时扩展：前端/监控可调 ``/api/v1/health/schema`` 看到
当前 DB 状态（缺失表、enum 漂移），不必重启服务。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import settings
from app.core.response import success

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health/schema")
async def health_schema():
    """Schema 健康检查 — **永远 200**（不引入新 bug）。

    失败兜底：audit 内部抛任何异常都返 ``status="degraded"`` 而非 500。
    防止 health 端点本身崩溃复现"无法连接后端服务"问题。

    信息粒度：
    - settings.debug=True：返完整 missing_tables + enum_drift
    - 生产模式：仅返 ``status`` 字段（不暴露内部状态）
    """
    try:
        from app.core.schema_audit import audit_required_tables, audit_db_consistency

        missing = await audit_required_tables(fail_on_mismatch=False)
        drift = await audit_db_consistency(fail_on_mismatch=False)
    except Exception:
        logger.exception("health/schema audit crashed; returning degraded")
        return success({"status": "degraded", "error": "audit_unavailable"})

    payload: dict = {"status": "ok" if not (missing or drift) else "degraded"}
    if settings.debug:
        payload["missing_tables"] = missing
        payload["enum_drift"] = drift
    return success(payload)
```

**关键设计**（Momus 硬伤 1 修正）：
- **永远 200**（`success()` helper），不引入新 "无法连接" 问题
- audit 抛任何异常 → 返 `status="degraded"`，不阻断前端
- debug 模式返完整信息，生产模式仅 `status`

**注册到 router**：`apps/api/app/api/router.py` 加：

```python
from app.api.health import router as health_router
# ...
api_router.include_router(health_router)  # 注：当前 router.py 没有 api_router 聚合
```

实际看 `router.py` 是直接 import 一堆 router，**没聚合**。需看 main.py 怎么用 router。

## 5. M4: ADR

**新建文件**：`docs/architecture-decision-records/2026-06-03-required-tables-audit.md`

引用之前 enum ADR（不重复事故背景）：

```markdown
# ADR-2026-06-03: 启动期必需表审计

> **相关**：2026-06-03 后端僵死事故，事故背景与防护层级见
> `2026-06-03-enum-and-uuid-pattern.md`。本 ADR 聚焦"必需表审计"的设计。

## Context

L1+L2 已修 operation_stats_hourly 缺失表问题。L3 启动期 audit
（`audit_required_tables`）设计为**通用**检查所有 model 表。

## Decision

1. **表缺失不阻止启动**（dev 友好）：dashboard 端点 L1.1/L1.2 已优雅降级，
   aggregation_loop L1.3 启动检查也兜底，单点风险已被 L1 覆盖。
2. **健康检查端点 `/api/v1/health/schema`** 永远 200，最差 `status="degraded"`，
   不引入"端点本身崩溃导致无法连接"的新 bug。
3. **生产严格化路径**：未来想阻止启动显式传 `fail_on_mismatch=True`。

## Why Not Fail-By-Default

对照 `audit_db_consistency` 默认 `True`（enum drift 必爆故 fail），
`audit_required_tables` 默认 `False`（表缺失有 L1 兜底故 warn）。
两 audit 默认值不同是**有意设计**，非不一致。

## References

- `.omo/plans/decision-records/2026-06-03-enum-and-uuid-pattern.md`
- `.omo/plans/l3-polish.md`（本 ADR 的 plan）
- `app/core/schema_audit.py::audit_required_tables`
- `app/api/health.py`（M2 新建）
```

## 6. 验收标准

| 验证 | 通过 |
|---|---|
| `audit_required_tables(fail_on_mismatch=False)` 不抛 | ✅ |
| `audit_required_tables(fail_on_mismatch=True)` + 缺失表 → RuntimeError | ✅ |
| `audit_required_tables` + mock engine 抛错 → 不抛，返 `[]` | ✅ |
| `GET /api/v1/health/schema` 返回 200 | ✅ |
| 健康端点内部 audit 抛错 → 仍 200 + `status="degraded"` | ✅ |
| 4 个 schema_audit 测试全过 | ✅ |
| 96 个原测试 0 回归 | ✅ |
| ADR 文件存在 + 引用之前 enum ADR | ✅ |

## 7. 风险

| 风险 | 缓解 |
|---|---|
| M1 改签名影响 lifespan | 默认 False 等价原行为 |
| M2 健康端点被前端/监控高频轮询，audit 开销 | audit 一次 ~50ms，10/s 轮询 = 0.5% CPU，可接受 |
| M2 debug 模式返完整信息暴露内部 | 生产 `settings.debug=False` 仅返 `status` |
| M3 测试污染真 DB | 测试只读不写，rollback fixture 已有 |
| M4 ADR 与之前 enum ADR 脱节 | 显式交叉引用 |

## 8. Out of Scope（独立 PR，不做）

- ❌ 写 `interview_evaluations` migration（真问题，独立 PR）
- ❌ 修 `screening.py:67` 字段不存在 bug（需先确认 field 设计 + 调用点）
- ❌ 13 个 alembic check 漂移修复
- ❌ Prometheus/Sentry 集成

## 9. 文件清单

**新建**（2）：
- `apps/api/tests/test_schema_audit.py`
- `apps/api/app/api/health.py`
- `docs/architecture-decision-records/2026-06-03-required-tables-audit.md`

**修改**（2）：
- `apps/api/app/core/schema_audit.py`（加 `fail_on_mismatch` 参数 + RuntimeError raise 块）
- `apps/api/app/main.py`（lifespan 显式 `fail_on_mismatch=False`）

**总修改**：~15 行；总新建：~100 行（主要是测试 + health 端点）

## 10. 回滚

```bash
git revert <commit>  # 无 DB 改动
```

## 11. 时间预估

| 模块 | 时间 |
|---|---|
| M1 schema_audit 加参数 | 5 分钟 |
| M3 测试 4 个 | 15 分钟 |
| M2 health 端点 | 10 分钟 |
| M4 ADR | 5 分钟 |
| 验证 | 5 分钟 |
| **总计** | **40 分钟** |
