# AI 招聘系统 — 下一阶段权威路线图 (2026-06-01)

> **本文件取代**：`langgraph-migration-plan.md` / `resume-parser-mcp-plan.md` / `operations-monitoring-plan.md`
> **归档位置**：`.omo/plans/_archive/`（保留原文供溯源）
> **本文件是** Phase S / T / U 的**唯一**实施入口

---

## 总体节奏

```
R (清理整合) → S (LangGraph) → T (MCP + ResumeParser) → U (运维可观测)
4-6h            10-15h          8-12h                  10-15h
                                总计 32-48h ≈ 4-6 周
```

> ⚠️ S 必须在 T/U 之前完成 — LangGraph 主图是 T/U 的编排基础。
> T 与 U **可并行**（不同模块，无共享代码）。

---

## Phase S：完成 LangGraph 编排迁移

> 起点：`app/graphs/` 脚手架已建（__init__/orchestrator_graph/resume_parser_graph）
> 目标：替换 `app/agents/orchestrator_agent.py` + `orchestrator_session.py`

| # | 任务 | 文件 | 估时 |
|---|---|---|---:|
| S.1 | 安装 langgraph + langgraph-checkpoint-postgres，验证 PostgresSaver 兼容 asyncpg | `pyproject.toml` | 30 min |
| S.2 | 完成 `resume_parser_graph.py` 7 个 step 节点 + conditional edge | `app/graphs/resume_parser_graph.py` | 2h |
| S.3 | 完成 `orchestrator_graph.py` 主图（调用 Agent.run()，不做 Subgraph 包装）| `app/graphs/orchestrator_graph.py` | 3h |
| S.4 | 写 `app/api/tasks.py`（任务管理 API：list / get / snapshots / timeline）| `app/api/tasks.py` | 1h |
| S.5 | 流量切换：POST `/api/v1/orchestrator/analyze` → 新 Graph；旧路由改名 `/legacy` 留 1 周 | `app/api/orchestrator.py` + `router.py` | 1h |
| S.6 | 删 `app/agents/orchestrator_agent.py` + `orchestrator_session.py` | 同 | 30 min |
| S.7 | `tests/test_graphs/` 两个 graph 的单元测试 | `apps/api/tests/test_graphs/` | 2h |
| S.8 | E2E 回归（Playwright）+ pytest 全量 |  | 1h |

**S 退出标准**：
- [ ] `orchestrator_graph.invoke("解析这份简历")` 走通
- [ ] 旧 API `/legacy` 仍可调用，新 API 走 Graph
- [ ] 全量测试 100% 通过
- [ ] 旧 orchestrator 文件已删

---

## Phase T：MCP Tool System + ResumeParsingAgent

> **状态**：T.1-T.8 ✅ 全部完成（2026-06-02 代码审查通过）
> **审查修复**：T.3 `router_route.py` 添加 `resume_parser` intent + 关键词；T.6 `test_interview_tools_defined` 更新为 3 个工具

> 起点：`app/tools/` 框架已建（5 个工具文件 + `__init__.py` 包含 discover_tools）
> 目标：把 `_BUILTIN_TOOLS` 从 `agent_service.py` 真正迁出，注册 resume_parser 路由

| # | 任务 | 文件 | 估时 | 状态 |
|---|---|---|---:|---|
| T.1 | 精简 Prompt-H 到 80 行 | `app/agents/prompts/resumeParser.md` | 30 min | ✅ 38行 |
| T.2 | 实现 `ResumeParsingAgent` 7-step 工作流 | `app/agents/resume_parser.py` | 3h | ✅ 151行 |
| T.3 | RouterAgent 注册 `resume_parser` 意图 | `app/api/router_route.py` | 1h | ✅ 已修复 |
| T.4 | 迁移 `_BUILTIN_TOOLS` screening 部分到 `app/tools/screening.py` | `app/tools/screening.py` | 1h | ✅ 5个工具 |
| T.5 | 迁移 `_BUILTIN_TOOLS` interview 部分到 `app/tools/interview.py` | `app/tools/interview.py` | 1h | ✅ 3个工具 |
| T.6 | `tests/test_tools/` 工具 handler 单测 | `tests/test_tools/` | 2h | ✅ 25 passed |
| T.7 | `tests/test_resume_parser_agent.py` Agent 7-step 流程测 | `tests/test_resume_parser_agent.py` | 1h | ✅ 8 tests |
| T.8 | E2E：上传简历 → 解析 → 评估 跑通 | `apps/web/e2e/screening-flow.spec.ts` | 1h | ✅ 覆盖 |

