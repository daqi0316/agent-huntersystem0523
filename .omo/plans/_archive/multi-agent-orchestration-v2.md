# 多 Agent 协同架构 v2 — 编排 + 协作 + 人工介入 + 前端可见

> 目标：Orchestrator 编排 6 个 Specialist Agent 协同工作，中间可人工介入，前端看到全过程

## 架构总览

### 7 个 Agent

```
OrchestratorAgent (编排中枢)
  │
  ├── SourcingAgent   (寻源)    — JD 生成、候选人搜索、渠道策略、话术模板
  ├── ScreeningAgent  (初筛)    — 简历筛选、多维评分、风险标记
  ├── InterviewAgent  (面试)    — 轮次规划、评价表生成、反馈收集
  ├── OfferingAgent   (Offer)   — 薪酬计算、总包方案
  ├── OnboardingAgent (入职)    — 入职计划、里程碑管理
  └── AnalyticsAgent  (数据)    — 漏斗分析、KPI 报表
```

### 协作模型

```
     OrchestratorAgent
     ┌─────────────────────────────────────┐
     │  shared_context: {                   │
     │    "sourcing.candidates": [...],     │  ← Sourcing 写入
     │    "sourcing.jd": {...},             │  ← Sourcing 写入
     │    "screening.results": [...],       │  ← Screening 写入
     │    "interview.plan": {...},          │  ← Interview 写入
     │    ...                               │
     │  }                                   │
     └─────────────────────────────────────┘
           │ 调度     ▲ 写入     ▲ 读取
           ▼          │         │
     ┌─────────┐ ┌─────────┐ ┌──────────┐
     │Sourcing │→│Screening│→│Interview │→ ...
     └─────────┘ └─────────┘ └──────────┘
```

### 协作数据流（命名空间隔离）

| 输出 Agent | Key | 被谁消费 | Schema |
|-----------|-----|---------|--------|
| Sourcing | `sourcing.candidates` | Screening | `[{id, name, resume_text, ...}]` |
| Sourcing | `sourcing.jd` | Screening | `{title, requirements, ...}` |
| Screening | `screening.results` | Interview | `[{candidate_id, score, passed, ...}]` |
| Screening | `screening.passed_ids` | Interview/Offering | `[candidate_id, ...]` |
| Interview | `interview.plan` | Offering | `{rounds, schedule, ...}` |
| Offering | `offering.package` | Onboarding | `{candidate_id, total, ...}` |

### 人工介入点

Orchestrator 在关键决策点暂停执行，通过 HumanLoop 向用户发送审批请求，用户在前端 approve/reject 后继续。

```
子任务 A (Sourcing) 完成
    │
    ▼
[暂停]  🤖 编排Agent: "已找到 5 位候选人，是否开始初筛？"
    │             用户 → [✅ 批准] / [❌ 拒绝] / [✏️ 修改条件]
    │
    ▼
子任务 B (Screening) 继续执行
```

审批任务通过 `HumanLoopService` 持久化，前端已有的 `/human-loop/pending` endpoint 可以复用。

---

## 当前状态 vs 目标

### 现存能力

| 组件 | 当前状态 |
|------|---------|
| OrchestratorAgent | `is_multi_stage()` ✅ `decompose()` ✅ `build_dag()` ✅ `execute_sub_task()` ⚠️ 路由到 `router_*` 而非 Specialist Agent |
| SourcingAgent | ✅ 纯 Python，有 build_talent_map() 等 |
| ScreeningAgent | ⚠️ run() 调 pipeline.run() 需要 LLM，无 LLM 则挂 |
| InterviewAgent | ⚠️ schedule 纯 Python，evaluation_form 需要 LLM |
| OfferingAgent | ✅ 纯 Python，calculate_total_package() |
| OnboardingAgent | ✅ 纯 Python，generate_plan() |
| AnalyticsAgent | ✅ 纯 Python，build_funnel() |
| HumanLoop | ✅ `human_loop.py` 已有 `get_pending_proposals()` / `approve_proposal()` |
| RouterAgent | ✅ 路由表存在，`chat_with_tools()` Step 2 分发 |
| AgentRegistry | ✅ 自动注册 |
| Bootstrap | ✅ `init_agents()` + `get_router()` |

