# Phase V — S.6 Sunset Migrations (3-5 days dedicated)

> 2026-06-01 启动计划
> 阻塞来源：Task 1 (S.6 sunset 4 PRs) 因新 `orchestrator_graph.py` 缺乏 multi-stage DAG 支持而需 multi-day 重写
> 建议启动日期：2026-06-02
> 目标完成日期：2026-06-08（软期限）/ 2026-06-15（硬期限）

> **状态更新 2026-06-01（PR-V.3）**：PR-V.3 ✅ **已完成 + 已提交**（commit `6f4898c`）。
> `agent_service.py:578-621` Step 1 块已迁移：原 `OrchestratorAgent().run()/route_single()` 改为 `create_orchestrator_graph(checkpointer=None, with_interrupt=False).ainvoke(make_initial_orchestrator_state(...))` + `_adapt_graph_result_to_legacy(state)`。
> 设计要点：`checkpointer=None` (per-request in-memory, no Redis 持久化；PR-V.2 的 /resume 用独立的 Redis-backed graph via `app/api/orchestrator._get_graph()`)；`with_interrupt=False` (one-shot 路径，无 pause/resume；awaiting_approval 仍可通过 state mutation `paused_at_level` + `status` 实现)。
> 测试更新：`TestChatWithToolsOrchestratorFlow` 4 个测试重写（mock `app.graphs.orchestrator_graph.create_orchestrator_graph` + adapter 模拟图路径），1 个新测试验证 `with_interrupt=False` + `input_text` 透传；`test_orchestrator.py` 删除 2 个废弃 xfail 测试（覆盖已迁移到 `test_orchestrator_graph_multistage.py`）。
> 全量回归 180/180 绿（test_graph_adapter 7 + TestChatWithToolsOrchestratorFlow 5 + test_orchestrator 64 + test_graphs/ 64 + test_human_loop_api 29 + test_human_loop_resume_migration 11）。
> 提前 4 天完成（计划日期 2026-06-05）。仅剩 PR-V.4（删除 legacy 文件 + 清理 __init__.py re-exports）。

> **状态更新 2026-06-01（PR-V.2）**：PR-V.2 ✅ **已完成 + 已提交**（commit `c2119e3`）。
> `/resume` 端点已迁移：使用 `graph.update_state` + `graph.ainvoke(None, config)` 恢复 multi-stage 会话，保留 legacy `OrchestratorSession` fallback（PR-V.4 删除）。
> 新增 Redis 索引 `appr:graph_thread:{approval_id} → thread_id` (24h TTL) 用于 approval_id → thread_id 查找；`migrate_legacy_orchestrator_sessions()` 启动时 SCAN `orch:session:*`，只读不删。
> 17 新测试（6 graph path + 11 migration）；111/111 回归绿。提前 3 天完成（计划日期 2026-06-04）。

> **状态更新 2026-06-01（PR-V.1）**：PR-V.1 ✅ **已完成 + 已提交**（commit `7bf5d57`）。
> `orchestrator_graph.py` 现已支持 multi-stage DAG（7 新 state 字段、3 新节点、条件边、checkpointer awaiting_approval 暂停）。
> 52/52 新测试通过；`test_graphs/` + `test_graph_adapter.py` 全量回归 71/71 绿。
> 阻塞解除。可立即开始 PR-V.2（human_loop /resume 迁移）。

## 背景

S.6 计划硬删 `orchestrator_agent.py` + `orchestrator_session.py`（共 2 文件，~778 行），
需先完成 4 个迁移 PR。详见 `.omo/plans/S6-findings.md`。

**关键架构差距**（2026-06-01 发现）：

| 能力 | Legacy `OrchestratorAgent` | New `orchestrator_graph.py` |
|---|---|---|
| `is_multi_stage()` | ✅ | ❌ |
| Multi-stage DAG (`levels`/`paused_at_level`/`sub_tasks`) | ✅ | ❌ |
| `run()` multi-stage | ✅ | ❌ |
| `route_single()` single intent | ✅ | ✅ (via `_INTENT_TO_NODE` 14 映射) |
| HumanLoop `awaiting_approval` | ✅ | ❌（用 LangGraph `interrupt_before`） |
| Session 持久化 | ✅ Redis | ✅ Checkpointer (MemorySaver/PostgresSaver) |
| `/resume` 端点恢复 multi-stage session | ✅ | ❌（无对应 API） |

