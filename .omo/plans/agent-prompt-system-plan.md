# Agent 提示词系统升级计划

## 审核结论

### ✅ 代码库现有基础设施质量高（无需重写）
| 组件 | 状态 | 说明 |
|------|------|------|
| `BaseAgent` | ✅ 扎实 | 统一输出协议、自动注册、Prompt 加载 |
| `AgentRegistry` | ✅ 完整 | 注册/解析/状态/注销 |
| `OrchestratorAgent` (635行) | ✅ 扎实 | LLM 分解 + 关键词降级 + DAG 调度 + HumanLoop |
| `RouterAgent` (180行) | ✅ 扎实 | 11 意图、双策略分类 |
| `MessageBus` | ✅ 扎实 | 类型化事件、pub/sub、事件历史 |
| `SharedMemory` | ✅ 扎实 | Redis → InMemory、TTL |
| `HumanLoopAgent` (292行) | ✅ 完整 | Redis 持久化、过期、审批历史 |
| `ScreeningAgent` (287行) | ✅ 扎实 | 6 维评估、风险标记、规则兜底 |
| `InterviewAgent` (254行) | ✅ 扎实 | LLM 评价表生成 + 反馈汇总 + 规则降级 |
| `SourcingAgent` (183行) | ✅ 完整 | Mapping/渠道/话术/JD 生成 |
| `OfferingAgent` (235行) | ✅ 完整 | 定薪/Offer函/谈判策略/风险评估 |
| `AnalyticsAgent` (198行) | ✅ 完整 | 漏斗/渠道/KPI/异常检测 |
| `OnboardingAgent` (148行) | ✅ 完整 | 里程碑/Check-in/转正评估 |
| `PII/Security` | ✅ 完整 | PII 脱敏、权限检查 |
| `AuditLogger` | ✅ 完整 | 审计日志 |

### 🔴 核心差距：提示词文件过浅
所有 8 个 `prompts/*.md` 文件（26-45 行）只是大纲，缺少：

- **角色定义**：每个 Agent 的中文角色身份（如"篩官"、"猎手"）
- **执行协议**：特定场景下的行为规则、推理步骤
- **行为约束**：边界条件、不得做的事项
- **质量门控**：输出质检规则、降级阈值
- **详细输出 Schema**：完整的 JSON 结构定义

### 🟡 功能性差距（优先级低）

| 缺失项 | 说明 | 影响 | 定级 |
|--------|------|------|------|
| GSSC 上下文管道 | Gather→Score→Select→Compose | 当前 flat shared_context 在小窗口中可能含无关数据，但尚未出现实际污染问题 | P2 |
| 工具注册中心 | 无集中 Schema 管理 | 工具在各 Agent 中硬编码，但 Agent 当前全部 stateless，注册中心暂时闲置 | P2 |
| A2A 5 模式 | 仅实现了广播 | 缺少 request-reply/pipeline/escalate/join | P2 |
| 四层记忆 | 工作/情景/语义/感知 | 当前只有 KV 存储，但 Agent 全 stateless 不依赖精化/遗忘 | P3 |
| screen_resume 精筛 Agent | Router 没配，但 Orchestrator 映射到 screening | 当前无独立 Agent，功能合并到 screening 中 | 未来 |

---

## 执行计划

**总原则**：最大化现有基础设施的价值。不重写任何已工作良好的代码，专注于提示词文件升级。

**不受此计划影响的文件**：
- `base.py` — prompt 加载机制不变
- `agents/__init__.py` — 导出列表不变
- `screening_agent.py`, `sourcing_agent.py` 等 7 个 Agent 实现 — 代码逻辑不变
- `registry.py`, `message_bus.py`, `shared_memory.py` — Phase 1 不动

### Phase 1 — 重写全部 8 个提示词文件（P0）

基于文档 `Ai 招聘Agent 提示词系统.md` 的内容，逐文件重写。

#### 内容来源映射

| 文件 | 文档来源 | 代码参考 |
|------|---------|---------|
| `screening.md` | §3 Prompt-C（第295-426行） | `screening_agent.py` (287行) |
| `sourcing.md` | §2 Prompt-B（第158-293行） | `sourcing_agent.py` (183行) |
| `orchestrator.md` | §1 Type-A + §10 上下文工程（第6-156行 + 第1300-1347行） | `orchestrator_agent.py` (635行) |
| `router.md` | §1 任务路由规则（第55-98行） | `router_agent.py` (180行) |
| `interview.md` | §4 Prompt-D（第428-585行） | `interview_agent.py` (254行) |
| `analytics.md` | §7 Prompt-G（第912-1059行） | `analytics_agent.py` (198行) |
| `offering.md` | §5 Prompt-E（第587-749行） | `offering_agent.py` (235行) |
| `onboarding.md` | §6 Prompt-F（第751-910行） | `onboarding_agent.py` (148行) |

#### 1.1 `prompts/screening.md` → 从 38 行 → ~100 行
- 保留现有 6 维评估和风险标记结构
- 增加：角色定义（篩官）、4 维评估框架（硬性/软性/动机/潜力）、评分标准与一票否决、执行协议
- 来源：文档 §3（Prompt-C），代码 `screening_agent.py`

#### 1.2 `prompts/sourcing.md` → 从 45 行 → ~100 行
- 保留现有 4 项能力和输出格式
- 增加：角色定义（猎手）、ReAct 循环协议、渠道优先级矩阵、Mapping 方法论
- 来源：文档 §2（Prompt-B），代码 `sourcing_agent.py`

