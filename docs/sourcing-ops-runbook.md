# Sourcing 模块运维手册 (P6)

> 适用范围: 寻源系统 (apps/api/app/sourcing/)  
> 最后更新: 2026-06-11

## 目录

1. [系统概览](#1-系统概览)
2. [日常运维](#2-日常运维)
3. [数据归档](#3-数据归档)
4. [健康探测](#4-健康探测)
5. [性能调优](#5-性能调优)
6. [故障恢复](#6-故障恢复)
7. [数据库维护](#7-数据库维护)

---

## 1. 系统概览

### 架构

```
用户请求 → FastAPI (/api/v1/sourcing/*) → Orchestrator → Platform Adapter → 外网平台
                                                 ↓
                                            arq Worker (Redis) ← 异步任务
                                                 ↓
                                            dedup Engine (Redis)
                                                 ↓
                                            Candidate → PostgreSQL
```

### 依赖服务

| 服务 | 用途 | 端口 |
|------|------|------|
| PostgreSQL | 持久化 (tasks/candidates/logs) | 5432 |
| Redis | arq 队列 + 去重缓存 | 6379 |

### 关键表

| 表 | 用途 | 数据量预估 |
|----|------|-----------|
| `sourcing_tasks` | 采集任务 | ~1K/天 |
| `crawl_logs` | 采集日志 | ~10K/天 |
| `candidates` | 候选人 (含 sourcing 字段) | ~5K/天 |
| `candidates_archive` | 归档冷数据 | >180 天 |
| `sourcing_platform_configs` | 平台配置 | <50 行 |
| `sourcing_platform_accounts` | 平台账号 | <200 行 |

---

## 2. 日常运维

### 启动 sourcing 模块

```bash
# 开发环境（需先启动基础设施）
make dev:infra
make api:dev

# 确保 Redis 和 PostgreSQL 可达
redis-cli ping       # → PONG
psql -d postgres -c "SELECT 1"  # → 1
```

### 启动 arq Worker

```bash
# Worker 会自动注册 sourcing 任务处理器
cd apps/api
python -m app.sourcing.arq_worker
```

Worker 监听队列中的 `crawl_task` 和 `analyze_candidates` 任务。

### 查看任务状态

```bash
# API
curl http://localhost:8000/api/v1/sourcing/tasks?status=running

# 直接查 DB
psql -d aihunter -c "
  SELECT id, keyword, status, total_found, after_dedup, created_at
  FROM sourcing_tasks
  WHERE created_at > now() - interval '24 hours'
  ORDER BY created_at DESC;
"
```

### 取消卡住的任务

```bash
curl -X POST http://localhost:8000/api/v1/sourcing/tasks/{task_id}/cancel

# 或直接 DB update（紧急情况下）
psql -d aihunter -c "
  UPDATE sourcing_tasks SET status = 'failed' WHERE id = '...';
"
```

---

## 3. 数据归档

### 自动归档规则

`candidates` 表中超过 180 天的终端状态候选人自动归档到 `candidates_archive`：

- **终端状态**: `completed`, `failed`, `blacklisted`, `archived`
- **条件**: `updated_at < NOW() - 180 days`
- **动作**: COPY → DELETE（关联表由 CASCADE 自动清理）

### 手动执行存档

```bash
# 预览（不实际操作）
make api:archive

# 实际执行
make api:archive:run

# 或直接运行脚本
python scripts/archive_candidates.py --days 180 --batch 500
```

### 定时任务

建议配置 crontab 或 CI 定时任务每月运行一次归档：

```cron
# 每月 1 号凌晨 3 点执行归档
0 3 1 * * cd /path/to/project && python scripts/archive_candidates.py --days 180
```

### 数据恢复

归档数据仍在同一数据库，可直接查询：

```sql
SELECT * FROM candidates_archive WHERE email = 'candidate@example.com';
```

如需恢复到 candidates 主表，手动 INSERT 即可。

---

## 4. 健康探测

### 系统健康检查（全栈）

```bash
bash scripts/health-check.sh
```

通过 6 步检查: infra 服务 → 后端 → 登录 → token 验证 → 前端可达 → E2E 登录。

### Playwright 平台健康探测（CI 定时任务）

定义文件: `.github/workflows/platform-health-probe.yml`

- 定时: 每天 UTC 02:00
- 检查项: API 健康端点、DB、Redis、arq 队列、平台配置、前端页面、无控制台错误
- 失败时: Slack 通知

手动触发:

```bash
gh workflow run platform-health-probe.yml
```

### 后端平台探测

```bash
cd apps/api
python -c "from app.sourcing.health_probe import probe_platform_health; import asyncio; print(asyncio.run(probe_platform_health()))"
```

---

## 5. 性能调优

### 当前已加索引

| 表 | 索引 | 类型 | 作用 |
|----|------|------|------|
| `candidates` | `ix_candidates_skills_gin` | GIN | skills.any() 技能搜索 |
| `candidates` | `ix_candidates_raw_data_gin` | GIN | JSON 路径查询 |
| `candidates` | `ix_candidates_org_status` | B-tree | 组织+状态过滤 |
| `crawl_logs` | `ix_crawl_logs_task_platform` | B-tree | 任务+平台筛选 |
| `sourcing_tasks` | `ix_sourcing_tasks_org_status` | B-tree | 组织+状态过滤 |

### 游标分页

大列表页（如候选人列表）应使用游标分页而非 offset/limit：

```python
from app.utils.cursor_pagination import paginate_desc, paginate_asc

query = select(Candidate).where(Candidate.org_id == org_id)
page = await paginate_desc(db, query, Candidate.created_at, page_size=20, cursor=cursor)
```

### 慢查询排查

```sql
-- PostgreSQL 慢查询日志（需启用 pg_stat_statements）
SELECT query, calls, total_time / calls AS avg_ms, rows
FROM pg_stat_statements
WHERE query LIKE '%candidates%' OR query LIKE '%sourcing_tasks%'
ORDER BY avg_ms DESC
LIMIT 10;
```

---

## 6. 故障恢复

### Scenario A: arq Worker 挂了

**症状**: 任务状态一直是 `pending`，不进入 `running`。  
**处理**:

```bash
# 检查 worker 进程
ps aux | grep arq_worker

# 重启 worker
cd apps/api && python -m app.sourcing.arq_worker

# 检查 Redis 连接
redis-cli ping
redis-cli llen arq:queue
```

### Scenario B: 平台封禁（Account Banned）

**症状**: 某个平台连续失败，`crawl_logs.status = 'account_banned'`。  
**处理**:

1. 确认该平台是否有备用账号: `SELECT * FROM sourcing_platform_accounts WHERE platform='boss_zhipin' AND status='active';`
2. 更换账号后恢复: 系统自动轮换（`RecoveryExecutor`）
3. 若所有账号被封 → 等待冷却期或联系平台

### Scenario C: API 返回 500 / 超时

**症状**: `/api/v1/sourcing/*` 端点响应慢或报错。  
**处理**:

```bash
# 1. 先跑健康检查
bash scripts/health-check.sh

# 2. 检查 API 进程
ps aux | grep uvicorn
make api:dev   # 重启 API

# 3. 检查看门狗日志
cat /tmp/wd-stdout.log

# 4. 查看数据库连接池
psql -d aihunter -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
```

### Scenario D: 数据不一致 / 重复候选人

**症状**: 同一候选人出现多条记录。  
**处理**:

1. 查指纹冲突: `SELECT dedup_fingerprint, count(*) FROM candidates WHERE dedup_fingerprint IS NOT NULL GROUP BY 1 HAVING count(*) > 1;`
2. 使用合并 API: `curl -X POST http://localhost:8000/api/v1/sourcing/candidates/merge -d '{"primary_id": "...", "merge_ids": ["..."]}'`
3. 手动清理 Redis 去重集（重置 TTL）: `redis-cli expire "sourcing:dedup:boss_zhipin" 0`

---

## 7. 数据库维护

### 迁移

```bash
# 升级到最新
make api:migrate

# 检查模型与 DB 一致性
make api:check-schema

# 手动执行
cd apps/api && alembic upgrade head
```

### 迁移历史

| Revision | 日期 | 说明 |
|----------|------|------|
| `p6_5_perf_indexes` | 2026-06-11 | GIN/组合索引 |
| `p6_4_candidates_archive` | 2026-06-11 | 候选人归档表 |
| `043c3b04ac57` | 2026-06-11 | P0 sourcing 建表 |
| `p2_c_agent_llm_generations` | 2026-06-05 | LLM generations |

### 关键指标

| 指标 | 正常范围 | 告警阈值 |
|------|---------|---------|
| 任务成功率 | > 80% | < 60% |
| 候选人新增/天 | 100-5000 | < 10 |
| crawl_logs 失败率 | < 20% | > 50% |
| API 响应时间 (p95) | < 2s | > 5s |
| 账号活跃比例 | > 70% | < 30% |