## Phase V 范围（4 PRs，依赖关系如下）

### PR-V.1: Extend `orchestrator_graph.py` 支持 multi-stage DAG（最复杂，2 天）

**目标**：让新 graph 支持 `levels`/`sub_tasks`/`paused_at_level` 概念

**实现路径**：
```python
# app/graphs/orchestrator_graph.py 新增：
class OrchestratorState(TypedDict):
    # 现有字段
    task_id: str
    user_id: str
    intent: str
    input_text: str
    agent_result: dict | None
    # 新增 multi-stage 字段
    multi_stage: bool
    sub_tasks: list[dict]  # 从 RouterAgent.multi_stage_decompose() 获取
    current_level: int     # 当前执行到的 level
    levels: list[list[int]] # DAG 拓扑排序
    paused_at_level: int | None
    results: list[dict]    # 每个子任务结果
```

**关键节点**：
- 新增 `multi_stage_decompose` 节点（调用 `RouterAgent.decompose()`）
- 新增 `execute_level` 节点（并行执行当前 level 的所有子任务）
- 新增 `should_continue_or_pause` 条件边（检查是否有 `awaiting_approval`）

**测试要求**：
- `tests/test_orchestrator_graph.py`（新文件）
  - 单 intent 流程（已有，需扩展）
  - Multi-stage 流程（2-level DAG）
  - Multi-stage 暂停/恢复（与 checkpointer 集成）
  - `awaiting_approval` 触发暂停

### PR-V.2: Migrate `human_loop /resume` to graph（1 天）

**目标**：替换 `app/api/human_loop.py:127-208` 的 80 行 legacy 代码

**实现**：
```python
# human_loop.py /resume 改写
from app.graphs.orchestrator_graph import create_orchestrator_graph
from app.api.orchestrator import _build_checkpointer  # 复用 Task 4

graph = create_orchestrator_graph(checkpointer=_build_checkpointer())
config = {"configurable": {"thread_id": req.approval_id}}
state = graph.get_state(config)
if not state:
    return error("session not found", status_code=404)

# 标记当前 approval 为 approved
graph.update_state(config, {"approval_status": "approved"})
# 恢复执行
result = await graph.ainvoke(None, config)
return success(result.values)
```

**数据迁移**（重要！）：
- 检查 Redis 中残留的 `OrchestratorSession` 数据
- 编写 migration script：把 Redis session 转换为 LangGraph checkpointer 状态
- 在 `__init__.py` lifespan 启动时执行一次性迁移

**测试**：
- 更新 `tests/test_human_loop_api.py::TestResumeAfterApproval::*`（如存在）
- 新增 `tests/test_human_loop_resume_migration.py`（数据迁移测试）

### PR-V.3: Migrate `agent_service step 1` to graph（0.5 天）

**目标**：替换 `app/services/agent_service.py:547-567` 的 legacy 调用

**实现**：
```python
# agent_service.py chat_with_tools() 改写 Step 1
from app.graphs.orchestrator_graph import create_orchestrator_graph
from app.api.orchestrator import _build_checkpointer

graph = create_orchestrator_graph(checkpointer=_build_checkpointer())
config = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}

# 异步流式 invoke（如果 graph 支持 stream）
result = await graph.ainvoke({
    "task_id": uuid4().hex,
    "user_id": user_id,
    "job_id": "",  # Step 1 不知道 job_id
    "input_text": last_user_msg,
}, config=config)

# 状态映射：graph output → _build_approval_response() 期望的格式
if result.get("status") == "interrupted":  # LangGraph interrupt
    approval_resp = _build_approval_response_from_interrupt(result)
```

**测试**：
- 更新 `tests/test_agent_service.py` 中 `TestChatWithToolsOrchestratorFlow` 相关测试
- 需要把 2 个 xfail (test_execute_sub_task_interview_awaits_approval + test_run_with_awaiting_approval) 解 xfail

