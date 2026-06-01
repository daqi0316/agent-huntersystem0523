# 多 Agent 协同架构 — 编排 + 独立空间 + 前端可见性

> 目标：让 6 个 Specialist Agent 真正独立执行、Orchestrator 负责任务分配、前端看到 Agent 身份
  
## 架构概览

```
用户输入: "筛选张三的简历，安排两轮面试，然后发offer"
  │
  ▼
  OrchestratorAgent
  │
  ├─ decompose() → [screening, interview, offering]
  │  每个 sub_task 含：type + 提取的 parameters + depends_on
  │
  ├─ execute_plan()
  │  按 DAG 分层执行：
  │     Layer 0: ScreeningAgent.run({candidate, resume, job_req})   ← 独立空间
  │              → 输出 {candidate_id, overall_score, ...}
  │     Layer 1: InterviewAgent.run({candidate_id, plan: ...})      ← 依赖上一步输出
  │              → 输出 {interview_plan, ...}
  │     Layer 2: OfferingAgent.run({candidate_id, score, ...})      ← 依赖上一步输出
  │              → 输出 {total_package, ...}
  │
  └─ aggregate() → 汇总结果 + 标明每个结果来自哪个 Agent
       │
       ▼
  前端显示:
    ┌────────────────────────────────────┐
    │ [编排中]  🤖 Orchestrator          │
    │   正在分解任务...                   │
    │ [处理中]  🔍 初筛 Agent            │
    │   评分 85/100 ✅                    │
    │ [处理中]  📅 面试 Agent            │
    │   已生成 2 轮面试计划 ✅             │
    │ [处理中]  💰 Offer Agent           │
    │   总包 ¥500,000/年 ✅               │
    │ [完成]    🤖 Orchestrator          │
    │   全部完成，共 3 个任务              │
    └────────────────────────────────────┘
```

## 当前状态评估

### Specialist Agents 现状

| Agent | run() 依赖 | 纯 Python 行为 | LLM 依赖行为 | 能否独立工作 |
|-------|-----------|---------------|-------------|------------|
| Screening | PipelineAgent(pipeline.run → LLM) | 风险检测、维度扩展 | 简历解析、匹配评分、门控判断 | ❌ 无 LLM 则挂 |
| Interview | LLM(get_llm_client) | schedule_interview_rounds() | 评价表生成、反馈汇总 | ⚠️ 默认 action=schedule 可纯 Python |
| Sourcing | 无 LLM 依赖 | build_talent_map()、渠道策略 | — | ✅ 纯 Python |
| Offering | 无 LLM 依赖 | calculate_total_package() | — | ✅ 纯 Python |
| Onboarding | 无 LLM 依赖 | generate_plan() | — | ✅ 纯 Python |
| Analytics | 无 LLM 依赖 | build_funnel()、calculate_kpi() | — | ✅ 纯 Python |

### orchestration_agent.py 现有 Orchestrator

| 能力 | 当前状态 | 问题 |
|------|---------|------|
| is_multi_stage() | ✅ 关键词检测 | 只检测，不提取参数 |
| decompose() | ✅ LLM 分解 + 关键词降级 | 降级时只返回 guess_type(task)，无结构化参数 |
| build_dag() | ✅ 拓扑排序分层 | 正确 |
| execute_sub_task() | ⚠️ 已实现 | 两个 bug: 1) resolve(`router_{type}`) 而非 Specialist Agent；2) Service 降级返回 stub 无实质结果 |
| run() | ✅ 入口 | 返回格式中 outputs 是扁平列表，无法追溯到具体 Agent |

### 当前 chat_with_tools() 三层分发问题

| 层 | 问题 |
|---|------|
| Step 1: Orchestrator | `is_multi_stage()` 后调 `orchestrator.run()`，但 execute_sub_task 路由到 router_* 而非 Specialist Agent → 要么路由失败降级 stub，要么路由到 ScreeningAgent 后因缺 LLM 抛异常 |
| Step 2: RouterAgent | 分发到 ScreeningAgent/InterviewAgent 后，run() 因缺 LLM 抛异常 → 静默降级到 Step 3 |
| Step 3: LLM tool loop | 用通用 SYSTEM_PROMPT，"你是招聘助手" → 用户感知不到团队 |

### 前端现状

