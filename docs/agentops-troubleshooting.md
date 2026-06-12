# AgentOps 平台 — 故障排查手册

> P2-C AgentOps 平台常见问题定位与修复。

---

## 1. 事件不显示

### 症状
看板（Debug Console / 质量看板）无数据。

### 排查步骤

```bash
# 1. 确认 AgentOps 已启用
curl http://localhost:8000/api/v1/dashboard/agentops/overview

# 2. 确认 business_events 表有数据
psql -c "SELECT count(*) FROM business_events;"

# 3. 确认 agent_experiment_run 表有数据
psql -c "SELECT count(*) FROM agent_experiment_run;"

# 4. 检查业务事件是否发射
curl http://localhost:8000/api/v1/dashboard/agentops/events?limit=5

# 5. 如果都为空，检查 agentops_enabled 配置
grep AGENTOPS_ENABLED .env
```

### 修复

**问题**：`AGENTOPS_ENABLED=false`
**修复**：设为 `true` 并重启

**问题**：业务代码未调用 `RecruitmentEvents.on_*()`
**修复**：在 resume_parser / screening_agent / jd_generator / interview 中确保已导入并调用 RecruitmentEvents

---

## 2. LLM Judge 不工作

### 症状
Experiment 使用 `agentops_evals` 模式但评分全是 heuristic（输出长度估算）。

### 排查步骤

```bash
# 1. 检查 LLM_JUDGE_ENABLED
grep LLM_JUDGE_ENABLED .env

# 2. 检查生产 LLM 是否可用
curl http://localhost:8000/health

# 3. 查看日志
grep "LLMJudgeFactory\|LLM judge" logs/api.log
```

### 修复

**问题**：`LLM_JUDGE_ENABLED=false`（默认）
**修复**：设为 `true`。Judge 默认使用生产 LLM + `gpt-4o-mini` 模型

**问题**：生产 LLM 不可用
**修复**：Judge 自动降级到 HeuristicJudge，不会阻塞实验运行

**问题**：rubric 未覆盖
**修复**：检查 `llm_judge.py` 中的 `_RUBRICS` 字典是否包含你的 ScoreType

---

## 3. PII 泄露

### 症状
第三方观测平台（Langfuse）看到明文手机号、邮箱、身份证。

### 排查

```bash
# 1. 检查 PrivacyPolicyConfig
python -c "
from app.agentops.privacy.policies import PrivacyPolicyConfig
cfg = PrivacyPolicyConfig(current_env='production')
print('resume_text:', cfg.get_action('resume_text'))
print('email:', cfg.get_action('email'))
print('phone:', cfg.get_action('phone'))
"
```

### 修复

**问题**：新字段未加入策略
**修复**：在 `privacy/policies.py` 的 `DEFAULT_FIELD_POLICIES` 中添加新字段

**问题**：字段名大小写不匹配
**修复**：`get_action()` 内部会 lower() 处理，确保传入的字段名小写

**问题**：代码绕过 sanitize 直接传原始数据
**修复**：确保所有事件发射路径都经过 `_strip_pii_from_domain()` 或 `sanitize_payload()`

---

## 4. Langfuse 连接失败

### 症状
日志中出现 `agentops export failed` 但业务正常。

### 排查

```bash
# 1. 检查 Langfuse 凭据
grep LANGFUSE .env

# 2. 检查网络连通性
curl -I $LANGFUSE_BASE_URL/api/public/health

# 3. 检查队列统计
# 查看日志中的 dropped count
```

### 修复

**问题**：`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 错误
**修复**：更新凭据后重启

**问题**：Langfuse 服务不可用
**修复**：这是设计预期的——AgentOps 自动降级到 NoopProvider，业务不中断。
队列满时新事件会被丢弃（`drop_new` 策略），重启后可恢复。

**问题**：队列积压
**修复**：增加 `agentops_queue_max_size` 或排查 exporter 为什么慢

---

## 5. 健康检查失败

### 症状
`bash scripts/health-check.sh` 某些步骤失败。

### 常见失败

| 步骤 | 常见原因 | 修复 |
|------|----------|------|
| Step 1（基础设施） | Docker 服务未启动 | `docker compose up -d postgres redis qdrant minio` |
| Step 2（后端进程） | uvicorn 未运行 | `make api:dev` |
| Step 3（登录） | 测试用户不存在 | 自动创建，重试即可 |
| Step 5（前端） | Next.js 未启动 | `pnpm dev` |
| Step 6（E2E） | 浏览器环境问题 | `npx playwright install` |

---

## 6. 常见错误信息

| 错误信息 | 原因 | 修复 |
|----------|------|------|
| `LLMJudgeFactory init failed` | LLM Judge 配置错误或 LLM 不可用 | 检查 LLM_JUDGE_* 配置，Judge 已自动降级 |
| `RecruitmentEvents emit failed` | EventEmitter 异常 | 检查 provider 可达性，事件已自动降级 |
| `Sanitize warning: unknown field` | 新字段未在策略中注册 | 添加到 `DEFAULT_FIELD_POLICIES` |
| `Queue full, dropping event` | 队列满，事件被丢弃 | 增加 `agentops_queue_max_size` 或排查 exporter |
| `Circuit breaker open` | 连续导出失败 | 等待恢复窗口（默认 60s）后自动半开 |

---

## 7. 获取帮助

- 健康检查：`bash scripts/health-check.sh`
- 查看日志：`tail -f logs/api.log | grep "agentops\|LLM judge\|RecruitmentEvents"`
- 后端测试：`cd apps/api && python -m pytest tests/test_agentops_*.py -v`