### PR-V.4: Test rewrites + `__init__.py` cleanup（1 天）

**目标**：60+ 测试用例迁移 + 4 个 re-export 移除

**步骤**：
1. `tests/test_orchestrator.py` → `tests/test_orchestrator_graph.py`（测 graph.ainvoke 行为，~20 tests）
2. 删除 `tests/test_orchestrator_session.py`（功能由 checkpointer 接管，~19 tests）
3. 更新 `tests/test_human_loop_api.py` /resume 测试（~7 tests）
4. 更新 `tests/test_agent_service.py` 中 orchestrator flow 测试（~3 tests）
5. 更新 `tests/test_multi_agent_pipeline.py`（~4 tests）
6. 移除 `app/agents/__init__.py` 4 个 re-export（OrchestratorAgent/get_orchestrator/PipelineOrchestrator/SequentialOrchestrator）
7. 移除 2 个文件的 `⚠️ DEPRECATED` 标记
8. 删除 `app/agents/orchestrator_agent.py` + `app/agents/orchestrator_session.py`
9. 验证：`grep -r "OrchestratorAgent\|OrchestratorSession" apps/api/app/` 返回 0 结果

## 每日里程碑

| 日期 | 完成项 | 验证 |
|---|---|---|
| **Day 1 (2026-06-02)** | ✅ PR-V.1 启动：扩展 `OrchestratorState` + `multi_stage_decompose` 节点（提前 1 天完成于 2026-06-01） | ✅ 新 graph 类型检查通过 + 单元测试覆盖 |
| **Day 2 (2026-06-03)** | ✅ PR-V.1 完成：`execute_level` + `should_continue_or_pause` + 测试（提前 2 天完成于 2026-06-01） | ✅ `test_orchestrator_graph_multistage.py` 52 tests 全过 + 回归 71/71 绿 |
| **Day 3 (2026-06-04)** | ✅ PR-V.2：human_loop /resume 迁移 + 一次性迁移脚本（提前 3 天完成于 2026-06-01） | ✅ 6 new graph path tests + 11 migration tests；端到端 111/111 绿 |
| **Day 4 (2026-06-05)** | ✅ PR-V.3：agent_service step 1 迁移 + 删 2 xfail（提前 4 天完成于 2026-06-01） | ✅ TestChatWithToolsOrchestratorFlow 5/5 + 回归 180/180 绿 |
| **Day 5 (2026-06-06)** | PR-V.4：test rewrites + __init__.py 清理 + 文件删除 | grep 0 结果 + pytest 1380+ 全过 |

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 多阶段 DAG 语义复杂，graph 实现易错 | 高 | 参考 LangGraph 官方 `Map-Reduce` + `Send` API 文档；先用 legacy 实现做行为基线测试 |
| Redis session 数据迁移丢失 | 高 | 迁移前全量备份 Redis；保留 legacy 文件 1 周观察期 |
| 60+ test rewrites 工作量大 | 中 | 优先迁移 P0（orchestrator + human_loop resume），P1/P2 标记 deprecated |
| LangGraph `interrupt_before` 与现有 HumanLoop 冲突 | 中 | PR-V.1 期间先在 graph 内部用 HumanLoop，不切到 native interrupt |

## 退出标准

- [ ] PR-V.1 → PR-V.4 全部合并到 main
- [ ] 4 个文件删除（orchestrator_agent.py + orchestrator_session.py + 2 个 test 文件）
- [ ] `__init__.py` 移除 4 个 re-export
- [ ] pytest 全量 ≥ 1380 pass / 0 fail
- [ ] `grep -r "OrchestratorAgent\|OrchestratorSession" apps/api/app/` 返回 0
- [ ] /legacy/analyze 流量 = 0（监控 1 周）
- [ ] Redis 中无残留 `OrchestratorSession` key

## 不在 Phase V 范围

- E2E Playwright 真实运行（仍需 dev server，Task 3 已写 specs）
- Coverage gate 自动化（U.10 spec 已写，需 CI 集成）
- Task 5 untracked spec doc（已决策：保留 untracked）
- PostgresSaver 生产部署（Task 4 已完成 env 切换，需 ops 配合）