**T 退出标准**：
- [x] `POST /api/v1/router/classify` 文本包含"解析"→ 路由到 `resume_parser`（验证：confidence 0.2）
- [x] `app/services/agent_service.py` 不再维护 `_BUILTIN_TOOLS`（仅引用 `all_builtin_tools()`）
- [x] `app/tools/all_tools()` 返回全部工具定义（discover_tools 动态加载）

---

## Phase U：运维可观测 + 生产就绪

> 起点：`app/models/operation_log.py` + `approval.py` + `operation_stats.py` 已建
> 目标：HumanLoop 审批 DB 持久化、错误分类、物化聚合、Audit UI

| # | 任务 | 文件 | 估时 |
|---|---|---|---:|
| U.1 | OperationLog 加 `error_category` / `immutable` / `superseded_by` | `app/models/operation_log.py` | 1h |
| U.2 | ApprovalService 接管 HumanLoop 持久化 | `app/services/approval_service.py`（新建）| 2h |
| U.3 | 重构 `app/agents/human_loop.py` 用 ApprovalService | 同 | 1h |
| U.4 | `operation_stats_hourly` 物化表 + 5min UPSERT 任务 | `app/services/aggregation_service.py`（已有，补完）| 2h |
| U.5 | `GET /api/v1/audit/logs` 端点 + 过滤 | `app/api/audit.py`（已有路由，补端点）| 1h |
| U.6 | ApprovalService.auto_expire() 定时 + publish SSE | `app/services/approval_service.py` | 1h |
| U.7 | AuditPanel 前端组件 | `apps/web/components/features/audit/audit-panel.tsx` | 1h |
| U.8 | AI 健康监测面板（成功率 / P95 / Agent 列表）| `apps/web/components/features/monitoring/ai-health.tsx` | 2h |
| U.9 | Dashboard 集成 + 审批倒计时 UI | `apps/web/app/(dashboard)/dashboard/page.tsx` | 1h |
| U.10 | E2E 回归 + 覆盖率守门 ≥ 90% |  | 1h |

**U 退出标准**：
- [ ] 进程重启后 pending 审批不丢失
- [ ] Dashboard `/operations/summary` 响应 < 200ms
- [ ] 前端可见 24h 成功率环图 + Agent P95 趋势
- [ ] 超时审批自动 expired

---

## 不在本路线图（明确范围）

> 避免 scope creep。明确**不做**：

- ❌ 前端技术栈替换（tRPC、shadcn 重构）
- ❌ 多租户（Schema-per-tenant 等方案选型）
- ❌ 中文文档英文化
- ❌ 重写 OMLXClient（已有 try/except）
- ❌ LangGraph interrupt 替代 HumanLoop（已决策走 ApprovalService）
- ❌ 新 Agent 模式（已 7/7 全部实现）

---

## 风险登记

| 风险 | 缓解 |
|---|---|
| LangGraph 与 asyncpg/SQLAlchemy 不兼容 | S.4 验证；不兼容降级 MemorySaver + DB 持久化 |
| `app/tools/` 已有 5 文件但功能未测试 | T.6/T.7 先写测试再写实现 |
| HumanLoop 改造回归风险高 | U.3 保留旧 HumanLoop 接口作为 shim，逐步替换 |
| 78 文件未提交导致 Phase R 之前的修改丢失 | R.3 优先 commit 全部 |

---

## 参考材料

- **PRD**：`AI_Recruitment_System_PRD.md`
- **架构**：`AI_Recruitment_Multi_Agent_System_Prompt_Architecture.md`
- **MCP 设计**：`AI_招聘系统_MCP_工具系统设计文档_v2.md`
- **记忆设计**：`AI招聘Agent_上下文记忆架构设计.md`
- **历史 plan**（归档保留）：`.omo/plans/_archive/`
  - `langgraph-migration-plan.md`（已被本文件吸收）
  - `resume-parser-mcp-plan.md`（已被本文件吸收）
  - `operations-monitoring-plan.md`（已被本文件吸收）
  - `multi-agent-orchestration-v1/v2/v3.md`（已被 LangGraph 取代）
