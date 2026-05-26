# AI 招聘系统 — v4 实施计划

> 基于 PRD v2.2 + 2026-05-25 全量代码扫描 + Momus 审查修正
> 作者：Sisyphus
> 执行规则：每个任务完成后 `lsp_diagnostics` + `pytest`(现存 46 不能红) + `pnpm build`

---

## 当前状态（来自代码分析）

| 维度 | 数据 | 来源 |
|:---|:---|:---|
| 后端 API 端点 | 20+ route 模块，4 stub（report/interview/pipeline/generate-report/parallel/data-aggregate/human-loop/stop） | `apps/api/app/api/` 扫描 |
| Agent 模式 | 7/7 全部实现，含门控+共识+DAG+审批流 | `apps/api/app/agents/` |
| Services | 6/8 真实逻辑，report.py + interview.py 为 stub | `apps/api/app/services/` |
| LLM Client | OMLXClient `chat()` 和 `embed()` 已有 try/except（chat 返回 `[LLM unavailable]`，embed 返回 `[]`）| `apps/api/app/llm/omlx_client.py` |
| RouterAgent | stub（`return {"intent": "unknown"}`），全局意图路由未运作 | `apps/api/app/agents/router_agent.py` |
| Application API | model 存在，零 route | `apps/api/app/models/application.py` 有定义，`apps/api/app/api/` 无对应 |
| 前端页面 | 12/12 页面有真实 API 调用，无纯 mock 页 | `apps/web/app/(dashboard)/` |
| 测试 | 46 tests / 6 files，覆盖率 50% | `apps/api/tests/` |
| CI | Docker Compose + CI workflow 存在 | `.github/workflows/ci.yml` |
| 鉴权 | JWT register/login/me，基础可用 | `apps/api/app/api/auth.py` |

---

## 执行策略

- **严格依赖顺序**：Phase N 开始前，Phase N-1 必须全部完成且验证通过
- **Phase 内分组**：有依赖的项必须串行，无依赖的项可并行（标注 "parallel-ready"）
- **退出标准**：每个 Phase 的可验证指标必须全部满足方可进入下一 Phase
- **每次只做一个 Phase**，完成后全量 pytest + pnpm build + E2E 验证
- **Momus Gate**：Phase 2a 启动前必须完成 memory-design.md 设计文档并通过 Momus 审查

```
依赖图：
Phase 0 (Stub修复) ──→ Phase 1 (数据流闭环)
                              │
               ┌──────────────┼──────────────┐
               ↓              ↓              ↓
          Phase 2a       Phase 2b         Phase 3/4
         (跨会话记忆)    (技能演化)       (可并行启动)
               │              │
               └──────┬───────┘
                      ↓
                 Phase 3 (智能化)
                 Phase 4 (商用化)

注：Phase 2a 和 2b 可并行启动
    - 2a 需要跨会话数据（多个 session 的聚合模式）
    - 2b 只需要单次 session 的成功记录（session_summaries 表即可）
    → 2b 不阻塞等 2a，二者可同时开工
```

---

## Phase 0：修复已知破损（1 周，无外部依赖）

> 目标：先把所有 stub、缺失端点、已知 bug 修掉，让系统在任何输入下都能给出合理响应而非"将在后续迭代实现"。
> 范围：不做任何新功能开发，不改 UI，不改数据库 schema（Settings 除外），不引入新依赖。

**内部依赖**：`Group A`（8 项完全并行）→ `Group B`（1 项，等 Group A 的 0.1 完成后才能开工）

---

### Group A（8 项并行，顺序不限）

