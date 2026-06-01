# Phase 3.5: AI Operations + HITL + Monitoring

> 基于 Momus 审核修正版（2026-05-31）
> 砍掉过度设计项，补全持久化缺口

---

## 核心修正（Momus）

| 原始规划问题 | Momus 发现 | 修正 |
|-------------|-----------|------|
| HumanLoop 审批在内存 | 进程重启丢失所有 pending | **2A'** 审批持久化到 DB |
| "失败"定义模糊 | system/user/business 混在一起 | **1A'** `error_category` 字段 |
| Metric 扫全表 | 数据量增长后不可用 | **3A'** 物化聚合表 `operation_stats_hourly` |
| SHA256 链式哈希 | 过度设计 | 砍掉，改 `immutable + superseded_by` |
| 审批升级 | 阻塞于 RBAC 多租户 | 砍掉（Phase 4） |
| 数据保留策略 | 数据量上来再说 | 砍掉（Phase 4） |

---

## 执行计划

### P0 — 基础设施加固（并行 3 项）

#### 1A' OperationLog.error_category

```
OperationLog:
  + error_category: str | None  # enum: system / user / business
                                # system = LLM超时/DB断连（报警）
                                # user   = 用户输入错误（记录不报警）
                                # business = 业务拒绝（正常流程）
  + immutable: bool = True       # app 层禁止 update，只 append
  + superseded_by: str | None    # 修正链

API:
  GET /operations → 增加 error_category 过滤
  GET /audit/logs → 新端点，只读审计视图（不可写）

文件:
  app/models/operation_log.py     — 加字段
  app/api/operations.py           — 加过滤
  app/api/audit.py (新)           — 审计查询端点
```

#### 2A' HumanLoop 审批 DB 持久化

```
ApprovalModel (新):
  approval_id, user_id, action_type, proposal(JSONB),
  status, candidate_email, created_at, expires_at, 
  escalated_at, resolved_at, resolution, resolver_id

HumanLoopAgent 改造:
  内存 pending_approvals → DB 读写
  create_proposal → INSERT
  confirm → UPDATE status
  get_pending → SELECT WHERE status='pending'
  _clean_expired → UPDATE WHERE expires_at < now

文件:
  app/models/approval.py (新)
  app/services/approval_service.py (新)
  app/agents/human_loop.py — 重构持久化
```

#### 3A' 物化聚合 + Metrics API

```
operation_stats_hourly (新表):
  bucket_hour, agent_name, action,
  total_ops, success_count, fail_count,
  avg_duration_ms, p50_ms, p95_ms

AggregationService:
  每 5 分钟: SELECT FROM operation_logs WHERE updated_at > last_bucket
  → UPSERT INTO operation_stats_hourly
  lifespan 中 create_task

API:
  GET /dashboard/operations/summary → 实时摘要（from 聚合表）
  GET /dashboard/operations/trend   → 24h 趋势（供 Recharts）

文件:
  app/models/operation_stats.py (新)
  app/services/aggregation_service.py (新)
  app/api/dashboard.py — 加端点
```

---

### P1 — 功能完成

#### 1B 审计查询（简化版）

```
GET /audit/logs?agent=&level=&from_date=&to_date=&limit=&offset=
GET /audit/stats → 各 agent 操作次数、失败率、平均耗时

前端:
  AuditPanel 组件 — 只读审计视图
```

#### 2A 超时自动拒绝

```
ApprovalService.auto_expire():
  UPDATE approvals SET status='expired', resolution='auto_rejected'
  WHERE status='pending' AND expires_at < now()
  publish("approval.expired", {approval_id})

HumanLoopAgent.run() 入口检查:
  先执行一次 auto_expire()
```

---

### P2 — 可视化

#### 1C 审计前端面板

```
apps/web/components/features/audit/audit-panel.tsx
  表格: 时间 | Agent | Action | Level | 状态 | 耗时
  过滤: 按 Agent / Level / 时间范围
  详情展开: input_summary / output_summary / error

Dashboard 集成:
  看板底部增加 "审计日志" 折叠面板
```

#### 2C 审批超时倒计时

```
前端 HumanLoop 卡片:
  显示 expires_at 倒计时（<5分钟红色闪烁）
  超时后灰显 + "已过期"
  SSE 事件 approval.expired 自动刷新
```

#### 3C 监控前端

```
Dashboard "AI 健康" 区块:
  成功率环图（24h / 7d）
  Agent 卡片列表: 名称 | 操作数 | 成功率 | P95耗时
  趋势折线图（Recharts）
  告警横幅（红色，置顶）

文件:
  apps/web/components/features/monitoring/ai-health.tsx
  apps/web/app/(dashboard)/dashboard/page.tsx — 集成
```

---

## 文件变更清单

| 文件 | 操作 | 归属 |
|------|------|------|
| `app/models/operation_log.py` | 修改（+error_category, superseded_by） | 1A' |
| `app/models/approval.py` | 新建 | 2A' |
| `app/models/operation_stats.py` | 新建 | 3A' |
| `app/services/approval_service.py` | 新建 | 2A' |
| `app/services/aggregation_service.py` | 新建 | 3A' |
| `app/services/operation_service.py` | 修改（+error_category） | 1A' |
| `app/api/operations.py` | 修改（+过滤） | 1A' |
| `app/api/audit.py` | 新建 | 1B |
| `app/api/dashboard.py` | 修改（+metrics） | 3A' |
| `app/api/router.py` | 修改（注册 audit 路由） | 1B |
| `app/agents/human_loop.py` | 修改（DB 持久化） | 2A' |
| `app/main.py` | 修改（+aggregation loop） | 3A' |
| `apps/web/components/features/audit/audit-panel.tsx` | 新建 | 1C |
| `apps/web/components/features/monitoring/ai-health.tsx` | 新建 | 3C |
| `apps/web/app/(dashboard)/dashboard/page.tsx` | 修改（集成） | 1C+3C |

---

## 退出标准

- [ ] 所有 OperationLog 写入 `error_category`，system_error 能正确触发报警
- [ ] HumanLoop 审批重启不丢失（pending 存在于 DB）
- [ ] `GET /dashboard/operations/summary` 响应 < 200ms（读聚合表）
- [ ] 超时审批自动标记 expired
- [ ] Dashboard 展示 AI 健康面板（成功率 + P95 + Agent 卡片）