#### 1.3 `prompts/orchestrator.md` → 从 45 行 → ~100 行
- 增加：角色定义（调度中樞）、GSSC 协议概要、任务路由规则（6 种 Agent 触发词）、多 Agent 协作规则（串行/并行/反馈循环/聚合）、安全策略
- 来源：文档 §1（Type-A）+ §10，代码 `orchestrator_agent.py`

#### 1.4 `prompts/router.md` → 从 26 行 → ~80 行
- 保留现有 11 种意图列表
- 增加：置信度分档、多意图加权、未知意图处理规则
- 来源：文档 §1 路由规则，代码 `router_agent.py`

#### 1.5 `prompts/interview.md` → 从 35 行 → ~80 行
- 保留现有 4 轮面试标准和评价表模板
- 增加：角色定义（面試官助理）、面试流程设计协议、BEI 问题库（6 维度）、面试官匹配算法
- 来源：文档 §4（Prompt-D），代码 `interview_agent.py`

#### 1.6 `prompts/analytics.md` → 从 43 行 → ~80 行
- 保留现有 KPI 指标和输出格式
- 增加：角色定义（數據官）、6 类指标体系（效率/质量/成本/多样性/渠道/预测）、分析原则
- 来源：文档 §7（Prompt-G），代码 `analytics_agent.py`

#### 1.7 `prompts/offering.md` → 从 35 行 → ~80 行
- 保留现有薪酬计算和谈判策略
- 增加：角色定义（談判專家）、总包构成框架、薪酬带宽设计、5 场景谈判策略矩阵
- 来源：文档 §5（Prompt-E），代码 `offering_agent.py`

#### 1.8 `prompts/onboarding.md` → 从 41 行 → ~80 行
- 保留现有 8 大里程碑
- 增加：角色定义（迎新官）、5 阶段入职旅程地图、风险信号监测
- 来源：文档 §6（Prompt-F），代码 `onboarding_agent.py`

#### Phase 1 Verification Gate
每文件完成后验证：
1. `load_prompt(name)` 能正常加载 → 返回非空字符串
2. 文件对比 git diff — 确认新内容包含角色定义+执行协议+输出 Schema
3. 现有 `tests/test_prompts.py` 通过

### Phase 2 — 补充功能性能力（P1→P2 降级）

#### 2.1 GSSC 上下文管道（~200 行新代码）
- 在 `orchestrator_agent.py` 中新增 `_gather_context()` / `_score_context()` / `_select_context()` / `_compose_context()`
- 对 shared_context 中的数据按相关性评分，只注入高相关条目到 Agent input
- **定级说明**：当前没有上下文污染报告，P2 合理。先不管。

#### 2.2 Agent 工具注册中心（~100 行新代码）
- 新建 `agents/tool_registry.py`
- 每个 Agent 声明其可用工具（名称、描述、参数 Schema）
- Orchestrator/Router 可发现 Agent 的可见能力
- **定级说明**：Agent 全 stateless，注册中心暂时闲置。P2。

### Phase 3 — 增强模式（P2→P3 降级）

#### 3.1 A2A 通信模式（~200 行新代码）
- 在 `message_bus.py` 中新增 request-reply 通道
- 新增 pipeline 模式（链式执行的事件驱动版）
- 新增 escalate 模式（失败时自动升级）

#### 3.2 四层记忆系统（~600-800 行新代码）
- 在现有 `shared_memory.py` 基础上扩展
- 新增 `ConsolidationPipeline`（从工作记忆→语义记忆的精化）
- 新增 `ImportanceScorer`（自动评分）
- 新增 4 层存储分离、遗忘策略、记忆生命周期管理
- **定级说明**：所有 Agent stateless，精化管道加上也是闲置。P3。

---

## 文件变更清单

```
Modified (8 prompt files):
  apps/api/app/agents/prompts/screening.md      ← 文档§3
  apps/api/app/agents/prompts/sourcing.md       ← 文档§2
  apps/api/app/agents/prompts/orchestrator.md   ← 文档§1+§10
  apps/api/app/agents/prompts/router.md         ← 文档§1路由规则
  apps/api/app/agents/prompts/interview.md      ← 文档§4
  apps/api/app/agents/prompts/analytics.md      ← 文档§7
  apps/api/app/agents/prompts/offering.md       ← 文档§5
  apps/api/app/agents/prompts/onboarding.md    ← 文档§6

**Phase 1 不涉及以下文件**（保持不变）:
  base.py, __init__.py, registry.py, message_bus.py, shared_memory.py,
  screening_agent.py, sourcing_agent.py, interview_agent.py,
  offering_agent.py, onboarding_agent.py, analytics_agent.py,
  router_agent.py, orchestrator_agent.py, human_loop.py
```

## 验证步骤

| Phase | 验证方法 |
|-------|---------|
| Phase 1 每文件 | `load_prompt(name)` 非空, git diff 确认内容, test_prompts.py 通过 |
| Phase 1 全部完成 | `get_available_prompts()` 返回 8 个, 所有 agent `system_prompt` 非空 |
| Phase 2+ | pytest 通过, LSP 无错误 |

## 实施顺序

```
Phase 1 (8 prompt files) → 全部并行独立，无交叉依赖
Phase 2.1 (GSSC) + 2.2 (tool registry) → 可并行
Phase 3.1 (A2A) + 3.2 (4-layer memory) → 可并行，但都排到 Phase 2 之后
```
