# S.6 软弃用 — 旧 Orchestrator 文件 Sunset 计划

> 2026-06-01 S.6 决策记录
> 2026-06-01 Task 1 更新：发现架构差距，PR 1-3 需 Phase V

## ⚠️ 2026-06-01 Task 1 关键发现：架构差距

**新 `app/graphs/orchestrator_graph.py` (157 行) 不是 legacy `OrchestratorAgent` 的 1:1 替代。**

| 能力 | Legacy `OrchestratorAgent` | New `orchestrator_graph.py` |
|---|---|---|
| `is_multi_stage()` 检测 | ✅ 有 | ❌ 无（直接走 intent recognition） |
| Multi-stage DAG (`levels`, `paused_at_level`, `sub_tasks`) | ✅ 有 | ❌ 无（单 agent 路由） |
| `run()` 多阶段编排 | ✅ 有 | ❌ 无 |
| `route_single()` 单意图 | ✅ 有 | ✅ 有（通过 `_INTENT_TO_NODE` 14 个映射） |
| HumanLoop integration (`awaiting_approval`) | ✅ 有 | ❌ 无（LangGraph native `interrupt_before`） |
| Session 持久化 (`OrchestratorSession`) | ✅ Redis 持久化 | ✅ Checkpointer（MemorySaver / PostgresSaver） |
| `/resume` 端点恢复 | ✅ 恢复 DAG 状态 | ❌ 无对应 API |

**结论**：
- **PR 2 (agent_service step 1)** — 可部分迁移：单意图路径用新 graph，多阶段路径**仍需 legacy OrchestratorAgent**
- **PR 1 (human_loop /resume)** — 无法迁移：新 graph 无 multi-stage DAG，恢复 multi-stage session 需要 legacy OrchestratorAgent
- **PR 3 (test rewrites)** — 需重写约 60+ 个测试用例（test_orchestrator.py 20 + test_orchestrator_session.py 19 + test_multi_agent_pipeline.py 4 + 其它）
- **PR 4 (__init__.py 清理)** — 必须在 PR 1-3 之后（移除 re-export 会破坏 7+ 引用）

**预估工作量** = 3-5 天全职（需 Phase V 专门处理）

## 决策：软弃用 (Soft Deprecation) 而非硬删

**为什么 S.6 计划说"删 `orchestrator_agent.py` + `orchestrator_session.py`"但我们不删：**

调研发现这 2 个文件被 **7+ 个生产文件 / 测试文件** 引用，**直接删除会破坏 S.5 刚建好的 legacy shim 和现有 human-loop resume 流程**：

| 引用方 | 类型 | 用途 |
|---|---|---|
| `app/api/orchestrator.py:9` | prod | S.5 的 `/legacy/analyze` shim |
| `app/api/human_loop.py:146,152,154` | prod | `/resume` 端点（审批后恢复） |
| `app/services/agent_service.py:549,551` | prod | Step 1 多阶段任务检测 |
| `app/agents/__init__.py:6` | prod | Re-export |
| `tests/test_orchestrator.py` (20 refs) | test | 老 Agent 行为 |
| `tests/test_orchestrator_session.py` (19 refs) | test | Session 持久化 |
| `tests/test_agent_service.py` (3 refs) | test | agent_service flow |
| `tests/test_human_loop_api.py` (7 refs) | test | human_loop 端点 |
| `tests/test_multi_agent_pipeline.py` (4 refs) | test | pipeline 编排 |

**正确路径** = 让这 2 个文件在 **1 周观察期**内自然被替代：

## Sunset 时间表

| 日期 | 动作 |
|---|---|
| **2026-06-01**（今天）| 加 ⚠️ DEPRECATED 标记（已完成）|
| **2026-06-01 ~ 06-08** | 观察期 — `/legacy/analyze` 流量 / 错误率 / 测试通过情况 |
| **2026-06-08** | 硬删 `orchestrator_agent.py` + `orchestrator_session.py` |
| **同时** | 必须先完成：<br>① `human_loop.py` 的 `/resume` 改用 LangGraph checkpointer 恢复<br>② `agent_service.py` step 1 改用 `create_orchestrator_graph().ainvoke()`<br>③ `tests/test_orchestrator*.py` 改测 graph wrapper<br>④ `__init__.py` 移除 4 个 re-export |

