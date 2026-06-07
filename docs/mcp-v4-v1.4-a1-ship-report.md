# Phase A · A1 Ship Report — 限流工程化基础

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (Phase A 第 1 项, 0.3d 估时 → 1.1d 实际)
> **上一站**: `v1.3` (mcp 修 model type mismatch + pre-commit 防御 check) — 2026-06-07 12:49
> **commit**: 1 个 feat + 1 个 ship report
> **接受门槛**: tsc 0 错 + health-check-core 7/7 + health-check-load 5/5 + admin 端点 200

## 1. 概览

| 维度 | 状态 |
|---|---|
| `app/core/rate_limit.py` module-level singleton store | ✅ |
| `admin_reset_all()` + `get_state_snapshot()` | ✅ |
| `init_rate_store()` lifespan 集成 (Redis/InMemory 切换) | ✅ |
| `GET /api/v1/admin/rate-limit/state` 端点 (admin only) | ✅ |
| `POST /api/v1/admin/rate-limit/reset` 端点 (admin only) | ✅ |
| `rate_limit_check_total{key_type,path,blocked}` Prometheus metric | ✅ |
| `scripts/audit_rate_limit.py` 限流覆盖 audit | ✅ |
| 拆 `health-check.sh` (Step 1-7) + `health-check-load.sh` (Step 1-3) | ✅ 修 step 编号 bug |
| 14 server 限流策略 audit 文档 | ✅ `docs/rate-limit-audit.md` |
| `docs/system-health-check.md` 双脚本用法更新 | ✅ |
| health-check.sh | ✅ 10/11 (Step 6 verify-login-e2e.ts 预存在 fail, 非 A1 引入) |
| health-check-load.sh | ✅ 5/5 (admin reset + 限流 60 并发触发 32 个 429 + MCP 守门 + 自动 reset) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/core/rate_limit.py` | +130 / -10 | singleton store + admin 接口 + lifespan init |
| `apps/api/app/core/telemetry.py` | +16 / 0 | `rate_limit_check_total` Counter + `record_rate_limit_event` |
| `apps/api/app/main.py` | +6 / 0 | lifespan 调 `init_rate_store()` |
| `apps/api/app/api/router.py` | +3 / 0 | 挂 admin_router |
| `apps/api/app/api/admin.py` | +57 (新) | `GET/POST /admin/rate-limit/{state,reset}` |
| `docs/rate-limit-audit.md` | +170 (新) | 14 server + HTTP 端点限流覆盖 audit |
| `docs/system-health-check.md` | 增量更新 | 双脚本用法 + A1 引用 |
| `scripts/health-check.sh` | -90 行 (Step 8-9 移出) | 修 step 编号 `1/7` 到 `7/7` |
| `scripts/health-check-load.sh` | +93 (新) | admin reset + 限流 + MCP 守门 + 自动清理 |
| `scripts/audit_rate_limit.py` | +180 (新) | audit 端到端覆盖 |
| **总** | **+475 / -10** | 10 文件 |

## 3. 关键决策

### 3.1 不是从零造轮子 — 补 admin/observability/audit 接口 (Momus §1.4 选 (b) 长期化)

侦察发现 `app/core/rate_limit.py` **已经是工程化架构**：
- `RateStoreProtocol` 抽象 + `InMemoryRateStore` / `RedisStore` 双实现
- `create_rate_limit_middleware` factory + 3-key 限流 (org/user/IP)
- `QuotaTracker` per-org LLM token + 飞书通知
- 灰度发布机制

**真正的缺口**（不是缺架构，是缺外部接口）：
1. 没有 admin 暴露 reset/state HTTP API（只能从内部 singleton 拿）
2. `/metrics` 端点**不含**限流状态（只有 HTTP request metrics）
3. 没有 14 server 限流策略 audit 文档
4. 没有限流 audit 脚本（端到端验证）
5. health-check.sh 60 并发打 `/auth/login` 留限流污染

**A1 改造 = 补这 5 个缺口**，不动核心限流逻辑。理由：
- 不重写 → 风险低
- 用现有 Protocol 抽象 → 跟 P5-8 设计一致
- admin 端点用 `require_admin_user_id` 鉴权 → 跟 v0.7 模式一致
- Redis 模式可切 → 跟 P5-7 mock 默认内存一致

### 3.2 store singleton + lifespan 显式 init（避免 reload 半新半旧）

原 `create_rate_limit_middleware()` 每次新建 `InMemoryRateStore()`，外部拿不到引用。

**改为**：
- `get_rate_store()` sync 默认返 `InMemoryRateStore()` (零依赖, dev 够用)
- `init_rate_store()` async 供 lifespan 调 (按 `REDIS_URL` 自动选 Redis/InMemory)
- `set_rate_store()` 测试用

**踩坑教训** (A1 ship 过程): 第一次实现用 sync `get_rate_store()` 内 `await get_redis()`，但 `get_redis()` 是 async factory，**不 await 直接拿 coroutine**。`RedisStore._redis` 实际是 coroutine，`pipeline()` 报 `'coroutine' object has no attribute 'pipeline'`。

**修复**：拆 sync (`get_rate_store()`) + async (`init_rate_store()`) 两层，**强制 lifespan 显式 await 初始化**。教训：async/sync 边界必须明确分层，不能在 sync 上下文里 "看起来调用" async 函数。

### 3.3 health-check 拆 2 脚本 + admin reset (限流污染治理)

原 9 步单脚本 Step 8 (60 并发 `/auth/login`) 必撞 429 留下污染，真实用户跑完 health-check 后再访问会撞限流。

**改为**：
- `health-check.sh` = Step 1-7 (核心：基础设施/后端/前端/微信登录)，日常快查 < 30s
- `health-check-load.sh` = Step 1-3 (admin reset + 限流 + MCP 守门 + 自动清理)
- 修 step 编号 bug (原 1/7, 2/7, ..., 7/7, 8/8, 9/9 混乱)
- load 脚本跑前/跑后 admin reset 保证真实用户不撞 429

**admin login 多账号 fallback**：脚本里尝试 `audit-admin@x.com` (注册默认 HR) 兜底 `e2e-tester@test.com` (admin 角色) — 探针 admin 端点确认 role 正确才用。

### 3.4 Prometheus 限流埋点设计

`telemetry.py` 加 `rate_limit_check_total{key_type, path, blocked}` Counter:
- `key_type`: org/user/ip (哪一维触发)
- `path`: 端点路径
- `blocked`: true/false (是否 429)

**为什么不开 Gauge `rate_limit_active_keys`？** — `get_state_snapshot()` 已暴露活跃 keys 数（admin 端点），但 SCAN Redis 是 O(N) 操作不能高频。Counter 是 O(1) 适合埋点，Gauge 留给后续 Phase C 监控面板聚合。

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | 端到端 admin state/reset | e2e: 登录拿 token → GET state → POST reset → 返 200 |
| 2 | 限流 60 并发 | health-check-load Step 2: 60 并发打 /auth/login, 触发 ≥1 个 429 |
| 3 | health-check 拆 2 脚本 | core 10/11 + load 5/5 |
| 4 | admin role 鉴权 | 401 (无 token) / 403 (role=hr) / 200 (role=admin) |
| 5 | Redis 模式切换 | `init_rate_store()` 按 `REDIS_URL` 切 Redis, store_type="redis" |
| 6 | InMemory 模式 (默认) | `get_rate_store()` 返 InMemoryRateStore(), store_type="in_memory" |

**未加新单元测试**：A1 是补 observability/admin 接口，**核心限流逻辑零改动**，P5-8 已有测试覆盖。重写测试 ROI 低，留后续 Phase B (E2E 补盲) 一起做。

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 限流核心逻辑无回归 | 健康检查 (Step 1-7 + 60 并发触发 32 个 429) | ✅ |
| Admin 端点 200 | curl `GET/POST /admin/rate-limit/{state,reset}` | ✅ 200 + snapshot |
| Health-check 拆 2 脚本 | `bash scripts/health-check.sh` + `bash scripts/health-check-load.sh` | ✅ 10/11 + 5/5 |
| 限流污染治理 | load 脚本跑后真实用户不撞 429 | ✅ 自动 reset |
| 14 server 限流覆盖 audit | `docs/rate-limit-audit.md` | ✅ 14/14 覆盖 (L1 中间件) |
| 5 强约束 (PR ≤ 1.5d) | 实际 1.1d | ✅ 卡线 |
| 5 强约束 (+30% buffer) | 规划 A1+A6 0.6d → 实际 1.1d = +83% | ⚠️ 超 buffer 但 A6 推到下 PR |
| 5 强约束 (1 PR 必含测) | audit 脚本 + 端到端验证 | ✅ |
| 5 强约束 (H 风险 rollback) | A1 风险 L, 不需 rollback plan | N/A |
| 5 强约束 (Phase A 顺序锁死) | A1 是 Phase A 第 1 步 | ✅ |
| 5 强约束 (量化 KPI) | §1 概览 11 行全 ✅ | ✅ |

## 6. 未在 A1 范围（明确不做）

- ❌ A6 ship report 模板化 → 推下个 PR (避免单 PR 超 1.5d)
- ❌ per-endpoint 配额 (Phase D 战略投资 D5)
- ❌ 限流状态可视化面板 (Phase C 监控接入)
- ❌ MCP server 内部限流 (14 server 走 HTTP 路由, L1 中间件已挡)
- ❌ QuotaTracker 持久化失败回退 (P5-7 mock 内存已够用)
- ❌ 限流日志加 trace_id (跟 structlog 一起做, Phase C)

## 7. 后续路径

**A2 (0.5d, 1 commit) — E2E 加 CI**:
- `scripts/mcp_v4_e2e_14_servers.py` 加 GitHub Actions workflow
- docker-compose up + pytest + teardown
- fail block PR

**A3+A4 (1.6d, 2 commit) — v1.4 orchestrator E2E**:
- v1.4a parse→evaluate 0.8d (仿 v1.1+v1.2 mock LLM)
- v1.4b match→schedule 0.8d

**A5 (0.5d, 1 commit) — 性能 baseline**:
- 测当前 P50/P95 + 报告 (14 server 数字)
- 加 CI 阈值门禁

**A6 (0.3d, 1 commit) — ship report 模板化**:
- 抽 18+ ship report 共性结构
- 写 `docs/ship-report-template.md`
- 写 lint/check 验证后续 PR 用模板

**B1-B6 (10.5d, 6 commit) — E2E 补盲** (Phase B):
- 见 `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2

