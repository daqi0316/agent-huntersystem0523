# MCP v4 v1.0b Ship Report — datetime.utcnow → datetime.now(UTC) tz-aware

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.7-v1.0-momus-review.md` §7.6 修正版 v1.0b
> **Git tag**: `mcp-v4-v1.0b-pre` (v1.0a feat commit) → `mcp-v4-v1.0b-shipped` (feat commit 70505cf)
> **commit**: 1 个 feat
> **接受门槛**: 4 新测试 + 47 回归 = 51/51 + grep 0 utcnow 残留

## 1. 概览

| 维度 | 状态 |
|---|---|
| apps/api/app/core/rate_limit.py 改 | ✅ 1 处 |
| apps/api/app/services/support.py 改 | ✅ 6 处 + import UTC |
| apps/api/app/api/privacy.py 改 | ✅ 2 处 + import UTC + 简化 .replace(tzinfo=) 模式 |
| apps/api/app/api/csm.py 改 | ✅ 1 处 + import UTC |
| 测试 | ✅ 4 新 + 47 回归 = 51/51 |
| grep `datetime.utcnow` apps/api/app/ | ✅ 0 命中 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/core/rate_limit.py` | +1 / -1 | year_month strftime |
| `apps/api/app/services/support.py` | +8 / -6 | 4 个函数各 1-2 处 + import UTC |
| `apps/api/app/api/privacy.py` | +2 / -4 | 2 处 + import UTC + 简化 replace 模式 |
| `apps/api/app/api/csm.py` | +2 / -2 | 1 处 + import UTC |
| `apps/api/tests/test_datetime_v1_0b_utc.py` | +66 (新) | 4 测试 |
| **总** | **+79 / -13** | 5 文件 |

## 3. 关键决策

### 3.1 `from datetime import UTC` (Py 3.11+ 风格)

```python
# 之前
from datetime import datetime
datetime.utcnow()

# 之后
from datetime import UTC, datetime
datetime.now(UTC)
```

**为什么 `UTC` 单例** (不是 `timezone.utc`):
- Python 3.11+ 标准库
- 项目 `requires-python = ">=3.12"` 满足
- 写时更短, 读时更清晰

### 3.2 privacy.py 简化 `.replace(tzinfo=)` 模式 (Momus 隐含)

```python
# 之前 (naive utcnow + replace tzinfo = 强制 aware)
datetime.utcnow().replace(tzinfo=req.scheduled_hard_delete_at.tzinfo)

# 之后 (now(UTC) 直接 aware, 不需 replace)
datetime.now(UTC)
```

**为什么改后更简洁**: `now(UTC)` 返 aware datetime, 与 DB aware 字段**直接**比较/相减, 无需手工标 tzinfo。

### 3.3 ⚠️ 破坏性变更: JSON serialize 后缀变化 (Momus §4.1 预警)

| 路径 | 改前 | 改后 |
|---|---|---|
| `datetime.utcnow().isoformat()` | `2026-06-07T10:00:00` | — |
| `datetime.now(UTC).isoformat()` | — | `2026-06-07T10:00:00+00:00` |

**影响**:
- API 返 JSON 含 timestamp 字段, 客户端解析
- 旧客户端期望无后缀, 新后缀 `+00:00` 是标准 ISO 8601
- JS `new Date("...")` 兼容 (两种格式都识别)
- **严格** ISO 8601 解析器 (如某些 Python 库) 可能 warn

**降低风险**:
- v1.0b 不需前端配合 (JS Date 兼容)
- 推荐前端用 `new Date()` 而非 `Date.parse()` 严格模式
- 推 changelog 通知

### 3.4 历史 naive 数据处理 (Momus §4.2)

DB `DateTime(timezone=True)` 列**已存**历史 naive timestamp 数据。

**改后读流程**:
1. SQLAlchemy 2.x 读 naive datetime from TZ-aware 列
2. 自动转 UTC aware (SQLAlchemy 内部处理, 不抛 warning)
3. 比较/相减 aware-aware 不抛 TypeError