### 差距

| 差距 | 涉及 |
|-----|------|
| Orchestrator 无法真正调度 Specialist Agent | `execute_sub_task()` 路由不对 |
| 子任务之间没有数据传递 | 缺 shared_context 协议 |
| 人工介入未集成到编排流程 | Orchestrator 没有暂停/等待机制 |
| Agent 从自然语言提取参数能力弱 | 需 LLM 或关键词提取 |
| 前端看不到 Agent 身份 | 接口缺 agent_actions，前端不展示 |

---

## Phase 1: Orchestrator 编排链路打通（3 周任务，可并行的标注 ✅）

### 1.1 修复 Orchestrator → Specialist Agent 路由

**改动文件：** `orchestrator_agent.py`

`execute_sub_task()` 改为：
1. `AgentRegistry.resolve(task_type)` 获取 Specialist Agent（screening → ScreeningAgent）
2. 从 `task.get("description")` 和 `task.get("parameters", {})` 构建 Agent 可识别的 `input_data`
3. 调用 `agent.run(input_data)` 拿到实质结果
4. 捕获 Agent 异常 → 标记 failed，继续执行下一个（不阻断整个流程）

**验证：** Orchestrator.run() 返回结果中每个子任务有 `source_agent` 指向真实 Agent 名称

### 1.2 实现 shared_context 数据传递

**改动文件：** `orchestrator_agent.py`（新增 `SharedContext` 类或字典）

```python
# Orchestrator 新增
shared_context: dict[str, Any] = {}

# Agent 返回结果后自动存入
def _store_result(self, agent_type: str, result: dict) -> None:
    """将 Agent 输出按命名空间存入 shared_context。"""
    self.shared_context[f"{agent_type}.result"] = result
    # 提取关键字段便于下游读取
    summary = result.get("result", {})
    if agent_type == "sourcing":
        self.shared_context["sourcing.candidates"] = summary.get("targets", [])
        self.shared_context["sourcing.jd"] = summary.get("jd", {})
    elif agent_type == "screening":
        self.shared_context["screening.results"] = summary.get("results", [])
        self.shared_context["screening.passed_ids"] = [
            r["candidate_id"] for r in summary.get("results", [])
            if r.get("passed")
        ]

# 下游 Agent 构建 input_data 时注入上游数据
def _build_agent_input(self, task_type: str, task: dict) -> dict:
    base = {"text": task.get("description", ""), "action": task_type}
    if task_type == "screening":
        base["candidate_list"] = self.shared_context.get("sourcing.candidates", [])
        base["jd"] = self.shared_context.get("sourcing.jd", {})
    elif task_type == "interview":
        base["candidate_ids"] = self.shared_context.get("screening.passed_ids", [])
    elif task_type == "offering":
        base["candidate_ids"] = self.shared_context.get("screening.passed_ids", [])
        base["scores"] = self.shared_context.get("screening.results", [])
    return base
```

**验证：** 编排 screening → interview 时，interview 能读到 screening 输出的 candidate_ids

### 1.3 集成 HumanLoop 人工介入

**改动文件：** `orchestrator_agent.py`，`human_loop.py`

Orchestrator 新增 `pause_for_approval()` 方法：

```python
async def pause_for_approval(
    self,
    message: str,
    context: dict,
    timeout_minutes: int = 60,
) -> dict:
    """暂停执行，等待用户审批。"""
    from app.agents.human_loop import HumanLoopAgent
    hl = HumanLoopAgent()
    proposal = await hl.create_proposal(
        title="编排审批",
        description=message,
        context=context,
        timeout_minutes=timeout_minutes,
    )
    # 轮询等待用户决策（或异步回调方式）
    return await hl.wait_for_decision(proposal["id"], timeout_minutes)
```

在编排流程中插入人工介入点：

```python
async def run(self, input_data: dict) -> dict:
    # 分解、执行...
    for level in levels:
        for task in level:
            result = await self.execute_sub_task(task)
            # 是否需要人工介入？
            if task.get("require_approval"):
                approval = await self.pause_for_approval(
                    message=f"{task['type']} 完成，是否继续？",
                    context={"task": task, "result": result},
                )
                if not approval.get("approved"):
                    result["status"] = "rejected"
                    result["rejection_reason"] = approval.get("reason", "")
    # 聚合...
```

