# 多 Agent 协同架构 v3 — 编排 + 协作 + 人工介入 + 前端可见

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

Orchestrator 通过 `shared_context` 在 Agent 间传递数据，命名空间隔离。

```
     OrchestratorAgent.shared_context
     ┌─────────────────────────────────────┐
     │  "sourcing.candidates": [...]       │
     │  "sourcing.jd": {...}               │
     │  "screening.results": [...]         │
     │  "interview.plan": {...}            │
     │  ...                                │
     └─────────────────────────────────────┘
           │ 调度     ▲ 声明式写入
           ▼          │
     ┌─────────┐ ┌─────────┐ ┌──────────┐
     │Sourcing │→│Screening│→│Interview │→ ...
     └─────────┘ └─────────┘ └──────────┘
     (output_keys 声明)  (output_keys 声明)
```

### "独立任务空间"定义

| 维度 | 定义 |
|------|------|
| 代码隔离 | 每个 Agent 独立文件，不互相 import |
| 数据隔离 | 各 Agent 通过 `share_context` 交换数据，不直接读取其他 Agent 的内部状态 |
| 工具隔离 | 各 Agent 可声明自己需要的 skill/tool 列表（当前未实现，保留扩展点） |
| 执行隔离 | 各 Agent 的 `run()` 无副作用的纯函数式调用（输入 dict → 输出 dict） |
| 物理 | 同一进程内（不拆分微服务，避免复杂化） |

### 人工介入流程

```
子任务完成
    │
    ▼
Orchestrator 检查 task.require_approval
    │
    ├─ False → 继续执行
    │
    └─ True  → HumanLoop.create_proposal()
                │
                ▼
               持久化编排状态到 Redis（shared_context + 执行位置 + session_id）
                │
                ▼
               返回 pending 状态给前端
               前端展示审批卡片
                │
                ▼
               用户 approve/reject
               POST /orchestrator/resume/{session_id}?decision=approve
                │
                ▼
               Redis 读取编排状态
               恢复执行
```

不轮询，不阻塞请求。编排状态存 Redis。

### chat_with_tools() Phase 1 后的架构

```python
async def chat_with_tools(messages, ...):
    last_user_msg = extract_last_user_message(messages)

    # ── Step 1: 统一走 Orchestrator ──
    if last_user_msg:
        from app.agents.bootstrap import get_orchestrator
        orchestrator = get_orchestrator()

        is_multi = orchestrator.is_multi_stage(last_user_msg)
        if is_multi:
            # 多阶段→走 decompose + DAG 编排
            result = await orchestrator.run({"task": last_user_msg, ...})
        else:
            # 单意图→ Orchestrator 直接路由到对应 Specialist Agent
            result = await orchestrator.route_single(last_user_msg)

        return {
            "reply": _build_reply(result),          # 自然语言摘要
            "tool_calls": [],
            "model": f"orchestrator/{result.get('status')}",
            "agent_actions": _extract_actions(result),  # 给前端展示
        }

    # ── Step 2: LLM tool loop（仅当前面都失败时的降级）──
    ...
```

**注意：** RouterAgent 不再在 `chat_with_tools()` 中直接分发。RouterAgent 降级为 Orchestrator 内部的分类器（classify() 方法）。所有用户消息的分发决策都由 Orchestrator 统一做。

---

## 当前状态 vs 目标

| 组件 | 当前状态 |
|------|---------|
| Orchestrator | ⚠️ `is_multi_stage()`, `decompose()`, `build_dag()`, `execute_sub_task()` 均存在，但 `execute_sub_task()` 路由到 `router_*` 而非 Specialist Agent |
| SourcingAgent | ✅ 纯 Python，有 `build_talent_map()` 等 |
| ScreeningAgent | ⚠️ `run()` 调 `pipeline.run()` 需 LLM，无 LLM 挂 |
| InterviewAgent | ⚠️ schedule 纯 Python，evaluation_form 需 LLM |
| OfferingAgent | ✅ 纯 Python |
| OnboardingAgent | ✅ 纯 Python |
| AnalyticsAgent | ✅ 纯 Python |
| HumanLoop | ✅ 已有 `create_proposal()`, `get_pending_proposals()`, `approve_proposal()` |
| RouterAgent | ✅ 路由表存在，`chat_with_tools()` Step 2 在用 |
| AgentRegistry | ✅ 自动注册 |

