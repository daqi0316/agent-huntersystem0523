# Langfuse 招聘 AgentOps 平台工程化规划

> 目标：不是“接入 Langfuse 埋点”，而是建设长期可演进的 **Recruitment AgentOps Platform**。Langfuse 是首个观测与评估后端，但业务侧必须保留抽象层、事件协议、隐私治理、评估闭环和扩展能力。

## 1. Momus 审核修正结论

上一版规划方向正确，但仍偏“功能清单”，不足以支撑长期工程化。必须修正为平台化方案：

- **工程化**：有抽象接口、标准事件协议、可靠性队列、测试和治理机制。
- **深度化**：覆盖 Agent、LLM、Tool、招聘业务节点、质量评估和事故复盘。
- **长远化**：支持多 Provider、多模型、多租户、数据治理、Prompt/模型实验和回归测试。
- **模块化**：拆分 core、provider、exporter、instrumentation、privacy、evaluation、sampling、reliability、governance。
- **可扩展**：Exporter / Evaluator / Sanitizer / Sampler / Enricher 均插件化。

核心修正：**不要做 Langfuse 埋点项目，要做 Recruitment AgentOps 平台；Langfuse 只是第一后端。**

## 2. 平台定位

平台要解决的问题：

1. 任意一次招聘 Agent 回复能否完整复盘？
2. 候选人为什么被推荐或拒绝？
3. 哪个工具调用失败率最高？
4. 哪类任务最慢、最耗 token、最容易 fallback？
5. 哪个 Prompt / 模型 / Agent 版本导致质量下降？
6. 用户差评能否转成可复用回归测试集？
7. 简历、候选人、面试反馈等隐私数据是否被安全处理？

## 3. 长期架构

```text
┌──────────────────────────────────────────────┐
│ 8. 产品化使用层                               │
│ Debug Console / 质量看板 / 成本看板 / 复盘页 │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 7. 治理控制面                                 │
│ 采样规则 / 脱敏规则 / 保留策略 / 权限策略     │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 6. 评估闭环层                                 │
│ Scores / Rubrics / Datasets / Experiments    │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 5. Exporter 适配层                            │
│ Langfuse / OTEL / Prometheus / ClickHouse     │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 4. 传输可靠性层                               │
│ Async Queue / Retry / Circuit Breaker / Flush │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 3. 标准事件层                                 │
│ TraceEvent / SpanEvent / LLMEvent / ToolEvent │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 2. 采集 SDK 层                                │
│ decorators / context manager / middleware     │
└──────────────────────────────────────────────┘
                     ↑
┌──────────────────────────────────────────────┐
│ 1. 招聘 Agent 业务执行层                      │
│ AgentService / Orchestrator / LLM / Tools     │
└──────────────────────────────────────────────┘
```

## 4. 设计原则

### 4.1 Langfuse 不直接侵入业务

业务代码不应到处：

```python
from langfuse import get_client
```

而应只依赖内部 SDK：

```python
from app.agentops import observe
```

### 4.2 先标准化事件，再导出到 Langfuse

业务侧产生内部标准事件：

```text
LLMGenerationCompleted
ToolInvocationFailed
AgentRoutingCompleted
ResumeParseScored
```

Langfuse 只是 exporter，不是业务协议本身。

### 4.3 所有能力插件化

必须支持：

```text
Exporter 可插拔
Evaluator 可插拔
Sanitizer 可插拔
Sampler 可插拔
Enricher 可插拔
Storage 可插拔
```

### 4.4 生产环境隐私优先

默认不上传：

```text
简历全文
明文手机号
明文邮箱
身份证
附件原始 URL
内部敏感审批备注
```

## 5. 模块化目录设计

建议新增：

```text
apps/api/app/agentops/
  __init__.py

  core/
    context.py
    events.py
    schemas.py
    ids.py
    clock.py

  providers/
    base.py
    noop.py
    langfuse.py
    composite.py

  exporters/
    base.py
    langfuse_exporter.py
    prometheus_exporter.py
    log_exporter.py

  instrumentation/
    fastapi.py
    llm.py
    tools.py
    agents.py
    langgraph.py
    conversation.py

  privacy/
    sanitizer.py
    pii_rules.py
    redaction.py
    hashing.py
    policies.py

  evaluation/
    schemas.py
    score_writer.py
    rubrics.py
    evaluators/
      rule_based.py
      llm_judge.py
      human_feedback.py
      resume_quality.py
      screening_quality.py
      jd_quality.py

  sampling/
    rules.py
    sampler.py

  reliability/
    queue.py
    retry.py
    circuit_breaker.py
    flush.py

  governance/
    retention.py
    tenant_policy.py
    access_policy.py
    audit.py

  dashboards/
    metrics.py
    queries.py
```

## 6. 核心接口

### 6.1 AgentOpsProvider