**验证：** Orchestrator 执行时遇到 require_approval=True 的子任务后暂停，调用 `human_loop.create_proposal()`，恢复后按用户决策继续或终止

### 1.4 ScreeningAgent 无 LLM 降级（✅ 可与 1.1-1.3 并行）

**改动文件：** `screening_agent.py`

当 LLM 不可用时（pipeline.run 抛异常），降级为规则评分：

```python
async def screen(self, ...):
    try:
        result = await self.pipeline.run({...})
    except Exception as e:
        logger.warning("LLM screening failed, fallback to rule-based: %s", e)
        result = self._rule_based_screen(resume_text, job_requirements)
    ...

def _rule_based_screen(self, resume_text: str, job_requirements: str) -> dict:
    """关键词匹配降级评分。"""
    # 简单关键词匹配 + 基础评分
    skills_found = [s for s in EXTRACTED_SKILLS if s.lower() in resume_text.lower()]
    score = min(len(skills_found) * 20, 100)
    return {
        "overall_score": score,
        "summary": f"规则评分 {score}/100 - 匹配 {len(skills_found)} 个技能",
        "gate_passed": score >= 60,
        "dimensions": {},
        "risks": [],
    }
```

**验证：** `ScreeningAgent.run({"text": "筛选前端工程师", "parameters": {...}})` 在无 LLM 时返回含 `overall_score` 的结果（而非抛异常）

### 1.5 Agent 统一 input/output 协议（✅ 可与 1.1-1.4 并行）

**改动文件：** `base.py`（新增抽象方法）+ 各 `*_agent.py`

```python
class BaseAgent(abc.ABC):
    async def run(self, input_data: dict) -> dict:
        """必须返回统一格式。"""
        ...

    def format_result(self, status: str, result: dict, summary: str) -> dict:
        """统一输出格式。"""
        return {
            "agent": self.name,
            "status": status,           # "completed" | "failed" | "rejected"
            "result": result,           # 结构化数据
            "summary": summary,         # 一句话摘要，前端展示用
            "details": {},              # 详细数据
        }
```

各 Agent 的 `run()` 改为返回 `format_result(...)` 而不是自由格式 dict。

**验证：** 每个 Agent 的 run() 返回结构一致，包含 `agent` / `status` / `result` / `summary` 字段

---

## Phase 2: 前端多 Agent 可见性（1 周）

### 2.1 后端 API 响应增加 agent_actions

**改动文件：** `app/api/agent.py`（AgentChatResponse）

```python
class AgentAction(BaseModel):
    agent: str          # "screening"
    agent_label: str    # "初筛 Agent"
    status: str         # "completed" / "processing" / "failed" / "awaiting_approval"
    summary: str        # "评分 85/100，通过"
    duration_ms: int

class AgentChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
    model: str = ""
    tool_calls: list[AgentToolCallInfo] = []
    agent_actions: list[AgentAction] = []   # ← 新增
```

`chat_with_tools()` 中：
- Orchestrator 执行时：每个子任务产生一个 AgentAction
- RouterAgent 分发时：命中 Specialist 的生成单个 AgentAction
- 降级到 tool loop 时：空列表

**验证：** 输入"筛选张三简历" → API 响应的 `agent_actions` 非空，包含 `agent="screening"`

### 2.2 前端 Agent 气泡 + 步骤展示

**改动文件：** `app/(dashboard)/agent/page.tsx`

- API 响应读取 `agent_actions` 字段
- 每条消息根据 `agent_actions` 渲染 Agent 标签
- Agent 图标映射：
  | Agent | 图标 | 标签 |
  |-------|------|------|
  | orchestrator | 🤖 | 编排 Agent |
  | sourcing | 🎯 | 寻源 Agent |
  | screening | 🔍 | 初筛 Agent |
  | interview | 📅 | 面试 Agent |
  | offering | 💰 | Offer Agent |
  | onboarding | 🚀 | 入职 Agent |
  | analytics | 📊 | 数据 Agent |