---

## Phase 1: 后端编排链路

### 1.1 修复 Orchestrator 路由 + 统一 IO 协议（B1 修正：合并原 1.1+1.5）

**改动文件：** `base.py`, `orchestrator_agent.py`, `screening_agent.py`, `interview_agent.py`, `sourcing_agent.py`, `offering_agent.py`, `onboarding_agent.py`, `analytics_agent.py`

**A) BaseAgent 统一输出格式**

```python
class BaseAgent(abc.ABC):
    @abstractmethod
    async def run(self, input_data: dict) -> dict:
        """每个 Agent 必须返回统一格式。"""

    # Agent 声明自己的输出 key（B2 修正：不硬编码在 Orchestrator）
    output_keys: list[str] = []

    # 自动注册到 AgentRegistry + 加载 System Prompt
```

```python
# 统一输出格式
{
    "agent": str,       # e.g. "screening"
    "status": str,      # "completed" | "failed" | "rejected"
    "summary": str,     # 一句话摘要，前端直接展示
    "result": dict,     # 结构化数据（含 output_keys 对应的字段）
    "details": dict,    # 详细数据（调试用）
}
```

**B) 各 Agent 声明 output_keys**

```python
class SourcingAgent(BaseAgent):
    output_keys = ["candidates", "jd"]

class ScreeningAgent(BaseAgent):
    output_keys = ["results", "passed_ids"]

class InterviewAgent(BaseAgent):
    output_keys = ["plan"]

class OfferingAgent(BaseAgent):
    output_keys = ["package"]

class OnboardingAgent(BaseAgent):
    output_keys = ["plan"]

class AnalyticsAgent(BaseAgent):
    output_keys = ["funnel", "kpi"]
```

**C) execute_sub_task() 按新协议调用 Agent**

```python
async def execute_sub_task(self, task: dict) -> dict:
    task_type = task.get("type")
    agent = AgentRegistry.resolve(task_type)
    if agent is None:
        return await self._execute_service_task(task_type, task)

    input_data = self._build_agent_input(task_type, task)
    try:
        result = await agent.run(input_data)
        # 统一格式：自动补全缺失字段
        return {
            "agent": result.get("agent", task_type),
            "status": result.get("status", "completed"),
            "result": result.get("result", {}),
            "summary": result.get("summary", ""),
            "details": result.get("details", {}),
        }
    except Exception as e:
        return {
            "agent": task_type,
            "status": "failed",
            "result": {},
            "summary": f"{task_type} 处理失败: {str(e)[:100]}",
            "details": {"error": str(e)},
        }
```

**D) _build_agent_input 从 shared_context 注入**

```python
def _build_agent_input(self, task_type: str, task: dict) -> dict:
    input_data = {
        "text": task.get("description", ""),
        "action": task.get("action", task_type),
    }
    # 注入 upstream data：按各 Agent output_keys 从 shared_context 读取
    for key in self.shared_context:
        namespace = key.split(".")[0]  # e.g. "sourcing.candidates" → "sourcing"
        if namespace != task_type:  # 注入其他 Agent 的输出
            input_data[key] = self.shared_context[key]
    return input_data
```

**E) _store_result 声明式（B2 修正）**

```python
def _store_result(self, agent: BaseAgent, task_type: str, result: dict) -> None:
    """遍历 Agent 声明的 output_keys，自动按命名空间写入 shared_context。"""
    result_data = result.get("result", {})
    for key in agent.output_keys:
        if key in result_data:
            self.shared_context[f"{task_type}.{key}"] = result_data[key]
    # 也存完整结果
    self.shared_context[f"{task_type}.full"] = result_data
```

不硬编码任何 Agent 类型。新 Agent 只需声明 `output_keys`。

**F) 不阻断策略**

```python
for level in levels:
    coros = [self.execute_sub_task(sub_tasks[i]) for i in level]
    level_results = await asyncio.gather(*coros, return_exceptions=True)
    for i, raw in zip(level, level_results):
        if isinstance(raw, Exception):
            results[i] = {
                "agent": sub_tasks[i].get("type", "unknown"),
                "status": "failed",
                "summary": f"执行异常: {str(raw)[:100]}",
                "result": {},
            }
        else:
            results[i] = raw
            self._store_result(sub_tasks[i].get("type"), raw)
```