#### 0.1 ReportService — 真实评估报告生成

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/services/report.py` (71 行 → ~150 行) |
| **当前** | `{"scores": {}, "summary": "Report pending..."}` 全 stub |
| **目标** | 读 Candidate + Application DB → LLM 生成 5-8 维度评分 + 综合评语 |
| **降级** | LLM 不可用时返回 keyword 频次分析的降级评分，`llm_generated: false` |
| **输出** | `{"candidate_name", "job_title", "score_dimensions": [{"name","score","reason"}], "overall_score", "summary", "llm_generated": bool}` |
| **测试** | `tests/test_report.py` 新建 4 tests（正常路径 + LLM 降级 + candidate 不存在 + evaluation 已缓存）|
| **边界** | Candidate 不存在 → 404; Evaluation 已存在 → 返回缓存不重复生成 |

#### 0.3 InterviewService — 真实面试安排写库

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/services/interview.py` |
| **当前** | `{"status": "pending_approval"}` 占位 |
| **目标** | 写入 Interview DB 表（model 已有），slot 冲突检测，confirm 更新 DB 状态 |
| **改动** | 60 行 |
| **冲突规则** | 同一 candidate 同一 date 不可有 2 条 `confirmed` 的 interview |
| **测试** | `tests/test_interview_service.py` 新建 3 tests（正常写入 + 冲突拒绝 + confirm 状态变更）|

#### 0.4 `/parallel/data-aggregate` — 聚合 evaluation 分数

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/api/parallel.py` |
| **当前** | `return {"message": "数据聚合将在后续迭代实现"}` |
| **目标** | 接收 `candidate_ids: UUID[]` → 聚合多份 evaluation → 平均分/最高分/维度分布 |
| **改动** | 25 行 |
| **输出** | `{"avg_score", "max_score", "dimension_distribution": [{"name", "avg", "min", "max"}], "sample_size"}` |
| **边界** | 空数组 → 空聚合; 部分 ID 不存在 → 跳过不报错 |

#### 0.5 `/human-loop/stop` — 清理 pending 提案

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/api/human_loop.py` |
| **当前** | `return {"message": "Stop功能将在后续迭代实现"}` |
| **目标** | 调用 `HumanLoopAgent._pending_purge_all()` 清理所有待审批项 |
| **改动** | 15 行 |
| **安全** | 需要 authenticated user; 返回已清理的 approval_id 列表 |

#### 0.6 Application CRUD 端点（model 存在但无 route）

| 属性 | 值 |
|:---|:---|
| **前置** | 第一步：读 `apps/api/app/models/application.py` 验证字段定义是否与前端需求匹配 |
| **文件** | 新建 `apps/api/app/api/applications.py` (80 行) + `apps/api/app/services/application.py` (40 行) |
| **当前** | Application model 存在，无 API route |
| **目标** | list(按 user/job 过滤) / get / create / update(状态变更) / delete + router.py 注册 |
| **同步** | `router.py` 添加 `router.include_router(applications.router)` |
| **测试** | `tests/test_applications.py` 新建 5 tests |
| **入参** | create: `{"candidate_id", "job_id", "cover_letter?"}` ; update: `{"status"}` |

#### 0.7 Settings API 端点

| 属性 | 值 |
|:---|:---|
| **文件** | 新建 `apps/api/app/api/settings.py` (40 行) + 新增 `apps/api/app/models/setting.py` (15 行) + Alembic migration |
| **当前** | Settings 页面纯前端 localStorage |
| **目标** | 简单 key-value 设置读写（user_id → key → value）|
| **存储** | 新建 `user_settings` 表（id UUID PK, user_id FK, setting_key VARCHAR, setting_value JSONB, updated_at），不做 User 表 JSONB 字段（不存在，加 migration 成本一样）|
| **改动** | 40 行 route + 15 行 model + 1 个 migration 文件 |

