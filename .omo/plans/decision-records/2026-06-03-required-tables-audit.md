# ADR-2026-06-03: 启动期必需表审计（audit_required_tables）

> **相关**：2026-06-03 后端僵死事故，事故背景与防护层级见
> `2026-06-03-enum-and-uuid-pattern.md`。本 ADR 聚焦"必需表审计"的设计。

## Context

L1+L2 已修 `operation_stats_hourly` 缺失表问题（具体见
`l3-polish.md` 之前的 fix commits）。

L3 启动期 audit（`audit_required_tables`）设计为**通用**检查所有 model 表：
dev 当前还缺 `interview_evaluations`（audit 实际发现），未来可能有更多。

## Decision

### 1. 表缺失不阻止启动（默认 `fail_on_mismatch=False`）

**对照** `audit_db_consistency`（默认 `fail_on_mismatch=True`）：

| 维度 | enum drift | 表缺失 |
|---|---|---|
| 必爆 500？ | 是（写库时强转失败） | 否（dashboard 端点 L1 优雅降级） |
| L1 兜底？ | 无（无 try/except 防护） | 有（dashboard.py try/except + L1.3 启动检查） |
| 严重度 | 高（生产立即 500） | 中（dev 可见，prod 也不爆） |
| 默认 fail？ | True | **False** |

**两 audit 默认值不同是有意设计**，非不一致。enum drift 无兜底故必须 fail；
表缺失有多层 L1 兜底故 warn 即可。

### 2. 健康检查端点 `/api/v1/health/schema` 永远 200

```
成功 → status="ok"
缺失表 / enum drift → status="degraded"（debug 模式返 details）
audit 自身抛错 → status="degraded", error="audit_unavailable"
```

**绝不返 500**：防止 health 端点本身崩溃复现"无法连接后端服务"问题
（2026-06-03 用户报告的同类现象）。

**信息粒度**：
- `settings.debug=True`：返 `missing_tables` + `enum_drift` 完整列表
- 生产模式：仅返 `status` 字段（不暴露内部状态）

### 3. 引擎可注入（`engine_arg` 参数）

`audit_required_tables` 和 `audit_db_consistency` 都接受 `engine_arg=None`：
- 默认 None：使用 module-level `engine`（生产路径）
- 测试传 `engine_arg=per_test_engine`：避免 pytest-asyncio event loop 绑定问题

**Why not 重构 module-level engine？** 改了会破坏 lifespan 主路径。
注入是最小侵入做法。

## Why Not Default-Fail (Production)

考虑过 `audit_required_tables(fail_on_mismatch=True)` 作为生产默认，
但：
- 表缺失**不**是 500 触发器（不像 enum drift）
- 强制 fail 会**阻塞**所有 dev / staging 实例启动
- L1 兜底已覆盖生产风险

未来如果某张**关键**表缺失且无 L1 兜底，**显式传 True** 即可，不需改默认。

## Layer of Defense

| 层 | 工具 | 状态 |
|---|---|---|
| L1 编译期 | `scripts/check_model_patterns.py` | ✅ |
| L2 启动期 enum | `audit_db_consistency` | ✅（fail=True） |
| L2 启动期 表 | `audit_required_tables` | ✅（fail=False） |
| L3 优雅降级 | dashboard.py try/except | ✅ |
| L3 启动检查 | aggregation_loop 启动 check | ✅ |
| L4 健康检查 | `/api/v1/health/schema` | ✅（本 ADR） |
| L5 测试 | `tests/test_schema_audit.py` | ✅（4 个测试） |
| L6 监控 | 业务/运维层 Prometheus | 未来 work |

## References

- `.omo/plans/decision-records/2026-06-03-enum-and-uuid-pattern.md` — 兄弟 ADR
- `.omo/plans/l3-polish.md` — 本 ADR 的 plan
- `app/core/schema_audit.py::audit_required_tables` — 实现
- `app/core/schema_audit.py::audit_db_consistency` — 兄弟实现
- `app/api/health.py` — M2 新建
- `tests/test_schema_audit.py` — M3 新建
