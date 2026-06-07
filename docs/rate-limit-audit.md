# 限流策略 Audit — 14 server + 全部 HTTP 端点

> 创建: 2026-06-07 (A1 PR)
> 范围: 现有所有限流配置 + 已知缺口 + 后续 PR 计划
> 配套: `app/core/rate_limit.py` + `app/api/admin.py` (限流状态查询/重置)

## 1. 限流架构总览

**两层防护**：

| 层 | 实现 | 限流类型 | 范围 |
|---|---|---|---|
| **L1 HTTP 中间件** | `create_rate_limit_middleware` (main.py:171) | 3-key 滑动窗口 (org/user/IP) | 全部 HTTP 端点 |
| **L2 per-org Quota** | `QuotaTracker` (rate_limit.py:138) | LLM token 月度配额 | LLM 调用端点 |

**A1 增强**：
- `app/core/rate_limit.py` module-level singleton store
- `app/api/admin.py` 加 `GET/POST /api/v1/admin/rate-limit/{state,reset}` (admin only)
- `app/core/telemetry.py` 加 `rate_limit_check_total{key_type,path,blocked}` Counter

## 2. 3-key 限流默认值

来源: `app/core/rate_limit.py:117` `DEFAULT_LIMITS`

| key | 限制 | 窗口 | 适用 |
|---|---|---|---|
| `org` | 100 req/min | 60s | 防团队滥用 |
| `user` | 60 req/min | 60s | 防个人刷 |
| `ip` | 30 req/min | 60s | 匿名端点防恶意 |

**任意一个 key 超限 → 429**

## 3. 排除路径 (不计入限流)

来源: `app/core/rate_limit.py:368` `exclude_paths`

```
/health, /metrics, /docs, /redoc, /openapi.json
/docs/*, /redoc/* (前缀匹配)
```

## 4. 14 server 限流覆盖

**14 server 全部走 HTTP 端点**（通过 `apps/api/app/api/*.py` 路由），**自动被 L1 中间件限流覆盖**。

| # | Server | 入口文件 | 端点数 | 限流覆盖 |
|---|---|---|---|---|
| 1 | application | `app/api/applications.py` | 6 | ✓ L1 中间件 |
| 2 | candidate | `app/api/candidates.py` | 5 | ✓ L1 中间件 |
| 3 | dashboard | `app/api/dashboard.py` | 5 | ✓ L1 中间件 |
| 4 | evaluation | `app/api/evaluations.py` | 4 | ✓ L1 中间件 |
| 5 | interview | `app/api/interviews.py` | 12 | ✓ L1 中间件 |
| 6 | jd | `app/api/jobs.py` (job_server 用) | 5 | ✓ L1 中间件 |
| 7 | knowledge | `app/api/knowledge.py` | 4 | ✓ L1 中间件 |
| 8 | resume | `app/api/resume.py` | 4 | ✓ L1 中间件 |
| 9 | screening | `app/api/screening.py` | 4 | ✓ L1 中间件 |
| 10 | search | `app/api/*` (search 走多端点) | 3 | ✓ L1 中间件 |
| 11 | skill_mgr | `app/api/mcp_servers.py` (skill 走 mcp) | 7 | ✓ L1 中间件 |
| 12 | utils | `app/api/*` (utility 端点) | 3 | ✓ L1 中间件 |
| 13 | weather | `app/api/knowledge.py` (集成) | 1 | ✓ L1 中间件 |
| 14 | dashboard_reports | `app/api/dashboard_reports.py` | 4 | ✓ L1 中间件 |