#### 0.8 Settings 页面端口修复

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/web/app/(dashboard)/settings/page.tsx` |
| **当前** | `localhost:8001`（错误端口） |
| **目标** | `localhost:8000`（与 API 一致）|
| **改动** | 1 行 |

#### 0.9 RouterAgent — 实现完整意图分类（替代原 0.9 OMLXClient，因 OMLXClient 已有错误处理）

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/agents/router_agent.py` |
| **当前** | `return {"intent": "unknown", "confidence": 0}` stub |
| **目标** | LLM 分类用户输入为 `write_jd / screen_resume / evaluate_candidate / schedule_interview / query_data / chat` 六类 |
| **改动** | ~60 行（2 个新 prompt + 分类逻辑 + gate 检查）|
| **降级** | LLM 不可用时 keyword 匹配降级（"JD"→write_jd, "筛选"→screen_resume 等）|
| **测试** | `tests/test_agents.py` 扩 2 tests（LLM 路径 + keyword 降级路径）|

---

### Group B（1 项，依赖 Group A 的 0.1）

#### 0.2 `/pipeline/generate-report` — 接入 ReportService（等待 0.1 完成）

| 属性 | 值 |
|:---|:---|
| **依赖** | 0.1 ReportService 必须已完成 |
| **文件** | `apps/api/app/api/pipeline.py` |
| **当前** | `return {"success": True, "message": "报告生成功能将在后续迭代实现"}` |
| **目标** | 接收 `candidate_id + job_id` → 调用 `ReportService().generate_report()` |
| **改动** | 15 行 |
| **入参** | `{"candidate_id": UUID, "job_id": UUID}` |
| **出参** | `{"success": true, "data": ReportService 输出}` |
| **错误** | candidate_id/job_id 不存在 → 404; LLM 失败 → 200 + `llm_generated: false` 降级 |

---

### ⚠️ Phase 0 退出检查

```
[ ] `pytest` 全部 58+ tests 通过（原 46 + 新增 12）
[ ] `lsp_diagnostics` 后端所有修改文件无 error
[ ] `pnpm build` 前端无类型/编译错误
[ ] POST /pipeline/generate-report 返回结构化评估报告（非 stub 文本）
[ ] POST /human-loop/stop 返回已清理的 approval_id 列表
[ ] GET /settings?user_id=X 返回用户 key-value
[ ] POST /router/classify 返回正确的 intent（非 "unknown"）
```

---

## Phase 1：数据流闭环（2 周，依赖 Phase 0）

> 目标：候选人从「导入」到「面试安排」的全链路跑通，每一步失败有明确错误提示。
> 不做：不重构前端代码、不迁 tRPC、不做性能优化、不改数据库 schema。

### 1.1 串联数据流——状态机 + 边界检查

| 属性 | 值 |
|:---|:---|
| **缺失** | Candidate → Pipeline 之间无 "创建 screening task" 动作；Pipeline → Evaluation 之间无 await ReportService 的等待 |
| **目标** | 新增 `ScreeningTask` service 方法或状态流转函数 |
| **设计决策** | **方案 A（选中的）**：同步等待 + SSE 推送。理由：已有 OMLXClient 超时处理，LLM 10-15s 延迟在 SSE 场景下可接受。后期若需要异步再做方案 B（Celery/RabbitMQ）。|
| **文件** | `apps/api/app/services/candidate.py`（新增状态流转）, `apps/api/app/api/pipeline.py`（等待 ReportService）|

### 1.2 Pipeline SSE 进度推送

| 属性 | 值 |
|:---|:---|
| **后端** | SSE endpoint: `GET /api/v1/pipeline/{task_id}/stream` → 事件：`step_complete`, `gate_check`, `error`, `done` |
| **前端** | `apps/web/components/features/screening/StepIndicator.tsx` 新建组件（80 行），接收 SSE → 显示当前步骤/Gate 状态/百分比 |
| **改动** | 后端 ~50 行; 前端新建 1 组件 ~80 行 |
| **标准化** | SSE 数据格式：`{"type": "step_complete" | "gate_check" | "error" | "done", "data": {...}, "timestamp": ISO8601}` |