```python
class AgentOpsProvider:
    async def start_trace(self, event): ...
    async def start_span(self, event): ...
    async def record_generation(self, event): ...
    async def record_tool_call(self, event): ...
    async def record_score(self, event): ...
    async def flush(self): ...
    async def shutdown(self): ...
```

实现：

```text
NoopProvider
LangfuseProvider
OpenTelemetryProvider
CompositeProvider
```

### 6.2 Exporter

```python
class AgentOpsExporter:
    async def export_trace(self, event): ...
    async def export_span(self, event): ...
    async def export_generation(self, event): ...
    async def export_tool_call(self, event): ...
    async def export_score(self, event): ...
```

### 6.3 Evaluator

```python
class Evaluator:
    name: str
    version: str

    async def evaluate(self, trace_snapshot) -> list:
        ...
```

候选实现：

```text
ToolSuccessEvaluator
LatencyEvaluator
PIISafetyEvaluator
ResumeParseQualityEvaluator
ScreeningReasonabilityEvaluator
JDQualityEvaluator
HumanFeedbackEvaluator
LLMJudgeEvaluator
```

### 6.4 Sanitizer

```python
class Sanitizer:
    def sanitize_input(self, payload, context): ...
    def sanitize_output(self, payload, context): ...
    def sanitize_metadata(self, metadata): ...
```

策略：

```text
allow
mask
partial_mask
hash
drop
```

### 6.5 Sampler

```python
class Sampler:
    def should_capture(self, context, event) -> bool:
        ...
```

规则示例：

```text
错误全采
高延迟全采
VIP 用户全采
普通成功请求采样
dev 全采
prod 脱敏采样
```

## 7. 标准事件协议

所有事件必须带版本。

```json
{
  "schema_version": "agentops.v1",
  "event_id": "...",
  "event_type": "llm.generation.completed",
  "timestamp": "...",
  "environment": "prod",
  "service": "api",
  "trace_id": "...",
  "span_id": "...",
  "parent_span_id": "...",
  "tenant_id": "...",
  "user_id": "...",
  "session_id": "...",
  "request_id": "...",
  "operation_id": "...",
  "tags": [],
  "metadata": {}
}
```

事件分类：

```text
trace.started / trace.completed / trace.failed
span.started / span.completed / span.failed
llm.generation.started / completed / failed
tool.invocation.started / completed / failed
agent.routing.completed
agent.subgraph.completed
eval.score.created
eval.dataset.item.created
privacy.redaction.applied
privacy.violation.detected
```

## 8. 招聘业务事件

### 8.1 简历解析

```json
{
  "event_type": "recruitment.resume.parse.completed",
  "candidate_id": "...",
  "resume_id": "...",
  "file_type": "pdf",
  "field_completeness": 0.86,
  "quality_score": 0.78,
  "pii_redacted": true,
  "red_flags": []
}
```

### 8.2 候选人筛选

```json
{
  "event_type": "recruitment.screening.completed",
  "candidate_id": "...",
  "job_id": "...",
  "match_score": 82,
  "decision": "recommend",
  "hard_requirements_matched": true,
  "needs_human_review": false,
  "reason_codes": ["skill_match", "experience_match"]
}
```

### 8.3 JD 生成

```json
{
  "event_type": "recruitment.jd.generate.completed",
  "job_id": "...",
  "iteration_count": 3,
  "final_score": 8.2,
  "passed_threshold": true
}
```

### 8.4 面试安排

```json
{
  "event_type": "recruitment.interview.schedule.completed",
  "candidate_id": "...",
  "job_id": "...",
  "schedule_success": true,
  "conflict_detected": false,
  "tool_calls": 2
}
```

## 9. 数据流

### 9.1 在线链路

```text
用户请求
  ↓
FastAPI Middleware 创建 request context
  ↓
AgentService 创建 AgentOps trace
  ↓
Orchestrator / Agent / LLM / Tool 产出标准事件
  ↓
Sanitizer 脱敏
  ↓
Sampler 判断是否采集
  ↓
Async Queue
  ↓
Exporter
  ↓
Langfuse / Metrics / Logs
```

### 9.2 离线评估链路

```text
Langfuse traces
  ↓
筛选 bad case / 采样 case
  ↓
人工标注 / LLM-as-Judge / 规则评估
  ↓
Score 写回 Langfuse
  ↓
高价值 case 写入 Dataset
  ↓
Prompt / 模型 / Agent 改动跑 Experiment
  ↓
生成质量报告
  ↓
决定是否发布
```

## 10. 可靠性设计

业务主链路不能等待 Langfuse。

必须具备：

```text
异步队列
失败重试
熔断
队列满丢弃策略
shutdown flush
Langfuse 故障降级到 NoopProvider
```

策略：

