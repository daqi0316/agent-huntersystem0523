# AgentOps 平台 — 运维手册

> P2-C AgentOps 平台运维指南。适用于部署、配置、故障排查。

---

## 1. 配置清单

### 1.1 核心开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `agentops_enabled` | `False` | 全局开关，关闭时所有调用走 NoopProvider |
| `agentops_provider` | `"noop"` | Provider 类型：`noop` / `langfuse` |
| `agentops_environment` | `"local"` | 运行环境：`local` / `development` / `staging` / `production` |
| `agentops_queue_max_size` | `1000` | 事件队列最大容量 |
| `agentops_flush_timeout_seconds` | `2.0` | 进程退出时 flush 超时 |

### 1.2 Langfuse 配置

```bash
# .env
AGENTOPS_ENABLED=true
AGENTOPS_PROVIDER=langfuse
AGENTOPS_ENVIRONMENT=production
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_CAPTURE_INPUT=false   # 生产建议 false
LANGFUSE_CAPTURE_OUTPUT=false  # 生产建议 false
```

### 1.3 LLM Judge 配置

```bash
LLM_JUDGE_ENABLED=false           # 默认关闭
LLM_JUDGE_PROVIDER=omlx           # 评估用 LLM provider
LLM_JUDGE_MODEL=gpt-4o-mini       # 评估用模型（通常用轻量模型）
LLM_JUDGE_TIMEOUT=15.0            # 评估超时秒数
```

## 2. 部署检查清单

### 2.1 基础设施

- [ ] PostgreSQL 可连接（`business_events` 表已创建）
- [ ] Langfuse 实例可访问（自托管或 Cloud）
- [ ] Redis（用于队列缓冲，可选）

### 2.2 数据库迁移

```bash
cd apps/api
alembic upgrade head
```

需确认的迁移：
- `business_events` 表（业务事件存储）
- `agent_feedback` 表（用户反馈）
- `agent_dataset_item` 表（回归测试集）
- `agent_experiment` / `agent_experiment_run` 表（实验运行）

### 2.3 环境变量

- [ ] `AGENTOPS_ENABLED=true` 已设置
- [ ] `AGENTOPS_PROVIDER=langfuse` 已设置
- [ ] `AGENTOPS_ENVIRONMENT=production` 已设置
- [ ] `LANGFUSE_*` 凭据已配置
- [ ] `LLM_JUDGE_ENABLED` 按需配置

### 2.4 启动验证

```bash
# 1. 健康检查
bash scripts/health-check.sh

# 2. 完整测试
cd apps/api && python -m pytest tests/ -k "not e2e and not integration"

# 3. 验证非 e2e 测试全部通过（预期 2900+）
```

## 3. 监控指标

### 3.1 Prometheus 指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `tool_call_total` | Counter | `tool_name`, `tool_category`, `status` | 工具调用计数 |
| `llm_request_total` | Counter | `model`, `provider` | LLM 请求计数 |
| `llm_failure_total` | Counter | `model`, `error_type` | LLM 失败计数 |

### 3.2 看板 URL

| 看板 | URL |
|------|-----|
| AgentOps 概览 | `/agentops` |
| Debug Console | `/agentops/debug` |
| 成本看板 | `/agentops/cost` |
| 治理后台 | `/agentops/governance` |

## 4. 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Provider 抽象 | Provider 接口 + NoopProvider + CompositeProvider | Langfuse 故障不影响业务 |
| 事件存储 | PostgreSQL（`business_events` 表） | 无需额外基础设施 |
| LLM Judge 模型 | 独立于生产 LLM 配置 | 评估流量不影响生产、可用轻量模型 |
| PII 脱敏 | `sanitize_payload()` 字段级策略 | 生产默认 DROP/HASH P0/P1 字段 |
| 采样控制 | `SamplingConfig` + 确定性哈希 | 同一 trace_id 采样结果一致 |