**验证：** Orchestrator.run({"task": "筛选张三"}) 返回 outputs 中每个子任务有 `agent` 字段

### 1.2 shared_context 声明式数据传递（依赖 1.1）

**改动文件：** `orchestrator_agent.py`

（已在 1.1 的 _store_result 和 _build_agent_input 中实现。本任务负责验证和测试。）

**验证：**
- Sourcing → Screening 链：Sourcing 输出 `result.candidates` → shared_context 中 `sourcing.candidates` 出现 → Screening 的 `input_data` 中 `sourcing.candidates` 可用
- Screening → Interview 链同样验证

### 1.3 HumanLoop 集成 — 回调模式（M1 修正）

**改动文件：** `orchestrator_agent.py`, `human_loop.py`, 可能新增 `api/orchestrator.py`

**A) 编排状态持久化（M3 修正）**

```python
# orchestrator_agent.py
import json, hashlib

class OrchestratorSession:
    """编排会话状态，存 Redis。"""
    def __init__(self, session_id: str, sub_tasks: list, shared_context: dict,
                 current_level: int, current_index: int, results: list):
        self.session_id = session_id
        self.sub_tasks = sub_tasks
        self.shared_context = shared_context
        self.current_level = current_level
        self.current_index = current_index
        self.results = results

    def to_dict(self):
        return { ... }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

# 状态存储接口
async def save_session(self, session: OrchestratorSession):
    key = f"orchestrator:session:{session.session_id}"
    await self._redis.set(key, json.dumps(session.to_dict()), ex=3600)

async def load_session(self, session_id: str) -> OrchestratorSession | None:
    key = f"orchestrator:session:{session_id}"
    data = await self._redis.get(key)
    return OrchestratorSession.from_dict(json.loads(data)) if data else None
```

**B) 暂停与恢复**

```python
async def pause_for_approval(self, task: dict, result: dict) -> dict:
    from app.agents.human_loop import HumanLoopAgent

    # 1. 生成 session_id
    session_id = hashlib.md5(f"{datetime.now()}:{id(self)}".encode()).hexdigest()[:12]

    # 2. 保存当前编排状态到 Redis
    session = OrchestratorSession(
        session_id=session_id,
        sub_tasks=self.sub_tasks,
        shared_context=self.shared_context,
        current_level=self.current_level_idx,
        current_index=self.current_task_idx,
        results=self.results,
    )
    await self.save_session(session)

    # 3. 创建审批提案
    hl = HumanLoopAgent()
    proposal = await hl.create_proposal(
        title=f"编排审批: {task.get('type', '')} 完成",
        description=task.get("description", ""),
        context={"session_id": session_id, "task": task, "result": result},
        metadata={"orchestrator_session": session_id},
    )

    # 4. 返回 pending 状态（前端轮询或等待 resume）
    return {
        "status": "awaiting_approval",
        "proposal_id": proposal["id"],
        "session_id": session_id,
        "summary": f"等待审批: {task.get('description', '')}",
    }
```

**C) 恢复端点**

```python
# api/orchestrator.py
@router.post("/resume/{session_id}")
async def resume_orchestration(
    session_id: str,
    decision: str = Body(...),  # "approve" | "reject"
    reason: str = Body(""),
):
    """用户审批后恢复编排执行。"""
    from app.agents.bootstrap import get_orchestrator
    orch = get_orchestrator()
    result = await orch.resume(session_id, decision, reason)
    return {"success": True, "data": result}
```

```python
# orchestrator_agent.py
async def resume(self, session_id: str, decision: str, reason: str) -> dict:
    session = await self.load_session(session_id)
    if session is None:
        return {"status": "error", "summary": "编排会话已过期或不存在"}

    # 恢复状态
    self.shared_context = session.shared_context
    self.sub_tasks = session.sub_tasks
    self.results = session.results

    if decision == "reject":
        current = self.sub_tasks[session.current_index]
        self.results[session.current_index] = {
            "agent": current.get("type"),
            "status": "rejected",
            "summary": f"用户拒绝: {reason}",
            "result": {},
        }
        # 标记后续有依赖的任务也失败
        self._mark_dependents_failed(session.current_index, reason)
    # else: approve → 继续执行，不需要修改

    # 从暂停点继续
    return await self._execute_from(session.current_level, session.current_index)
```