```text
4xx 不重试
5xx 指数退避
连续失败 5 次熔断 60 秒
队列满默认 drop_new 并记录 dropped_count
脱敏异常则 drop payload
```

## 11. 隐私治理

### 11.1 数据分级

```text
P0 禁止出域：
- 简历全文
- 身份证
- 明文手机号
- 明文邮箱
- 附件原始 URL
- 内部敏感评价

P1 脱敏后可出：
- 姓名
- 公司名
- 学校
- 面试反馈
- 薪资范围

P2 可出：
- candidate_id
- job_id
- agent 名称
- 工具名
- 模型名
- 耗时
- 分数
```

### 11.2 策略配置

```yaml
agentops:
  privacy:
    default_policy: redact
    prod:
      capture_raw_messages: false
      capture_resume_text: false
      hash_candidate_identity: true
    dev:
      capture_raw_messages: true
      capture_resume_text: false
```

### 11.3 必测项

```text
手机号不会进入观测 payload
邮箱不会进入观测 payload
身份证不会进入观测 payload
简历全文不会进入观测 payload
附件 URL 不会进入观测 payload
```

## 12. Evaluation 体系

评估不应停留在“回答好不好”，必须按招聘业务拆分。

### 12.1 Intent Evaluation

```text
intent_correctness: 0/1
routing_confidence: 0-1
fallback_reason: categorical
```

### 12.2 Resume Parse Evaluation

```text
resume_field_completeness: 0-1
resume_parse_quality: 1-5
pii_safety: 0/1
```

### 12.3 Screening Evaluation

```text
screening_reasonability: 1-5
hard_requirement_consistency: 0/1
hallucination_risk: low/medium/high
human_review_needed: 0/1
```

### 12.4 JD Evaluation

```text
jd_completeness: 1-5
jd_clarity: 1-5
jd_attractiveness: 1-5
jd_compliance: 0/1
```

### 12.5 Conversation Evaluation

```text
answer_helpfulness: 1-5
context_consistency: 0/1
tool_use_correctness: 0/1
```

## 13. 闭环机制

### 13.1 Bad Case 闭环

```text
用户差评 / 系统检测失败
  ↓
自动标记 bad_case
  ↓
进入 Annotation Queue
  ↓
人工标注原因
  ↓
生成 score
  ↓
加入 Dataset
  ↓
成为回归测试用例
```

### 13.2 Prompt 发布闭环

```text
修改 Prompt
  ↓
绑定 prompt_version
  ↓
跑 Dataset Experiment
  ↓
比较质量 / 成本 / 延迟
  ↓
通过阈值
  ↓
发布
  ↓
线上继续监测
```

### 13.3 模型切换闭环

```text
新模型接入
  ↓
离线 Dataset 对比
  ↓
灰度流量采样
  ↓
质量和成本看板对比
  ↓
扩大流量
```

## 14. 控制面配置

### 14.1 采样规则

```yaml
sampling:
  default_rate: 0.1
  always_capture_errors: true
  always_capture_slow_traces_ms: 5000
  agent_overrides:
    screening: 1.0
    onboarding: 0.3
```

### 14.2 脱敏规则

```yaml
privacy:
  fields:
    phone: mask
    email: hash
    id_card: drop
    resume_text: drop
    candidate_name: partial_mask
```

### 14.3 评估规则

```yaml
evaluation:
  screening_reasonability:
    enabled: true
    sample_rate: 0.2
    evaluator: llm_judge
    rubric_version: screening_v1
```

### 14.4 保留策略

```yaml
retention:
  dev_days: 7
  staging_days: 30
  prod_days: 180
  incident_traces_days: 730
```

## 15. 产品化页面规划

### 15.1 Debug Console

给工程师用：

```text
按 trace_id 查链路
看 LLM 输入输出
看 tool args/result
看错误堆栈
看耗时瀑布图
跳转 Langfuse
```

### 15.2 招聘任务复盘页

给业务/运营用：

```text
候选人为什么被推荐
JD 为什么这样生成
面试安排失败在哪
人工介入发生在哪一步
```

### 15.3 质量看板

```text
筛选合理性
简历解析成功率
JD 质量
用户满意度
人工介入率
```

### 15.4 成本看板

```text
按模型成本
按 Agent 成本
按用户成本
按招聘任务成本
高成本异常 trace
```

### 15.5 治理后台

```text
配置采样规则
配置脱敏规则
配置保留策略
配置评估规则
查看隐私风险
```

## 16. 阶段规划

### Stage 1：平台地基

交付：

```text
agentops 模块
provider interface
event schema v1
context propagation
noop provider
langfuse provider
privacy sanitizer
sampling framework
reliability queue
```

验收：

```text
不用改业务逻辑也能安全创建 trace/span/score
Langfuse 关闭或故障不影响系统
```

### Stage 2：核心链路全量观测

交付：