### 1.3 HumanLoop UI 确认界面

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/web/app/(dashboard)/interview/page.tsx`（~120 行追加）|
| **当前** | Interview 页面有 CRUD 但缺少"待审批提案"视图 |
| **目标** | HumanLoopAgent 创建的 proposal → 前端审批卡片（面试时间/面试官/邮件草稿）→ 确认/修改/拒绝 |
| **状态机** | `pending` → `approved`（更新 Interview 表 status + 触发邮件动作）/ `rejected`（释放 slot）+ 反馈输入框 |

### 1.4 统一后端错误响应格式

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/main.py`（exception handler）+ 扫描所有 route 文件 |
| **当前** | 部分返回 `{"success": true, "data": ...}`，部分直接 return data，部分 `{"error": "..."}` |
| **目标** | 全局一致：成功 `{"success": true, "data": T}`；失败 `{"success": false, "error": string, "details?": FieldError[]}` |
| **改动** | 修改 exception handler + 全量 route 文件扫描对齐 |

### 1.5 前端统一错误处理

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/web/lib/api.ts`（拦截器）+ `apps/web/components/common/ErrorBoundary.tsx`（60 行）|
| **当前** | 每页单独 try/catch，有的弹 Toast 有的静默失败 |
| **目标** | API client 层统一拦截 4xx → Toast; 5xx → ErrorBoundary fallback UI |

### 1.6 补全关键路径测试（模块级覆盖率目标）

| 属性 | 值 |
|:---|:---|
| **目标** | Pipeline + Aggregator + HumanLoop 单元测试行覆盖率 ≥ 80%（非全局 70%）|
| **文件** | `tests/test_pipeline.py` 扩至 8+ tests; `tests/test_agents.py` 扩至 8+ tests |
| **原则** | 所有 LLM 调用用 `unittest.mock.patch` mock，确保确定性 |

### 1.7 CI 引入安全扫描

| 属性 | 值 |
|:---|:---|
| **文件** | `.github/workflows/ci.yml` |
| **当前** | 无 secret 检测、无 lint |
| **目标** | 在 test job 前加两步：(1) `grep -rn 'sk-[A-Za-z0-9]' --include='*.py' --include='*.ts' .` (2) `ruff check apps/api/` |
| **改动** | 10 行 YAML |

### ⚠️ Phase 1 退出检查

```
[ ] Playwright E2E test: `npx playwright test tests/e2e/screening-flow.spec.ts` 通过
    （覆盖：简历上传 → 初筛完成 → 报告生成 → 面试安排确认 全链路）
[ ] SSE 推送在 DevTools Network tab 中可见事件流（step_complete / gate_check / done）
[ ] HumanLoop 审批卡片可操作（查看 pending → 确认 → 状态变更为 approved）
[ ] 所有 API 返回统一 `{success, data/error}` 格式
[ ] 前端无静默失败：4xx 弹 Toast，5xx 显示 ErrorBoundary
[ ] `pytest` 全部通过 + Pipeline/Aggregator/HumanLoop 模块覆盖率 ≥ 80%
[ ] CI 中安全扫描步骤存在
[ ] `pnpm build` 通过
```

---

## Phase 2a：跨会话记忆（3 周，依赖 Phase 1）

> 前提条件：Phase 1 退出检查全部通过。
> 额外前置：memory-design.md 设计文档完成并通过 Momus 审查。
> 不做：不做文件系统 FTS5、不做行为画像建模、不改已有 Agent 接口。

### 2a.1 设计文档先行（Momus Gate）

| 属性 | 值 |
|:---|:---|
| **产出** | `.omo/plans/memory-design.md` |
| **内容** | session_summaries 表 schema、LLM 摘要 prompt、Qdrant 纯向量检索策略（放弃 FTS——`simple` 配置不支持中文分词）、User 审查 UI 设计、检索加权策略 |
| **审批** | Momus 审查通过后 Phase 2a 方可开始执行。若 Momus 驳回，修改设计后重新审查。|

### 2a.2 数据库迁移

| 属性 | 值 |
|:---|:---|
| **文件** | 新建 Alembic migration |
| **表** | `session_summaries(id UUID PK, user_id FK→users, summary_text TEXT, key_insights JSONB, created_at, updated_at)` |
| **索引** | `created_at DESC`（最近优先检索）+ Qdrant 向量索引（替代 FTS）|
| **改动** | ~50 行迁移 + 新建 model |

### 2a.3 会话摘要自动生成（AgentService hook）

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/agents/agent_service.py`（~80 行追加）|
| **触发** | `execute_conversation()` 完成后自动异步调用，不阻塞响应 |
| **LLM prompt** | "从以下对话中提取关键洞察：用户偏好、常用筛选条件、拒绝原因、成功模式。输出 JSON。" |
| **写入** | `SummaryService.create(user_id, summary_text, key_insights)` |