**2026-06-01 重新评估**：①②③ 需 Phase V（3-5 天），仅靠 Task 1 无法在 2026-06-08 前完成。**建议延长 sunset 至 2026-06-15**，并启动 Phase V 专门处理。

## 已落地标记 (2026-06-01)

- ✅ `app/agents/orchestrator_agent.py:1-7` — docstring 顶部加 ⚠️ DEPRECATED + 引用本文件
- ✅ `app/agents/orchestrator_session.py:1-7` — 同上
- ✅ `app/agents/__init__.py:7-13` — re-export 上方加 deprecation 注释
- ✅ `app/api/orchestrator.py:46-58` — `/legacy/analyze` 路由返回 `Deprecation` + `Sunset` + `X-Deprecated-By` HTTP 头

## 下次行动（2026-06-08 之前必须完成）

### 1. `app/api/human_loop.py` 的 `/resume` 改用 LangGraph checkpointer

```python
# 当前 (deprecated)
from app.agents.orchestrator_session import OrchestratorSession
from app.agents.orchestrator_agent import OrchestratorAgent
session = await OrchestratorSession.find_by_approval_id(req.approval_id)
orch = OrchestratorAgent()
orch.shared_context = dict(session.shared_context)
# ... 继续 DAG 执行 ...

# 目标 (new)
from app.graphs.orchestrator_graph import create_orchestrator_graph
graph = create_orchestrator_graph(checkpointer=PostgresSaver(...))
config = {"configurable": {"thread_id": req.approval_id}}
state = graph.get_state(config)
graph.update_state(config, {"approval_status": "approved"})
result = await graph.ainvoke(None, config)
```

### 2. `app/services/agent_service.py` step 1 改用 graph

```python
# 当前 (deprecated)
from app.agents.orchestrator_agent import OrchestratorAgent
orchestrator = OrchestratorAgent()
result = await orchestrator.run({"task": text, "context": ctx})

# 目标 (new)
from app.graphs.orchestrator_graph import create_orchestrator_graph
graph = create_orchestrator_graph(checkpointer=MemorySaver())
result = await graph.ainvoke(
    {"task_id": uuid4().hex, "user_id": ..., "job_id": ..., "input_text": text, ...},
    config={"configurable": {"thread_id": task_id}},
)
```

### 3. 测试迁移

- `test_orchestrator.py` → `test_orchestrator_graph.py`（测 graph.ainvoke 行为）
- `test_orchestrator_session.py` → 删除（功能由 LangGraph checkpointer 接管）
- `test_human_loop_api.py` 改测 checkpointer-based resume
- `test_agent_service.py` 改测 graph wrapper
- `test_multi_agent_pipeline.py` 改测 graph 编排

### 4. `__init__.py` 清理

```python
# 移除 4 行 re-export
from app.agents.orchestrator_agent import OrchestratorAgent, get_orchestrator, PipelineOrchestrator, SequentialOrchestrator

# 从 __all__ 移除
"OrchestratorAgent",
"get_orchestrator",
"PipelineOrchestrator",
"SequentialOrchestrator",
```

## 监控指标（观察期 2026-06-01 ~ 06-08）

每天检查：

1. `/orchestrator/legacy/analyze` 调用次数（应逐步下降至 0）
2. `/orchestrator/legacy/analyze` 错误率（应保持低位，证明 shim 工作正常）
3. `OrchestratorSession` Redis key 数量（应逐步下降至 0）
4. 新 `/orchestrator/analyze` 调用次数（应稳定上升）

## 退出标准

- [ ] 7 天观察期无 legacy 流量或全部流量已迁移
- [ ] 4 个迁移 PR 全部合并（human_loop, agent_service, tests, __init__）
- [ ] `grep -r "OrchestratorAgent\|OrchestratorSession" apps/api/app/` 返回 0 结果
- [ ] pytest 全量通过
- [ ] 删除 PR 合入

## 风险

- 如果 7 天内 legacy 流量仍 >10%，延长观察期
- 如果 human_loop `/resume` 端点有未恢复的 session（Redis 中残留），需要数据迁移到 PostgresSaver