```text
FastAPI request context
route_single trace
conversation session binding
OperationLog trace_id 关联
orchestrator span
LLM generation
tool span
```

验收：

```text
任意用户消息可完整复盘：用户输入 → 意图识别 → Agent → LLM → Tool → 回复 → 持久化
```

### Stage 3：招聘业务 Agent 深度观测

交付：

```text
resume parse observability
screening observability
jd generation observability
interview scheduling observability
human approval observability
```

验收：

```text
能解释候选人为什么被推荐/拒绝，能定位 JD 生成和面试安排问题
```

### Stage 4：质量评估体系

交付：

```text
score taxonomy
rule evaluators
human feedback API
LLM judge evaluators
rubric versioning
Langfuse scores
```

验收：

```text
每类招聘任务都有质量分，线上 trace 可被自动/人工评分
```

### Stage 5：Dataset / Experiment / 回归

交付：

```text
bad case pipeline
dataset creation
experiment runner
prompt/model comparison
CI quality gate
release report
```

验收：

```text
每次改 Prompt/模型/Agent 逻辑前，有回归测试和质量报告
```

### Stage 6：运营治理平台

交付：

```text
Debug Console
质量看板
成本看板
招聘复盘页
治理后台
告警机制
周报机制
```

验收：

```text
工程、产品、运营、管理者都能用该平台做决策
```

## 17. 实施优先级

正确顺序：

```text
1. 事件协议
2. Provider 抽象
3. 隐私策略
4. 上下文传播
5. 可靠性队列
6. Langfuse Exporter
7. 主链路埋点
8. LLM / Tool / Agent 深度埋点
9. Evaluation
10. Dataset / Experiment
11. Dashboard / Governance
```

## 18. 最终验收标准

### 工程标准

```text
Langfuse 故障不影响业务
监测代码不污染业务逻辑
所有监测有统一 schema
生产环境默认脱敏
关键链路 trace 完整
所有 LLM 调用可见
所有工具调用可见
```

### 产品标准

```text
能复盘任意一次招聘 Agent 回复
能定位候选人推荐原因
能分析用户差评原因
能发现高失败率工具
能评估 Prompt 改动影响
```

### 运营标准

```text
能看成本
能看质量
能看用户满意度
能看 Agent 健康
能生成周期报告
```

### 安全标准

```text
无明文 PII 泄露
简历全文不上报
敏感字段有测试覆盖
支持数据保留策略
```

## 19. 实施 TODO List

> TODO 拆分原则：先平台地基，再业务接入；先协议和隐私，再 Langfuse；先采集事实，再做评估；先后端闭环，再产品化看板。

### 19.1 Stage 1 — AgentOps 平台地基

- [ ] 创建 `apps/api/app/agentops/` 模块目录结构
- [ ] 定义 `AgentOpsProvider` 抽象接口
- [ ] 定义 `AgentOpsExporter` 抽象接口
- [ ] 实现 `NoopProvider`，确保关闭观测时业务无副作用
- [ ] 实现 `CompositeProvider`，支持未来多 Provider 并行输出
- [ ] 定义 `BaseEvent`、`TraceEvent`、`SpanEvent`、`LLMGenerationEvent`、`ToolInvocationEvent`、`ScoreEvent`
- [ ] 为所有事件增加 `schema_version`
- [ ] 定义事件类型枚举：trace、span、llm、tool、agent、eval、privacy
- [ ] 实现 `AgentOpsContext`，包含 trace_id、span_id、user_id、session_id、tenant_id、request_id、operation_id
- [ ] 使用 `contextvars` 实现异步上下文传播
- [ ] 实现 trace/span/generation/tool/score helper API
- [ ] 增加 `OBSERVABILITY_ENABLED`、`OBSERVABILITY_PROVIDER`、`LANGFUSE_*` 配置项
- [ ] 增加 `LANGFUSE_ENVIRONMENT`、`LANGFUSE_CAPTURE_INPUT`、`LANGFUSE_CAPTURE_OUTPUT` 配置项
- [ ] 在 FastAPI lifespan 中接入 provider shutdown / flush
- [ ] 编写 provider 单元测试
- [ ] 编写 NoopProvider 无副作用测试

### 19.2 Stage 2 — Langfuse Exporter

- [ ] 添加 Langfuse SDK 依赖
- [ ] 实现 `LangfuseExporter`
- [ ] 将内部 `TraceEvent` 映射为 Langfuse trace/root observation
- [ ] 将内部 `SpanEvent` 映射为 Langfuse span
- [ ] 将内部 `LLMGenerationEvent` 映射为 Langfuse generation
- [ ] 将内部 `ToolInvocationEvent` 映射为 Langfuse tool/span
- [ ] 将内部 `ScoreEvent` 映射为 Langfuse score
- [ ] 支持 Langfuse `user_id`、`session_id`、`metadata`、`tags`
- [ ] 支持 Langfuse trace_id 与内部 operation_id 互相关联
- [ ] 实现 Langfuse 发送失败时 warning-only，不影响主业务
- [ ] 实现本地 Langfuse smoke test 脚本
- [ ] 文档化 Langfuse 自托管启动方式和 API key 配置