**MCP server (mcp_servers/builtin/*.py) 不直接挂限流** — 走 HTTP 路由自动覆盖。

## 5. 高频端点 (需要重点关注)

| 端点 | 路由前缀 | 风险 |
|---|---|---|
| `/api/v1/auth/login` | `app/api/auth.py` | 撞限流 → 健康检查 Step 8 60 并发打 401/422/429 |
| `/api/v1/agent/*` | `app/api/agent.py` + `agent_events.py` + `agent_telemetry.py` | 高频调用 |
| `/api/v1/pipeline/*` | `app/api/pipeline.py` | LLM token 消耗大 (per-org quota 兜底) |
| `/api/v1/interviews/*` | `app/api/interviews.py` (12 端点) | 业务高频 |
| `/api/v1/dashboard/*` | `app/api/dashboard.py` + `dashboard_reports.py` | 缓存命中率需监控 |

## 6. per-org LLM Quota (L2 兜底)

来源: `app/core/rate_limit.py:131` `PLAN_QUOTAS_TOKENS`

| Plan | 月度 token 配额 |
|---|---|
| starter | 500,000 |
| pro | 2,000,000 |
| enterprise | 10,000,000 |
| (未配置 plan) | 100,000 默认 |

**触发**：
- 超 80% → 飞书 webhook 通知 owner (`send_quota_breach_notification`)
- 超 100% → `check_and_consume` 拒绝 (返 allowed=False)
- 灰度发布: `RATELIMIT_ROLLOUT_PCT` 0-100, 1% 起步

## 7. 已知缺口 (后续 PR 计划)

| # | 缺口 | 影响 | 建议 PR | 估时 |
|---|---|---|---|---|
| 1 | **per-endpoint 配额缺失** | LLM 端点 (/pipeline, /agent) 应有更严格限额 (如 10 req/min) | D5 (Phase D 战略投资) | 1d |
| 2 | **MCP server 内部限流** | 14 server 自身不限制（如 resume parser 调 LLM） | 暂不需 (HTTP 层已挡) | — |
| 3 | **quota 持久化缺失败回退** | QuotaTracker 内存版重启丢计数 | 已有 Redis 版可切, 但 P5-7 默认 mock 走内存 | 0.5d |
| 4 | **限流命中率监控** | 无 429 rate 趋势面板 | Phase C 监控接入 (A5 性能 baseline 后) | — |
| 5 | **限流白名单机制** | health-check 60 并发必撞限流, 需 ad-hoc 调阈值 | A1 已加 admin reset 缓解 | ✓ |
| 6 | **限流日志缺 trace_id** | 429 响应无 request_id, 排查困难 | 后续 P2 (跟 structlog 一起做) | — |

## 8. A1 之前 vs A1 之后

| 能力 | A1 之前 | A1 之后 |
|---|---|---|
| Store 单例 | ✗ 每次新建 (admin 拿不到) | ✓ module-level singleton |
| 状态查询 | ✗ 看不到 (只能看 429 现象) | ✓ `GET /admin/rate-limit/state` |
| 状态清空 | ✗ 等 60s 自然过期 | ✓ `POST /admin/rate-limit/reset` |
| 限流 metrics | ✗ /metrics 无 rate_limit | ✓ `rate_limit_check_total{key_type,path,blocked}` |
| Health-check 限流污染 | ✗ 60 并发必撞 | ✓ 拆 2 脚本 + load 前 reset |

## 9. 运维 SOP (A1 新增)

### 9.1 健康检查撞限流 (临时清空)
```bash
ADMIN_TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@x.com","password":"..."}' | jq -r .access_token)

curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    http://localhost:8000/api/v1/admin/rate-limit/reset | jq
```

### 9.2 故障排查 (看当前状态)
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
    http://localhost:8000/api/v1/admin/rate-limit/state | jq
# 返: {store_type, active_buckets, active_counters, limits: {...}}
```

### 9.3 429 率监控 (Prometheus)
```promql
sum(rate(rate_limit_check_total{blocked="true"}[5m])) by (path)
/
sum(rate(rate_limit_check_total[5m])) by (path)
```

## 10. 引用

- 限流核心: `apps/api/app/core/rate_limit.py` (P5-8 313 行, A1 加 130 行)
- 限流中间件注册: `apps/api/app/main.py:171`
- Admin 端点: `apps/api/app/api/admin.py` (A1 新增)
- Telemetry: `apps/api/app/core/telemetry.py` (A1 加 14 行)
- 健康检查: `scripts/health-check.sh` (A1 拆分)
- 历史教训: `.omo/plans/2026-06-07-roadmap-corrected.md` §0.5 (LangGraph 推后), §1.4 (限流 mitigation 选 (b) 拆脚本)