### 2a.4 历史摘要检索 + Agent prompt 注入

| 属性 | 值 |
|:---|:---|
| **文件** | 新建 `apps/api/app/services/summary_service.py`（~100 行）|
| **检索策略** | Qdrant 纯向量检索（放弃 FTS——PostgreSQL `simple` 配置不支持中文分词，`zhparser`/`jieba` 引入成本高）。query 嵌入后向量相似度 Top 5。后期精度不足时可加 `pg_trgm`。|
| **注入** | 新会话初始化时，system prompt 追加 `"以下是你之前了解到的信息：\n{检索结果摘要}"` |

### 2a.5 用户可审查/编辑/删除记忆（前端）

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/web/app/(dashboard)/settings/page.tsx` 增加"记忆管理" tab（~100 行）|
| **功能** | 列表查看 + 全文搜索（前端过滤）+ 编辑单条 + 删除单条 |

### ⚠️ Phase 2a 退出检查

```
[ ] 会话结束后 `session_summaries` 表写入数据（psql 查表确认）
[ ] 新会话 system prompt 中包含历史摘要（服务端日志可查）
[ ] Settings 页面'记忆管理' tab 可查看/搜索/删除记忆
[ ] `pytest` 全部通过 + summary_service 覆盖率 ≥ 75%
[ ] `pnpm build` 通过
```

---

## Phase 2b：技能演化（4 周，依赖 Phase 1 + 可选依赖 Phase 2a）

> 依赖澄清：2b 只需要 Phase 1 的数据流闭环（确保有成功的 session 记录）和 session_summaries 表（Phase 2a 的 2a.2）。
> 2b 不依赖 Phase 2a 的 2a.4（混合检索）/2a.5（前端审查），因为 2b 直接从 session_summaries 表读成功的 session 记录即可。
> → **2a 和 2b 可并行启动**。

### 2b.1 Skill 模板提取器

| 属性 | 值 |
|:---|:---|
| **文件** | 新建 `apps/api/app/skills/extractor.py`（~120 行）|
| **输入** | session_summaries 中标记为"成功"的 session（用户点过"保留此经验"或 pipeline 评分 ≥ 80）|
| **LLM prompt** | "分析以下招聘筛选经验，提取可复用的 Skill：{步骤、判断标准、工具调用模式、权重}" |
| **输出** | `{"name": str, "description": str, "trigger_conditions": str, "steps": [...], "tools_needed": [...], "confidence": float}` |

### 2b.2 置信度门控 + 自动/手动注册

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/skills/extractor.py` + `apps/api/app/skills/installer.py` |
| **门控规则** | confidence ≥ 0.8 → 自动写入 `app/skills/{name}/` 目录（备注：0.8 是初始拍脑袋值，上线后统计用户确认率来校准）|
| **门控规则** | confidence < 0.8 → 写入 `pending_skills` 表 → Settings 页面"待确认"列表 |
| **改动** | ~60 行 |

### 2b.3 新会话自动加载匹配 Skill