### 19.3 Stage 3 — 可靠性与传输层

- [ ] 实现异步事件队列
- [ ] 支持队列容量配置
- [ ] 实现队列满策略：`drop_new`、`drop_oldest`、`sample_errors_only`
- [ ] 记录 dropped event 计数
- [ ] 实现 exporter 发送超时控制
- [ ] 实现 5xx 指数退避重试
- [ ] 实现 4xx 不重试策略
- [ ] 实现熔断器：连续失败 N 次后暂停发送
- [ ] 实现半开探测恢复
- [ ] 实现进程退出前 flush
- [ ] 编写 Langfuse 不可用降级测试
- [ ] 编写队列满丢弃策略测试

### 19.4 Stage 4 — 隐私与脱敏治理

- [ ] 梳理招聘业务敏感字段清单
- [ ] 定义 P0/P1/P2 数据分级
- [ ] 复用或扩展 `apps/api/app/agents/pii_filter.py`
- [ ] 实现 `sanitize_input()`
- [ ] 实现 `sanitize_output()`
- [ ] 实现 `sanitize_metadata()`
- [ ] 实现 message sanitizer
- [ ] 实现 tool args sanitizer
- [ ] 实现 tool result sanitizer
- [ ] 实现 attachment metadata sanitizer
- [ ] 生产环境默认禁止上传简历全文
- [ ] 生产环境默认隐藏手机号、邮箱、身份证
- [ ] 对 candidate_name 支持 partial mask
- [ ] 对 email / phone 支持 hash 关联
- [ ] 增加脱敏策略配置文件
- [ ] 增加 PII 泄露检测测试
- [ ] 增加简历全文不上报测试
- [ ] 增加附件 URL 不上报测试

### 19.5 Stage 5 — 主聊天链路 Trace 化

- [ ] 在 FastAPI middleware 中创建 request context
- [ ] 在 `apps/api/app/services/agent_service.py` 的 `route_single()` 创建 root trace
- [ ] 绑定 user_id
- [ ] 绑定 session_id
- [ ] 绑定 request_id
- [ ] 绑定 operation_id
- [ ] 记录脱敏后的用户输入
- [ ] 记录脱敏后的最终回复
- [ ] 记录 attachment metadata，不记录附件原始内容
- [ ] 记录 orchestrator 成功状态
- [ ] 记录 orchestrator fallback 状态
- [ ] 记录 no_handler 状态
- [ ] 记录 `_save_conversation_turn()` span
- [ ] 将 trace_id 写入 response 或 OperationLog metadata
- [ ] 增加主链路 trace smoke test

### 19.6 Stage 6 — LLM Generation 标准化

- [ ] 为 `OMLXClient.chat()` 增加 generation 事件
- [ ] 为 `VLLMClient.chat()` 增加 generation 事件
- [ ] 为 Qwen provider 增加 generation 事件
- [ ] 为 DeepSeek provider 增加 generation 事件
- [ ] 为 Zhipu provider 增加 generation 事件
- [ ] 统一记录 model/provider
- [ ] 统一记录 temperature/max_tokens 等参数
- [ ] 统一记录 input messages，先经过 sanitizer
- [ ] 统一记录 output，先经过 sanitizer
- [ ] 提取并记录 token usage
- [ ] 记录 LLM latency
- [ ] 记录 LLM error type
- [ ] 记录 retry attempt
- [ ] 将 `agent_service.py` 中直接调用 `llm.client.chat.completions.create()` 的位置改为统一包装
- [ ] 标准化 generation 命名：intent、tool_planning、final_response、summary、jd_generate、jd_evaluate
- [ ] 增加 LLM 失败不影响观测系统的测试

### 19.7 Stage 7 — Tool Invocation 标准化

- [ ] 找到工具统一执行入口
- [ ] 为每次 tool call 创建 tool span/event
- [ ] 记录 tool_name
- [ ] 记录脱敏后的 args
- [ ] 记录脱敏后的 result
- [ ] 记录 success/error
- [ ] 记录 retry_count
- [ ] 记录 duration_ms
- [ ] 记录 needs_human
- [ ] 记录 escalation mode
- [ ] 定义 tool category：schedule、candidate、job、resume、search、mcp、memory、approval
- [ ] 定义 tool error taxonomy
- [ ] 增加工具调用成功率指标
- [ ] 增加工具失败 trace 测试

### 19.8 Stage 8 — Orchestrator / Agent Graph 深度观测