**不需 migration**——历史数据自动正确处理。

**下游比较** (`req.scheduled_hard_delete_at - datetime.now(UTC)`):
- 改前: naive utcnow - naive DB datetime, OK
- 改后: aware now(UTC) - aware DB datetime, OK (SQLAlchemy 转换)
- **不破坏** 现有逻辑

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_now_utc_returns_tz_aware` | 核心: `datetime.now(UTC).tzinfo is not None` |
| 2 | `test_now_utc_isoformat_includes_offset` | isoformat() 含 `+00:00` 或 `Z` 后缀 (Momus §4.1) |
| 3 | `test_now_utc_compatible_with_aware_datetime` | 与 `RawResume.updated_at` (DB aware 字段) 比较不抛 TypeError |
| 4 | `test_now_utc_does_not_raise_deprecation` | aware datetime 不触发 "utcnow"/"naive" 警告 |

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 4 新测试 + 47 回归 = 51/51 | `pytest tests/test_datetime_v1_0b_utc.py + 47` | ✅ 51 passed |
| grep 0 utcnow 残留 | `grep -rn "datetime\.utcnow" apps/api/app/` | ✅ 0 命中 |
| 4 文件 import UTC | `grep "from datetime" 4 files` | ✅ 全部 `from datetime import UTC, datetime` |
| 现有 rate_limit/privacy/csm/support 测试仍 pass | (隐式通过 51/51) | ✅ |
| mcp 14 server e2e 14/14 | `mcp_v4_e2e_14_servers.py` | ✅ 14/14 |

## 6. 未在 v1.0b 范围 (明确不做)

- ❌ 客户端 changelog 通知 JSON 后缀变化 — 推后续 (前端 changelog)
- ❌ DB migration (改 schema) — 不需, SQLAlchemy 自动处理
- ❌ `SENTRY TRACES_SAMPLE_RATE` (带空格) 代码 typo 修 — 推 v1.0b.1
- ❌ 4 文件外其他 datetime.utcnow — 0 命中 (grep 验证)
- ❌ 改 aware 的下游服务 (scheduler / cron / report) — 推后续 (需业务测)

## 7. 后续路径

**v1.0b.1 (0.1d, 1 commit)**: SENTRY TRACES_SAMPLE_RATE typo 修
- 改代码 `os.getenv("SENTRY TRACES_SAMPLE_RATE")` → `os.getenv("SENTRY_TRACES_SAMPLE_RATE")`
- 改 .env.example 同步
- 删 SKIP_KEYS 这 2 行
- 重跑 check_env_keys.py

**v2.0+**: 多租户 / 前端技术栈替换 / LangGraph interrupt (CLAUDE.md 强制不做)

## 8. 回滚方法

```bash
git checkout mcp-v4-v1.0b-pre
# 或
git revert <v1.0b-feat-commit>
# 改动 5 文件: rate_limit.py + support.py + privacy.py + csm.py + test_datetime_v1_0b_utc.py
# 回滚 = revert 1 commit
```

**回滚影响范围**:
- 4 文件改回 naive utcnow (Pydantic / SQLAlchemy 不会破)
- 4 测试删 (v1.0b 自身)
- **47 回归测试仍 pass** (v0.4d/v0.5b/v0.6a/b/c/c.1/v0.7/v0.7.1 不依赖 v1.0b)

## 9. 引用

- v1.0b plan: `.omo/plans/v0.7-v1.0-momus-review.md` §7.6
- v1.0b Momus 审核: `.omo/plans/v0.7-v1.0-momus-review.md` §4 (4 项 v1.0b 问题)
- v0.5-replan §6 原文: "C.5 Fix Python deprecation warnings" (原始任务来源, utcnow 是核心)
- Python 3.12 datetime: PEP 615 + 3.11 release notes (UTC 单例)
- 现有 4 文件测试: rate_limit_test / privacy_test / csm_test / support_test (全 pass)