| 属性 | 值 |
|:---|:---|
| **文件** | `apps/api/app/agents/agent_service.py`（~40 行追加）|
| **匹配策略** | 新会话的 intent（RouterAgent 分类结果）→ 模糊匹配 Skill.trigger_conditions → 匹配的 Skill 自动注入 tools 列表 |
| **举例** | intent=screen_resume → 自动激活"Java 后端初筛 Skill"→ tools 列表多出该 Skill 的工具 |

### ⚠️ Phase 2b 退出检查

```
[ ] 从 3+ 次成功 session 中提取出 ≥ 1 个可复用 Skill（JSON 文件写入 app/skills/{name}/）
[ ] confidence ≥ 0.8 的 Skill 自动注册后，新会话 tools 列表中可见
[ ] confidence < 0.8 的 Skill 在 Settings"待确认"页出现
[ ] 提取的 Skill 在后续会话中实际被调用并返回有意义的结果
[ ] `pytest` 全部通过 + `pnpm build` 通过
```

---

## Phase 3：招聘助手智能化（3-4 周，依赖 Phase 2 完成）

| # | 功能 | 文件 | 改动量 | 前置 |
|:---|:---|:---|:---|:---|
| 3.1 | 主动推荐：新简历上传后自动匹配历史 JD + 推送 Top 5 | `apps/api/app/agents/agent_service.py` + `apps/api/app/api/candidates.py` | ~80 行 | Phase 1（数据流通）|
| 3.2 | 多轮对话初筛：Agent 追问候选人细节再出分 | `apps/api/app/agents/pipeline.py` 改为多轮交互 | ~100 行 | Phase 2b（技能就位）|
| 3.3 | 邮件/日历 MCP 集成 | 新建 `apps/api/app/tools/email_tool.py` + `calendar_tool.py` | ~150 行 | Phase 1（HumanLoop UI 已确认）|
| 3.4 | 面试题智能生成 | 新建 `apps/api/app/services/interview_question_service.py` | ~80 行 | Phase 1 |

### ⚠️ Phase 3 退出检查

```
[ ] 上传简历后 30 秒内 API 返回主动推荐结果（非空）
[ ] 多轮对话初筛可交互式完成（Agent 追问 → 用户回答 → 更新评分 → 出结论）
[ ] MCP 邮件通过 HumanLoop 确认后实际送达（使用测试邮箱验证）
[ ] 所有 Phase 3 功能有 E2E 测试覆盖
[ ] `pnpm build` 通过
```

---

## Phase 4：商用化（4 周，依赖 Phase 1 稳定，与 Phase 3 可并行）

| # | 功能 | 文件 | 改动量 | 前置 |
|:---|:---|:---|:---|:---|
| 4.1 | **多租户**（方案待定：Phase 4 启动前必须出设计文档比较 RLS / Schema-per-tenant / DB-per-tenant）| `apps/api/app/core/tenant.py` 新建 + 改造 | ~200 行 | Phase 1 稳定 |
| 4.2 | RBAC（admin/hr/recruiter）| `apps/api/app/api/auth.py` + middleware | ~100 行 | Phase 1 |
| 4.3 | 数据合规（候选人导出/删除/脱敏）| `apps/api/app/api/candidates.py` 扩展 | ~60 行 | — |
| 4.4 | 计费（Stripe 集成）| 新建 `apps/api/app/api/billing.py` | ~150 行 | — |
| 4.5 | Docker Compose 生产配置 | `docker-compose.prod.yml` + README 更新 | ~80 行 | — |

### ⚠️ Phase 4 退出检查

```
[ ] 两个不同的 tenant 登录后各自看到隔离的数据（手动验证）
[ ] admin/hr/recruiter 三种角色权限差异可验证（API 返回不同结果）
[ ] 候选人数据可完整导出为 JSON 且可物理删除
[ ] Stripe webhook 收付正常
[ ] `pnpm build` 通过
```

---