- [ ] 为 `intent_recognition` 增加 span
- [ ] 为 `execute_subgraph` 增加 span
- [ ] 为 `create_snapshot` 增加 span
- [ ] 为每个 subgraph 增加 agent span
- [ ] 为 `BaseAgent.run()` 设计通用 span 包装方式
- [ ] 为 `GenEvalLoop` 增加 iteration span
- [ ] 为 JD generate/evaluate/improve 分别记录 generation
- [ ] 为 HumanLoop 增加 span
- [ ] 为 Approval 流程增加 span
- [ ] 在 LangGraph async 执行中保持 AgentOpsContext 不丢失
- [ ] 增加复杂任务 trace 树结构测试

### 19.9 Stage 9 — 招聘业务事件深化

- [ ] 定义 `recruitment.resume.parse.completed` 事件
- [ ] 定义 `recruitment.screening.completed` 事件
- [ ] 定义 `recruitment.jd.generate.completed` 事件
- [ ] 定义 `recruitment.interview.schedule.completed` 事件
- [ ] 定义 `recruitment.offer.completed` 事件
- [ ] 定义 `recruitment.onboarding.completed` 事件
- [ ] 简历解析事件记录 field_completeness、quality_score、red_flags
- [ ] 筛选事件记录 match_score、decision、reason_codes、needs_human_review
- [ ] JD 生成事件记录 iteration_count、final_score、passed_threshold
- [ ] 面试安排事件记录 schedule_success、conflict_detected、tool_calls
- [ ] 所有业务事件只使用业务 ID，不记录明文个人信息

### 19.10 Stage 10 — Evaluation 基础体系

- [ ] 定义 score taxonomy
- [ ] 定义 score schema
- [ ] 实现 `ScoreWriter`
- [ ] 实现 `ToolSuccessEvaluator`
- [ ] 实现 `LatencyEvaluator`
- [ ] 实现 `PIISafetyEvaluator`
- [ ] 实现 `IntentCorrectnessEvaluator`
- [ ] 实现 `ResumeParseQualityEvaluator`
- [ ] 实现 `ScreeningReasonabilityEvaluator`
- [ ] 实现 `JDQualityEvaluator`
- [ ] 实现 `ConversationHelpfulnessEvaluator`
- [ ] 将 evaluator 输出写入 Langfuse scores
- [ ] 为 evaluator 增加 version 字段
- [ ] 为 rubric 增加 version 字段
- [ ] 增加 rule-based evaluator 单元测试

### 19.11 Stage 11 — 用户反馈与人工标注

- [ ] 设计 `POST /api/v1/agent/feedback` API
- [ ] 前端支持 👍 / 👎
- [ ] 前端支持反馈原因选择
- [ ] 前端支持文字反馈
- [ ] feedback 写入 Langfuse score
- [ ] feedback 关联 trace_id/message_id/session_id
- [ ] 定义 bad_case 标记规则
- [ ] 支持将 bad case 推入人工标注队列
- [ ] 定义人工标注字段：错误类型、严重程度、修正建议、是否进 dataset

### 19.12 Stage 12 — Dataset / Experiment / 回归闭环

- [ ] 设计线上 trace 到 dataset item 的转换规则
- [ ] 支持从用户差评生成 dataset item
- [ ] 支持从系统失败生成 dataset item
- [ ] 支持从人工标注生成 dataset item
- [ ] 定义招聘典型测试集：JD、简历解析、筛选、面试安排、工具调用
- [ ] 设计 Prompt experiment 流程
- [ ] 设计模型切换 experiment 流程
- [ ] 设计 Agent 逻辑变更 regression 流程
- [ ] 定义质量门禁阈值
- [ ] 在 CI 中预留 regression gate 接口
- [ ] 输出实验报告模板

### 19.13 Stage 13 — 控制面与治理配置

- [ ] 设计采样规则配置
- [ ] 设计脱敏规则配置
- [ ] 设计评估规则配置
- [ ] 设计 retention 配置
- [ ] 支持按环境覆盖配置
- [ ] 支持按 agent 覆盖采样率
- [ ] 支持错误全采
- [ ] 支持慢请求全采
- [ ] 支持租户级策略
- [ ] 支持角色级可见性策略
- [ ] 记录治理配置变更 audit log

### 19.14 Stage 14 — 看板与产品化页面

- [ ] 设计 Debug Console 信息架构
- [ ] 支持按 trace_id 查询链路
- [ ] 支持查看 LLM generation 列表
- [ ] 支持查看 tool call 列表
- [ ] 支持查看错误堆栈和耗时瀑布图
- [ ] 支持跳转 Langfuse trace
- [ ] 设计招聘任务复盘页
- [ ] 设计质量看板
- [ ] 设计成本看板
- [ ] 设计 Agent 健康看板
- [ ] 设计治理后台
- [ ] 设计周报导出能力
- [ ] 设计异常告警规则