**D) chat_with_tools 中处理 await_approval**

```python
# 当 Orchestrator 返回 await_approval 时
if result.get("status") == "awaiting_approval":
    return {
        "reply": f"需要你的审批: {result.get('summary', '')}",
        "model": "orchestrator/awaiting_approval",
        "agent_actions": [{
            "agent": "orchestrator",
            "agent_label": "编排 Agent",
            "status": "awaiting_approval",
            "summary": result.get("summary", ""),
            "proposal_id": result.get("proposal_id"),
            "session_id": result.get("session_id"),
        }],
    }
```

**验证：** 
- approve → 编排从暂停点继续执行
- reject → 当前任务标记 rejected，依赖它的下游跳过
- session 过期 → 返回错误，不崩溃

### 1.4 ScreeningAgent 规则降级（✅ 并行独立）

**改动文件：** `screening_agent.py`

```python
async def screen(self, candidate_id, job_id, resume_text, job_requirements):
    try:
        result = await self.pipeline.run({...})
    except Exception as e:
        logger.warning("LLM screening failed, fallback to rule-based: %s", e)
        result = self._rule_based_screen(resume_text, job_requirements)
    ...

def _rule_based_screen(self, resume_text, job_requirements) -> dict:
    # TF 关键词匹配
    required_skills = self._extract_skills(job_requirements)
    found = [s for s in required_skills if s.lower() in resume_text.lower()]
    score = min(round(len(found) / max(len(required_skills), 1) * 100), 100)

    # 降级结果标记置信度（m3 修正）
    return {
        "overall_score": score,
        "summary": f"规则评分 {score}/100（低置信度，LLM 不可用）",
        "gate_passed": score >= 60,
        "gate_result": {
            "gate_passed": score >= 60,
            "needs_human_review": True,  # 降级结果标记需人工复核
            "gate_summary": f"规则评分，建议人工复核。匹配 {len(found)}/{len(required_skills)} 个技能",
        },
        "match_result": {"overall_score": score, "strengths": found, "weaknesses": []},
        "risks": [{"type": "llm_unavailable", "severity": "warning",
                   "description": "LLM 不可用，使用规则评分，仅供参考"}],
    }
```

**验证：** 无 LLM 时返回含 `overall_score` 和 `needs_human_review=True` 的结果，不抛异常

### 1.5 chat_with_tools() 重构（M2 修正）

**改动文件：** `agent_service.py`

```python
async def chat_with_tools(messages, user_id=None, session_id=None, ...):
    await _register_builtins()

    last_user_msg = extract_last_message(messages)

    if last_user_msg:
        # Step 1: Orchestrator 统一处理（RouterAgent 不再直接分发）
        try:
            from app.agents.bootstrap import get_orchestrator
            orch = get_orchestrator()
            is_multi = orch.is_multi_stage(last_user_msg)

            if is_multi:
                result = await orch.run({
                    "task": last_user_msg,
                    "context": {"user_id": user_id, "session_id": session_id},
                })
            else:
                result = await orch.route_single({
                    "text": last_user_msg,
                    "context": {"user_id": user_id, "session_id": session_id},
                })

            if result.get("status") == "awaiting_approval":
                return _build_approval_response(result)

            return {
                "reply": _summarize_orch_result(result),
                "tool_calls": [],
                "model": f"orchestrator/{result.get('status', 'completed')}",
                "agent_actions": _extract_agent_actions(result),
            }
        except Exception as e:
            logger.warning("Orchestrator failed, fallback to tool loop: %s", e)

    # Step 2: LLM tool loop（降级）
    return await _tool_calling_loop(messages, user_id, ...)
```

**注意：** `OrchestratorAgent` 新增 `route_single()` 方法——不走 decompose/DAG，直接 classify → 分发到对应 Specialist Agent。