| 层面 | 当前状态 | 问题 |
|-----|---------|------|
| API response | `{reply, model, tool_calls}` | `model` 字段有值（如 "router/screening"）但前端忽略 |
| 消息气泡 | 统一 Bot 图标 + "AI 招聘助手" | 没有 Agent 标识 |
| 多步骤 | 用户发一条 → 等回复 → 显示 | 没有分步进度 |

## 目标架构

```
┌──────────────────────────────────────────────────────┐
│                    Frontend                           │
│  ┌────────────────────────────────────────────────┐  │
│  │  Agent Chat                                    │  │
│  │  [🤖 Orchestrator]  [🔍 初筛] [📅 面试] ...   │  │
│  │  每个 Agent 气泡有独立图标 + 名称 + 状态        │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────┘
                       │ POST /agent/chat
┌──────────────────────▼───────────────────────────────┐
│              chat_with_tools()                        │
│                                                       │
│  Step 1: OrchestratorAgent                            │
│    ├─ decompose() → [SubTask]                         │
│    │   每个 SubTask 含: {type, params, depends_on}    │
│    ├─ AgentRegistry.resolve("screening")              │
│    │   → 拿到 SpecialistAgent 实例                    │
│    ├─ screening.run(context_package)                  │
│    │   → 返回 AgentResult {agent, action, result}     │
│    └─ 聚合 → {reply, agent_actions: [...]}            │
│                                                       │
│  Step 2: RouterAgent (single intent)                  │
│    ├─ classify(text) → intent                         │
│    ├─ route → SpecialistAgent.run()                   │
│    └─ result + agent name                             │
│                                                       │
│  Step 3: LLM tool loop (fallback)                     │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│              Specialist Agents                        │
│                                                       │
│  ScreeningAgent         InterviewAgent                │
│  ├─ 提取 natural lang params                         │  ├─ 提取 params         │
│  ├─ 用 LLM 以初筛专家身份执行                        │  ├─ schedule/pure or LLM│
│  └─ 返回 {score, summary, details}                   │  └─ 返回 {plan, ...}    │
│                                                       │
│  SourcingAgent           OfferingAgent                │
│  ├─ 纯 Python 执行                                    │  ├─ 纯 Python            │
│  └─ 返回 {talent_map, ...}                            │  └─ 返回 {package, ...}  │
│                                                       │
│  OnboardingAgent         AnalyticsAgent               │
│  ├─ 纯 Python                                         │  ├─ 纯 Python            │
│  └─ 返回 {plan, ...}                                  │  └─ 返回 {funnel, ...}   │
└──────────────────────────────────────────────────────┘
```

## 执行计划

### Phase 1: OrchestratorAgent 修复 — 直连 Specialist Agent（3 个任务）

**目标**：Orchestrator 能真正把子任务分发给对应的 Specialist Agent 并拿到实质结果

**1.1 修复 execute_sub_task() 路由**
- 当前 `resolve("router_{type}")` → 改为 `resolve(type)` 拿到 Specialist Agent（screening → ScreeningAgent）
- 构建 Context Package 作为 input_data：`{agent_type, instruction, parameters, context, task_id}`
- 如果 Specialist Agent 不在 Registry 中，再降级到 Service 层
- 验证：Orchestrator 调度后能看到 Agent 返回的真实 agent 名称

**1.2 Specialist Agent 统一输入/输出协议**
- 定义 `AgentInput`：`{text, parameters: dict, context: dict, task_id: str}`
- 定义 `AgentResult`：`{agent: str, status: str, result: dict, summary: str, details: dict}`
- 每个 Agent 的 run() 从 input_data 中提取 parameters，如果 parameters 为空则从 text 中提取
- 每个 Agent 的 run() 返回统一 AgentResult 格式

**1.3 Orchestrator 结果聚合 —— 保留 Agent 溯源**
- `outputs` 改为每个元素标 `source_agent`：`[{type, source_agent, status, result, ...}]`
- 聚合时收集每个 Agent 的 summary 作为最终回复
- 验证：Orchestrator 返回结果中每个子任务能追溯到执行它的 Agent

### Phase 2: Specialist Agent 增强 — 自然语言参数提取 + 带上下文执行（4 个任务）

**目标**：Agent 能从自然语言提取参数，Agent 间能传递上下文