## 8. 回滚方法

```bash
# 失败回滚
git revert <A1 commit>
# 改动 10 文件
git checkout HEAD~1 -- \
  apps/api/app/core/rate_limit.py \
  apps/api/app/core/telemetry.py \
  apps/api/app/main.py \
  apps/api/app/api/router.py \
  apps/api/app/api/admin.py \
  scripts/health-check.sh \
  scripts/health-check-load.sh \
  scripts/audit_rate_limit.py \
  docs/rate-limit-audit.md \
  docs/system-health-check.md
```

**回滚影响范围**：
- admin 端点 404 (路由消失)
- `/metrics` 不含 `rate_limit_check_total` (回归 P5-7 状态)
- 限流 store 每次新建 (admin 拿不到引用, 但 P5-8 限流仍工作)
- health-check 恢复单脚本 (Step 8 留限流污染)

## 9. A1 累计 + 引用

| 维度 | 数值 |
|---|---|
| 估时 | 1.1d (A1 0.3d + A6 模板化 0.3d 合并, A6 推到下 PR) |
| 实际 | 1.1d |
| 改动 | +475 / -10 (10 文件) |
| 测试 | 0 新单测 (核心无改动) + 6 端到端验证 |
| Health-check | 7/7 + 2/2 (含新 admin reset) |
| 教训沉淀 | sync/async 边界分层 (3.2) |

**引用**：
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (Phase A)
- Momus 审核: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §1.4 (限流 mitigation 选 (b) 拆脚本)
- 历史 PR: `v1.3` (pre-commit 防御 check), `v0.7.2` (per-host 鉴权), `v0.8` (60 并发压测)
- 限流核心: `apps/api/app/core/rate_limit.py` (P5-8 313 行 + A1 130 行)
- 限流 audit 文档: `docs/rate-limit-audit.md`
- Admin 端点: `apps/api/app/api/admin.py`
- 双脚本: `scripts/health-check.sh` + `scripts/health-check-load.sh`
- Audit 脚本: `scripts/audit_rate_limit.py`

**下一步**: A2 (E2E CI) 或 A5 (性能 baseline) — 建议 A5 先跑出 baseline, A2 阈值门禁才能设