### 19.15 Stage 15 — 验证与上线

- [ ] 本地 Langfuse 自托管验证
- [ ] 测试环境 Langfuse 部署验证
- [ ] 生产部署资源评估：Postgres、Redis、ClickHouse、S3、Web、Worker
- [ ] 验证 UTC timezone 要求
- [ ] 验证 Langfuse health/readiness
- [ ] 验证 API key 权限
- [ ] 验证隐私策略在生产强制生效
- [ ] 验证 Langfuse 故障时业务可用
- [ ] 跑完整系统健康检查
- [ ] 编写运维手册
- [ ] 编写故障排查手册

## 20. TODO 优先级分组

### P0 — 不做不能开始业务接入

- [ ] 事件协议 v1
- [ ] Provider 抽象
- [ ] NoopProvider
- [ ] LangfuseExporter
- [ ] AgentOpsContext
- [ ] PII sanitizer
- [ ] 异步队列与失败隔离

### P1 — 不做不能形成完整可观测链路

- [ ] route_single root trace
- [ ] LLM generation 标准化
- [ ] tool invocation 标准化
- [ ] OperationLog 与 trace_id 关联
- [ ] Orchestrator span
- [ ] session_id 贯通

### P2 — 不做不能形成业务深度

- [ ] 简历解析业务事件
- [ ] 候选人筛选业务事件
- [ ] JD 生成业务事件
- [ ] 面试安排业务事件
- [ ] Agent graph 深度观测

### P3 — 不做不能形成长期优化闭环

- [ ] score taxonomy
- [ ] rule evaluator
- [ ] human feedback
- [ ] LLM-as-Judge
- [ ] dataset pipeline
- [ ] experiment runner
- [ ] CI regression gate

### P4 — 不做不能产品化运营

- [ ] Debug Console
- [ ] 招聘复盘页
- [ ] 质量看板
- [ ] 成本看板
- [ ] 治理后台
- [ ] 告警和周报

## 21. 代码库调研结论（实施前校准）

> 2026-06-09 调研现有后端结构后，对 TODO 做以下校准。结论：第一阶段不要急着接业务链路，先做可独立测试的 `agentops` 地基；不直接改 `agent_service.py`、LLM client、FastAPI middleware，避免把观测系统引入主链路风险。

### 21.1 现有监控基础

已有 Prometheus 指标中心：

```text
apps/api/app/core/telemetry.py
```

已有能力：

```text
HTTP 请求计数 / 延迟
5xx 计数
DB pool 指标
LLM 请求 / token / failure 指标
前端 telemetry 白名单与基础 PII 过滤
```

实施影响：

```text
AgentOps 不替代 core.telemetry。
AgentOps 做 trace / span / generation / score。
Prometheus 继续做聚合指标。
后续可增加 PrometheusExporter，但 P0 先不做。
```

### 21.2 现有隐私基础

已有 PII 工具：

```text
apps/api/app/agents/pii_filter.py
```

已有能力：

```text
strip_pii
mask_pii
strip_pii_from_dict
summarize_prompt_for_audit
summarize_output_for_audit
```

实施影响：

```text
AgentOps privacy.sanitizer 应复用 pii_filter，不重新造正则。
新增逻辑只做字段级 drop/mask/hash 策略。
测试应复用 test_pii_filter.py 的风格。
```

### 21.3 现有 LLM 接入点

LLM 入口：

```text
apps/api/app/llm/omlx_client.py
apps/api/app/llm/vllm_client.py
apps/api/app/llm/cn_providers.py
apps/api/app/services/agent_service.py
```

注意：`agent_service.py` 里存在直接调用：

```python
llm.client.chat.completions.create(...)
```

实施影响：

```text
P0 不改 LLM 调用。
P1 再统一封装 LLM generation，避免第一阶段侵入核心聊天链路。
```

### 21.4 现有 FastAPI 生命周期

生命周期入口：

```text
apps/api/app/main.py
```

已有 lifespan 做：

```text
logging setup
Sentry init
rate-limit store init
schema audit
MCP server load
agent init
recommendation scheduler
aggregation loop
redis/qdrant shutdown
```

实施影响：

```text
P0 不接 main.py，避免启动链路复杂化。
等 agentops provider/queue 测试稳定后，再在 P1 加 init/shutdown。
```

### 21.5 测试风格

测试目录：

```text
apps/api/tests/
```

现有风格：

```text
pytest / pytest.mark.asyncio
unittest.mock.patch / AsyncMock
函数式单测 + 小类组织均存在
```

实施影响：

```text
新增 test_agentops_*.py，优先纯单元测试。
不要依赖数据库、Redis、Langfuse 实例。
Langfuse exporter 用 fake client / import fallback 测试。
```

### 21.6 健康检查约束

代码改动后必须参考：