```python
async def route_single(self, input_data: dict) -> dict:
    """单意图快捷路由。"""
    from app.agents.router_agent import RouterAgent
    router = RouterAgent()
    intent = router.classify(input_data)  # 只分类，不分发
    agent = AgentRegistry.resolve(intent)
    if agent:
        result = await agent.run(input_data)
        return {
            "status": "completed",
            "outputs": [result],
            "total_sub_tasks": 1,
            "succeeded": 1,
            "failed": 0,
        }
    return {"status": "no_handler", "outputs": [], "total_sub_tasks": 0, ...}
```

---

## Phase 2: 前端多 Agent 可见性

### 2.1 后端 API 响应增强

**改动文件：** `api/agent.py`

```python
class AgentAction(BaseModel):
    agent: str
    agent_label: str
    status: str                    # "completed" | "processing" | "failed" | "awaiting_approval"
    summary: str
    duration_ms: int = 0
    proposal_id: str | None = None  # 人工审批时非空
    session_id: str | None = None   # 人工审批时非空

class AgentChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
    model: str = ""
    tool_calls: list[AgentToolCallInfo] = []
    agent_actions: list[AgentAction] = []
```

`_extract_agent_actions()` 从 Orchestrator 结果提取 actions。

### 2.2 前端 Agent 气泡 + 步骤展示

**改动文件：** `app/(dashboard)/agent/page.tsx`

- Agent 图标映射
- 消息气泡根据 `agent_actions` 展示 Agent 标签
- 多 Agent 时间线样式
- `awaiting_approval` 状态显示审批卡片

### 2.3 审批弹窗（m1 修正：用 resume endpoint）

```typescript
// approve handler
const handleApprove = async (sessionId: string) => {
    await api.post(`/orchestrator/resume/${sessionId}`, { decision: "approve" });
    // 重新发送原消息以刷新结果
    sendMessage(lastMessage);
};

// reject handler
const handleReject = async (sessionId: string, reason: string) => {
    await api.post(`/orchestrator/resume/${sessionId}`, { decision: "reject", reason });
    // 显示拒绝结果
};
```

---

## DAG

```
Phase 1 ── ✅ 表示可并行
  │
  1.3 HumanLoop ─────────── ✅ 可独立开发
  │
  1.4 Screening 降级 ────── ✅ 可独立开发
  │
  1.1 路由修复 + IO 协议     ← 必须先做（核心）
    └── 1.2 shared_context  ← 依赖 1.1
         └── 1.5 chat重构   ← 依赖 1.1 + 1.2
              │
Phase 2
  │
  2.1 API 增强 ──────────── 依赖 1.5（需要 Orchestrator 跑通）
  │
  2.2 前端气泡 ──────────── 依赖 2.1
  │
  2.3 审批弹窗 ──────────── 依赖 2.1 + 1.3
```

---

## 验证标准

### Phase 1
- [ ] 所有 Agent 的 `run()` 返回统一格式 `{agent, status, summary, result, details}`
- [ ] `execute_sub_task()` 路由到真实 Specialist Agent 而非 `router_*`
- [ ] `shared_context` 声名式存储和注入（不硬编码 Agent 类型）
- [ ] Orchestrator 编排 2+ 个 Agent 链式执行（screening → interview）数据传递正确
- [ ] HumanLoop 暂停后 approve/reject 分别正确恢复/终止
- [ ] 编排状态存 Redis，重启后可恢复
- [ ] ScreeningAgent 无 LLM 降级返回 needs_human_review=True
- [ ] 现有 962 个测试通过，新增 15+ 测试

### Phase 2
- [ ] API 含 `agent_actions` 字段
- [ ] 前端气泡显示 Agent 标签
- [ ] 审批弹窗 approve/reject 可用
- [ ] 6 个 Playwright 测试覆盖单 Agent / 多 Agent / 降级 / 审批四种场景
- [ ] 现有测试全部通过

---

## 错误处理

| 场景 | 行为 |
|------|------|
| Agent.run() 抛异常 | 标记 failed，继续执行后续子任务，最终 status=partial |
| shared_context 无所需 key | 下游 Agent 收到空值，自行处理 |
| HumanLoop 超时 | status=awaiting_approval，session 过期后返回"已过期" |
| LLM 不可用 | Screening 降级规则评分 + needs_human_review |
| 全链部分失败 | 返回 partial，前端展示成功/失败计数 |
| Redis 不可用 | HumanLoop 暂停功能降级（跳过审批直接继续） |