- 多 Agent 链式执行时：时间线样式展示每个 Agent 的处理结果
- 单 Agent 分发时：气泡上方显示 Agent 标签

**验证：** Playwright 测试捕获 API 含 agent_actions 的响应，确认 DOM 中出现 Agent 标签

### 2.3 人工介入 UI（审批弹窗）

**改动文件：** `app/(dashboard)/agent/page.tsx`

- 检测 `status="awaiting_approval"` 的 AgentAction
- 展示审批卡片：消息描述 + approve / reject 按钮 + 可选的修改输入
- 调用 `POST /human-loop/{proposal_id}/approve` 或 `/reject`
- 审批后自动重发原消息继续流程

**验证：** 手动测试编排中触发 approve → 流程继续；reject → 流程终止显示拒绝原因

---

## DAG / 依赖关系

```
Phase 1  ── 可并行的任务标注 ✅
  │
  1.1 Orchestrator → Agent 路由修复
  │
  1.2 shared_context 数据传递 ──── 依赖 1.1（需要 Agent 先跑通）
  │
  1.3 HumanLoop 集成 ───────────── 可独立开发（不依赖 1.1/1.2）
  │
  1.4 ScreeningAgent 降级 ──────── ✅ 与 1.1-1.3 完全并行
  │
  1.5 Agent IO 协议统一 ────────── ✅ 与 1.1-1.4 并行，但需在 1.1 用之前定稿
  │                                   建议先做 1.5 再 1.1
  │
  │  → 顺序建议: 1.5 → [1.1 + 1.3 ✅ + 1.4 ✅] → 1.2
  │
Phase 2
  │
  2.1 API 字段增强 ─────────────── 依赖 Phase 1 完成（需要 Orchestrator 产生 agent_actions）
  │
  2.2 前端气泡展示 ─────────────── 依赖 2.1
  │
  2.3 人工介入 UI ──────────────── 依赖 2.1 + 1.3
```

---

## 验证标准

### Phase 1 完成标准
- [ ] Orchestrator.run({"task": "筛选张三简历"}) 返回结果中 `outputs[0].source_agent` = "screening"
- [ ] shared_context 在 screening→interview 链中传递数据
- [ ] HumanLoop 暂停后可以通过 approve/reject 控制流程
- [ ] ScreeningAgent 无 LLM 时降级规则评分，不抛异常
- [ ] 所有 Agent 的 run() 返回 `format_result()` 格式
- [ ] 现有 962 个测试全部通过，新增 15+ 测试

### Phase 2 完成标准
- [ ] API 响应 `agent_actions` 在 Orchestrator 执行时非空
- [ ] 前端气泡显示 Agent 标签（单 Agent 和多 Agent 场景）
- [ ] 人工介入弹窗 approve/reject 可用
- [ ] Playwright 测试覆盖单 Agent / 多 Agent / 降级三种场景
- [ ] 现有 962 个测试全部通过，新增 5+ 测试（含 Playwright）

---

## 测试策略

| 类型 | 覆盖 | 数量 |
|------|------|------|
| pytest 单元测试 | Agent run() 协议一致性、shared_context 存取、HumanLoop 集成、Screening 降级 | Phase 1: 15+ |
| pytest 集成测试 | Orchestrator 编排流程（mock Agent） | Phase 1: 5+ |
| Playwright E2E | 前端气泡、Agent 标签、审批弹窗 | Phase 2: 3+ |

---

## 错误处理策略

| 失败场景 | 行为 |
|---------|------|
| Agent.run() 抛异常 | 标记子任务 failed，继续执行下一个，不阻断全流程 |
| shared_context 读取字段不存在 | 下游 Agent 收到空值，自行处理（用默认参数） |
| HumanLoop 超时未审批 | 任务标记 `awaiting_approval` 状态，用户历史中可见，下次消息触发恢复 |
| LLM 不可用 | ScreeningAgent 降级规则评分，intervewAgent 仅 schedule（不生成评价表） |
| 全链路部分失败 | 返回 `status=partial`，前端展示部分成功的结果 |