## 风险与依赖

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---|:---|:---|
| Phase 0 改动量大（9 项），mock 遗漏导致合入后回归 | 中 | 现有 46 个测试红 | 每个 sub-task 后跑 pytest 全量，不累积 |
| 方案 A（同步 SSE）在 LLM 10s+ 延迟下体验差 | 中 | 用户等待超时 | SSE 发送 `heartbeat` 每 5 秒保持连接；LLM timeout 设为 30s |
| Phase 2b skill 提取质量低，用户不信任 | 高 | 功能弃用 | 置信度门控（0.8） + 人工确认流程；上线后统计用户确认校准阈值 |
| Phase 3 MCP 需要第三方 API key | 中 | 阻塞邮件集成 | 先用 mock SMTP 验证流程，API key 单独配置 |
| Phase 4 多租户方案选型错误 | 中 | 后期迁移成本高 | Phase 4 启动前强制出设计文档 + Momus 审查 |

---

## 总工作量估算

| Phase | 单人周 | 并行策略 | 说明 |
|:---|:---|:---|:---|
| Phase 0 | 1 周 | Group A 8 项并行（理论上 1 人 1 天/项 × 8 项，但不同文件需上下文切换，实际 1 周）| 纯修 bug，无新技术挑战 |
| Phase 1 | 2 周 | 1.1 串行前置 → 1.2+1.3 并行 → 1.4+1.5+1.6+1.7 并行 | 数据流核心，E2E 测试最耗时 |
| Phase 2a | 3 周 | 设计先 1 周 → DB+service+UI 并行 2 周 | 设计文档需 Momus 审查，Delay risk |
| Phase 2b | 4 周 | 2b.1 先做（提取器），2b.2+2b.3 并行 | AI 提取质量不确定，可能有迭代 |
| Phase 3 | 3-4 周 | 3.1+3.2+3.3+3.4 全部可并行 | 但 MCP 需要第三方 key，被动等 |
| Phase 4 | 4 周 | 4.1+4.2+4.3 并行；4.4+4.5 可单独 | 多租户设计决策最长路径 |
| **合计** | **17-19 周** | | |

单人开发（线性执行）：**18 周**
双人开发（Phase 内并行）：**约 12 周**

---

## Momus 审查条目（来自审查报告，已解决的标记 ✓）

| # | 问题 | 状态 |
|:---|:---|:---|
| F1 | OMLXClient 已有 try/except，Phase 0.9 删除 | ✓ 已删除，替换为 RouterAgent 修复 |
| F2 | User model 无 JSONB，Settings 需新表 | ✓ 改用 `user_settings` 表 + migration |
| F3 | Application model 字段未验证 | ✓ 0.6 加前置验证步骤 |
| D1 | Phase 0 9 项不完全并行 | ✓ 改为 2 组（Group A 8 项并行 → Group B 1 项依赖）|
| D2 | Phase 2a→2b 依赖被高估 | ✓ 明确 2b 只需 session_summaries 表，改为可并行 |
| D3 | Momus gate 流程缺失 | ✓ 2a.1 写明"Momus 审查通过方可执行" |
| V1 | "手动走通"不可测量 | ✓ 改为 Playwright E2E test 通过 |
| V2 | FTS 不支持中文分词 | ✓ 放弃 FTS，改用 Qdrant 纯向量检索 + pg_trgm 备选 |
| V3 | 覆盖率目标重复 | ✓ Phase 0 不提覆盖率；Phase 1 改为模块级 80% |
| M1 | 缺少"不做什么"边界 | ✓ 每个 Phase 头部新增 Scope 说明 |
| M2 | RouterAgent stub 未安排 | ✓ Phase 0.9 新增 |
| M3 | 多租户方案未选型 | ✓ Phase 4.1 加"启动前出设计文档" |
| M4 | `pnpm build` 遗漏 | ✓ 所有 Phase 退出检查已加 |