```text
docs/system-health-check.md
scripts/health-check.sh
```

实施影响：

```text
文档改动无需跑完整健康检查。
后端代码改动后，至少跑新增单测 + 相关后端测试；完成实现后需跑系统健康检查。
```

## 22. 调研后修正的近期开发 TODO

> 这部分替代“直接开始全量 P0”的粗粒度任务。先做可独立验证的 AgentOps 内核，再接 Langfuse，再接主链路。

### 22.1 Sprint A — 纯内核，无外部依赖

- [ ] `apps/api/app/agentops/__init__.py`：创建包入口，只导出稳定 API
- [ ] `apps/api/app/agentops/core/schemas.py`：定义事件枚举与 dataclass/Pydantic schema
- [ ] `apps/api/app/agentops/core/context.py`：定义 `AgentOpsContext` 与 contextvars helper
- [ ] `apps/api/app/agentops/providers/base.py`：定义 provider 协议
- [ ] `apps/api/app/agentops/providers/noop.py`：实现 NoopProvider
- [ ] `apps/api/app/agentops/privacy/sanitizer.py`：复用 `app.agents.pii_filter` 实现输入/输出/metadata 脱敏
- [ ] `apps/api/tests/test_agentops_schemas.py`：验证 schema_version、event_type、to_dict
- [ ] `apps/api/tests/test_agentops_context.py`：验证 contextvars set/reset 与 async 传播
- [ ] `apps/api/tests/test_agentops_noop_provider.py`：验证 NoopProvider 所有方法无副作用
- [ ] `apps/api/tests/test_agentops_sanitizer.py`：验证手机号、邮箱、身份证、简历全文、附件 URL 不泄露

### 22.2 Sprint B — 可靠性层，仍不接业务

- [ ] `apps/api/app/agentops/reliability/circuit_breaker.py`：实现简单熔断器
- [ ] `apps/api/app/agentops/reliability/queue.py`：实现异步事件队列
- [ ] `apps/api/app/agentops/exporters/base.py`：定义 exporter 协议
- [ ] `apps/api/app/agentops/providers/composite.py`：支持多个 provider/exporter 组合
- [ ] `apps/api/tests/test_agentops_circuit_breaker.py`：验证失败阈值、熔断、半开恢复
- [ ] `apps/api/tests/test_agentops_queue.py`：验证 enqueue、flush、drop_new、exporter 抛错不外泄

### 22.3 Sprint C — Langfuse shell，可选依赖

- [ ] `apps/api/app/agentops/exporters/langfuse_exporter.py`：实现 Langfuse exporter shell
- [ ] Langfuse SDK import 必须放函数内部或 try/except 中
- [ ] 未安装 langfuse 时 exporter 初始化不应导致 app import 失败
- [ ] Langfuse key 缺失时自动降级 disabled
- [ ] exporter 发送失败只记录 warning，不抛给业务
- [ ] `apps/api/tests/test_agentops_langfuse_exporter.py`：用 fake client 验证事件映射
- [ ] `apps/api/tests/test_agentops_langfuse_optional.py`：验证未安装/未配置不影响导入

### 22.4 Sprint D — 配置与生命周期，轻接入

- [ ] `apps/api/app/core/config.py`：增加 AgentOps / Langfuse 配置项
- [ ] 配置默认必须是 disabled，避免本地测试被外部服务影响
- [ ] `apps/api/app/agentops/runtime.py`：提供 `get_agentops_provider()` 单例入口
- [ ] `apps/api/app/agentops/runtime.py`：提供 `shutdown_agentops()` flush/shutdown
- [ ] `apps/api/app/main.py`：仅在 lifespan shutdown 阶段调用 `shutdown_agentops()`
- [ ] 不在本阶段创建 FastAPI middleware
- [ ] 不在本阶段改 `agent_service.py`
- [ ] `apps/api/tests/test_agentops_runtime.py`：验证 disabled 默认返回 NoopProvider

### 22.5 Sprint E — 主链路接入前置验证

- [ ] 跑 `python -m pytest tests/test_agentops_*.py`
- [ ] 跑 `python -m pytest tests/test_pii_filter.py tests/test_llm_clients.py`
- [ ] 跑 ruff 针对 `app/agentops` 与新增测试
- [ ] 确认 `app.main` 可 import
- [ ] 再决定是否进入 P1：`route_single()` root trace

## 23. 暂缓项

以下不要在 P0 第一轮做：

- [ ] 不改 `agent_service.py`
- [ ] 不改 LLM client 行为
- [ ] 不改 FastAPI request middleware
- [ ] 不引入强依赖 Langfuse SDK 到全局 import
- [ ] 不接真实 Langfuse 实例
- [ ] 不做前端反馈页
- [ ] 不做 dashboard
- [ ] 不做 Dataset / Experiment
- [ ] 不做 LLM-as-Judge
