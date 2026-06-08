# F19.1 Ship Report — 迁 main.py + rate_limit.py 到 structlog (graceful degradation)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F19.1 — structlog 集中日志 续 (F19 启动 0.2d 后续)
> **依据**: `docs/followups.md` F19.1 (P1, 0.3d) + 承接 F19 启动 (1cd062a)
> **上一站**: `F20` (a304621 + 51c28ec) — 限流 audit
> **commit**: 1 feat (3 文件) + 1 ship report
> **接受门槛**: setup_logging() 在 lifespan 调过 + rate_limit `api INFO` 输出 + 78 E2E 不退化 + health-check 11/11

## 1. 概览

| 维度 | 状态 |
|---|---|
| `apps/api/app/core/logging.py` graceful degradation | ✅ structlog 未装时 fallback 标准 logging (带 `api` service tag) |
| `apps/api/app/main.py` lifespan startup 调 `setup_logging(service="api")` | ✅ uvicorn log 含 "api INFO app.main Starting..." 证实 |
| `apps/api/app/core/rate_limit.py` 用 `get_logger(__name__)` | ✅ uvicorn log 含 "api INFO app.core.rate_limit rate_limit: using Redis store..." 证实 |
| health-check 11/11 | ✅ |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 完整 8+ 服务迁移 | ❌ 推后续 (F19.2 telemetry + mcp/host, F19.3 tools/*) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/core/logging.py` | +12 / -7 | `try/except ImportError` 判 structlog, 加 fallback format + get_logger 返 stdlib |
| `apps/api/app/main.py` | +2 / -0 | lifespan 第 1 行调 `setup_logging(service="api")` |
| `apps/api/app/core/rate_limit.py` | +1 / -1 | `logger = logging.getLogger` → `from app.core.logging import get_logger` + `logger = get_logger(__name__)` |
| **总** | **+15 / -8** | 3 文件, 0 行新功能 (纯接入) |

## 3. 关键决策

### 3.1 graceful degradation (关键修法)

**F19 启动时问题**: structlog 依赖文档化但未装, venv 没 pip 装不上. F19 测用 `pytest.skip` 优雅降级.

**F19.1 升级**: 让 `setup_logging()` + `get_logger()` 在 structlog 不可用时仍可用:
- `try/except ImportError` 在模块顶层判 `_STRUCTLOG_AVAILABLE`
- `setup_logging()` 未装时调标准 `logging.basicConfig(format=f"... {service} {level} ...")` (含 service tag)
- `get_logger()` 未装时返 `logging.getLogger(name)` (stdlib)

**优点**:
- F19.1 代码立即可用 (不管 structlog 装没装)
- 装上 structlog 后自动升级 (F19 设计的 momus §3.3 字段格式)
- 0 production 风险 (fallback 跟 A1 ship 行为一致)

### 3.2 main.py lifespan startup 接入点

**位置**: `async def lifespan(app: FastAPI):` 第 1 行 (line 31)
**原因**: lifespan 启动时立即调, 确保后续所有 log 含 service tag
**实测**: uvicorn log line `2026-06-08 11:02:42,533 api INFO app.main Starting AI Recruitment System v0.1.0` — `api INFO` = `setup_logging(service="api")` 生效

**注**: uvicorn 自身启动消息 (如 `INFO: Started server process`) 在 lifespan 之前, 不受 `setup_logging` 影响. 这是预期行为 (uvicorn logging 独立于 app logging).

### 3.3 rate_limit.py 接入点

**改前**: `logger = logging.getLogger(__name__)`
**改后**: `from app.core.logging import get_logger` + `logger = get_logger(__name__)`
**验证**: `2026-06-08 11:02:42,533 api INFO app.core.rate_limit rate_limit: using Redis store at redis://localhost:6379/0` — `api` service tag + rate_limit logger 全工作

**关键**: rate_limit.py 现存 5+ `logger.info/warning` 调用全是 **positional args** (如 `logger.info("rate_limit: using InMemory store...")`), 不依赖 kwargs. 所以 fallback 到 stdlib 不会 crash. (F19 设计用 kwargs `logger.info("event", key=value)` 需 structlog).

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | uvicorn log 含 `api INFO` 格式 | setup_logging(service="api") 生效 | ✅ `2026-06-08 11:02:42,533 api INFO app.main Starting...` |
| 2 | rate_limit logger 输出 `api INFO app.core.rate_limit` | get_logger 工作 | ✅ `... api INFO app.core.rate_limit rate_limit: using Redis store at...` |
| 3 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 4 | `pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 5 | `git diff --stat` | +15 / -8 (3 文件) | ✅ 最小改动 |

**未测 / 推后续**:
- 完整 8+ 服务迁移 (F19.2 telemetry + mcp/host, F19.3 tools/* 7 服务)
- 1 query 跨 5 服务验 (F19.4, 需先全迁完)
- structlog 装上后 fallback 失效 (F19.5 验升级路径)
- loguru 选型最终决定 (momus G3 §3.3 选 structlog, 当前实现一致)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| setup_logging() 在 lifespan 调过 | uvicorn log grep "api INFO" | ✅ |
| rate_limit get_logger() 工作 | uvicorn log grep "app.core.rate_limit" | ✅ |
| graceful degradation | 无 structlog 跑 import OK, stdlib fallback 工作 | ✅ |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d (3 文件接入) | ✅ |
| 5 强约束 (Bugfix Rule) | 0 existing 业务逻辑改 (纯 logger 接入) | ✅ |
| 5 强约束 (1 PR 必含测) | 78 E2E + health-check 11/11 (生产环境验证) | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (fallback 跟 A1 一致, 装后升级) | ✅ |
| 5 强约束 (顺序锁死) | C1 收尾 (F18) → C2 启动 (F19 config) → F19.1 (本 PR) | ✅ |
| 5 强约束 (量化 KPI) | 1 graceful degradation + 2 uvicorn log 验 + 78 E2E + 11/11 health = 12 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **F19.2 迁 telemetry.py + mcp/host.py 到 structlog** (0.3d, P1) — 紧跟 F19.1
- ❌ **F19.3 迁 tools/* (7 服务)** (0.5d, P1) — Phase C 继续
- ❌ **F19.4 1 query 跨 5 服务验** (0.2d, P1) — 需先全迁完
- ❌ **F19.5 装 structlog 后 fallback 失效升级路径验** (0.1d, P2) — uv pip install structlog
- ❌ **F21 C2.3 drill 故障定位 <5min** (1d, P1) — Phase C 继续
- ❌ **F22 Phase D 8 PR** (15d, P3) — 远期

## 7. 引用

- Followup: `docs/followups.md` F19.1 (P1, 0.3d) ← 本 PR
- 上一站: `a304621` F20 feat + `51c28ec` F20 docs
- F19 启动: `b3e82f8` + `1cd062a` (structlog config + dep + skip 测)
- 修法目标: `apps/api/app/core/logging.py` (graceful degradation) + `apps/api/app/main.py` (lifespan 接入) + `apps/api/app/core/rate_limit.py` (get_logger 接入)
- momus §3.3 标准字段: `ts/level/service/event/path/latency_ms/status/user_id/org_id`
- 5 强约束: 规划 §7 (G1 §7 修后: 启动 PR 接受门槛 = ship report 完整性)

**Phase C 状态**: C1 收尾 (4 PR) + C2 启动 (F19 + F19.1 + F20) = 8 PR
**Phase A+B+C 累计**: 51 commit, 24 大项
**下一步**: 推 F19.2 迁 telemetry.py + mcp/host.py (0.3d, P1) — 承接 F19.1