**2.1 ScreeningAgent 增强**
- run() 从 input_data.text 提取 `candidate_name`, `job_title`, `requirements` 等
- 如需 LLM → 用 ScreeningAgent System Prompt + 专有工具调用，不走 pipeline.run()
- 提取的参数填充到 screen(candidate_id, resume_text, job_requirements) 调用
- 验证：输入"筛选张三的简历" → 输出有实质分数和摘要

**2.2 InterviewAgent 增强**
- 默认 action=schedule，schedule_interview_rounds() 已纯 Python 可用
- 从 text 提取 `candidate_name`, `rounds`, `interview_type`
- 如需 evaluation_form → 用 InterviewAgent System Prompt + LLM
- 验证：输入"安排张三两轮面试" → 生成有轮次细节的面试计划

**2.3 Agent 间上下文传递（Collaboration）**
- SubTask 的输出存到 Orchestrator 的 shared_context 中
- 后续 SubTask 可以从 shared_context 读取前置 Agent 的输出
- 例如：ScreeningAgent 输出 `{candidate_id: "xxx", overall_score: 85}` → InterviewAgent 读取 `candidate_id` 作为输入
- 验证：screening → interview → offering 链式调用时下游能读到上游的输出

**2.4 SourcingAgent/OfferingAgent/OnboardingAgent/AnalyticsAgent 统一**
- 统一 input/output 协议（同 1.2）
- 确保纯 Python 逻辑能从 parameters 中正确读取输入
- 添加从 text 提取参数的能力（LLM 降级时用关键词默认值）

### Phase 3: Frontend 多 Agent 可见性（2 个任务）

**目标**：用户在界面上能看到哪个 Agent 在处理、处理过程、处理结果

**3.1 后端 API 响应增强**
- `AgentChatResponse` 新增字段：
  ```python
  class AgentAction(BaseModel):
      agent: str         # "screening" / "interview" / ...
      agent_label: str   # "初筛 Agent" / "面试 Agent" / ...
      status: str        # "completed" / "processing" / "failed"
      summary: str       # 该 Agent 处理摘要
      duration_ms: int
  
  agent_actions: list[AgentAction] = []
  ```
- 当 Orchestrator 执行时，每个子任务对应一个 AgentAction
- 当 RouterAgent 分发时，命中 specialist 的记录为单个 AgentAction
- 当 chat 降级时，agent_actions 为空

**3.2 前端 Agent 气泡展示**
- 消息组件增加 `agent` 字段渲染：
  - 普通 assistant 消息 → 现有 Bot 图标
  - 有 agent 的消息 → 显示 Agent 专属图标 + 名称标签
  - 多 Agent 链式消息 → 折叠展开 / 时间线样式
- Agent 图标映射：
  - screening → 🔍 初筛 Agent
  - interview → 📅 面试 Agent
  - sourcing → 🎯 寻源 Agent
  - offering → 💰 Offer Agent
  - onboarding → 🚀 入职 Agent
  - analytics → 📊 数据 Agent
  - orchestrator → 🤖 编排 Agent
- 每个 AgentAction 显示为内联标签或卡片
- 验证：用户输入"筛选张三的简历" → 回复气泡顶部显示 `🔍 初筛 Agent`

## 验证规则

- 每个 Phase 完成后：`lsp_diagnostics clean` + 现有 pytest 不能变红
- Phase 1 完成后：Orchestrator 调度子任务返回结果中有 `source_agent` 字段
- Phase 2 完成后：Agent 能从自然语言提取非空参数；screening → interview 链式调用能传递数据
- Phase 3 完成后：API 响应包含 agent_actions；前端显示 Agent 标签
- 每个 Phase 新增 5+ 个测试

## 依赖图

```
Phase 1 ────────────────── Phase 2 ────────────── Phase 3
                                                          
1.1 fix execute_sub_task ─────┐                            
        │                     │                            
        ▼                     ▼                            
1.2 Agent IO protocol ──→ 2.1 ScreeningAgent ──→ 3.1 API enhanced
        │                     │                     │        
        ▼                     ▼                     ▼        
1.3 Orchestrator agg ────→ 2.2 InterviewAgent     3.2 Frontend UI
                           │                     
                           ▼                    
                           2.3 Agent context passing
                           │                     
                           ▼                    
                           2.4 Unify remaining agents
```
