# LangGraph 编排层迁移规划（Momus 修正版）

> 基于 Momus 审核修正（2026-05-31）
> 核心修正：
>   1. 不做 Subgraph 薄包装 → 主图 node 直接调 Agent.run()
>   2. 不分阶段共存 → P1 完成即切换，一次性废弃旧编排
>   3. interrupt 保留现有 HumanLoop → 不走 LangGraph 原生 interrupt
>   4. 快照复用 OperationLog → 不加新表
>   5. 先验证 PostgresSaver 兼容性

---

## 执行顺序

```
Week 1（验证 + 单 Agent 图）      Week 2（主图 + 迁移）
──┼───────────────────────────────┼─────────────────────────
Step 1 langgraph 安装 + 验证       Step 4 OrchestratorGraph
Step 2 resume_parser 单 Agent 图   Step 5 流量切换，废弃旧编排
Step 3 验证 checkpoint + interrupt Step 6 快照 API + 前端
```

---

## 详细步骤

### Step 1: 环境准备

```
1. pip install langgraph langgraph-checkpoint-postgres
2. 验证: from langgraph.graph import StateGraph 可导入
3. 验证: PostgresSaver 与当前 asyncpg/SQLAlchemy 兼容
4. 如果不兼容 → 回退方案: MemorySaver + SnapshotManager DB 持久化
```

---

### Step 2: resume_parser 单 Agent StateGraph

**不做子图薄包装**，而是把 resume_parser 的 7-step 展开为 graph 节点：

```
StateGraph(ResumeParserState)
  nodes:
    step_validate_input   — 校验 content/file_url
    step_parse_resume     — 调用 tools/resume_parser.py handler
    step_check_confidence — 置信度分级
    step_quality_assess   — 质量评估摘要
    step_risk_detect      — 风险标注
    step_dedup_check      — 去重检查
    step_format_output    — 返回标准化结果
    step_create_snapshot  — 写 OperationLog
  
  conditional edges:
    step_check_confidence → < 0.6 → node "需人工复核"(interrupt)
                         → ≥ 0.6 → continue
```

**文件**: `app/graphs/resume_parser_graph.py`（新建）

---

### Step 3: 验证 checkpoint + interrupt

```
1. graph.invoke() → 正常走通 7-step
2. 模拟置信度 < 0.6 → interrupt 触发 → 等待输入
3. 恢复执行 → 从断点继续
4. 验证 checkpoint 写入了 DB
```

---

### Step 4: OrchestratorGraph 主图

**不做 Subgraph**，每个 node 直接调用现有 Agent.run()：

```python
builder = StateGraph(TaskState)

nodes:
  intent_recognition → RouterAgent.classify()
  select_agent       → 路由到哪个 Agent
  execute_screening  → ScreeningAgent.run()    # 直接调，不包装
  execute_interview  → InterviewAgent.run()
  execute_sourcing   → SourcingAgent.run()
  execute_offering   → OfferingAgent.run()
  execute_onboarding → OnboardingAgent.run()
  execute_resume_parser → ResumeParserAgent.run()
  create_snapshot    → OperationService.create()  # 复用现有
  aggregate_results  → 合并 shared_context

conditional edges:
  select_agent → screening / interview / ... / complete → END
  execute_* → create_snapshot → aggregate_results → intent_recognition
```

**关键**: `interrupt_before` 触发后不直接等输入 → 走现有 HumanLoop（ApprovalService）。

---

### Step 5: 流量切换

```
一天内完成:
1. api/tasks.py 新建 → POST /tasks 走 Graph，POST /tasks/legacy 走旧编排
2. 验证新路径功能完整
3. 改默认路由 /tasks → 新路径
4. 删除 app/agents/orchestrator_agent.py
5. 删除 app/agents/orchestrator_session.py
```

---

### Step 6: 快照 API + 前端

**不加新表**，快照直接复用 `OperationLog`：

```
GET /tasks/{task_id}/snapshots → 从 OperationLog 按 task_id 查询
  不需要 SnapshotManager，OperationService.list() 已支持按 agent_name+action 过滤

GET /tasks/{task_id}/timeline  → 合并 OperationLog + approval_history
```

前端复用 `OperationFeed` 组件，加 filter 按 task_id。

---

## 不变的部分

| 模块 | 策略 |
|------|------|
| `app/agents/*.py` | 不修改，Graph node 直接调用 run() |
| `app/tools/` + `app/skills/` | 不修改 |
| `app/mcp/` | 不修改 |
| `app/api/human_loop.py` | 保留，interrupt 后走现有审批流 |
| `app/services/approval_service.py` | 保留 |
| `app/models/operation_log.py` | 复用为快照存储 |

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `pyproject.toml` | +langgraph, langgraph-checkpoint-postgres |
| `app/graphs/__init__.py` | 新建 |
| `app/graphs/resume_parser_graph.py` | 新建（7-step StateGraph） |
| `app/graphs/orchestrator_graph.py` | 新建（主编排 StateGraph） |
| `app/api/tasks.py` | 新建（任务管理 API） |
| `app/api/router.py` | 修改（注册 tasks 路由） |
| `app/agents/orchestrator_agent.py` | Step 5 废弃 |
| `app/agents/orchestrator_session.py` | Step 5 废弃 |
| `tests/test_graphs/test_resume_parser_graph.py` | 新建 |
| `tests/test_graphs/test_orchestrator_graph.py` | 新建 |

---

## 退出标准

- [ ] `from langgraph.graph import StateGraph` 可导入
- [ ] `resume_parser_graph.invoke()` 走通 7-step，低置信度触发 interrupt
- [ ] `orchestrator_graph.invoke("解析这份简历")` → 路由到 resume_parser 并返回
- [ ] interrupt 触发后 → 创建 Approval → 走 HumanLoop → 恢复执行
- [ ] 流量切换后旧编排废弃，所有 API 走新 Graph
- [ ] `GET /tasks/{id}/snapshots` 返回 OperationLog 快照
- [ ] 全部现有测试通过
