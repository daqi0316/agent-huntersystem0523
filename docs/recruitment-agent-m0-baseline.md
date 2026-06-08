# AI 招聘 Agent 深度缺口填补 — M0 基线冻结

> 日期：2026-06-08  
> 来源规划：`AI招聘Agent深度缺口填补规划.md` 第七章 Momus 审核修正版  
> 阶段目标：确认当前系统已有模型、API、Agent、页面，建立进入 M1 的实施基线。

---

## 1. M0 审核结论

当前系统已经具备招聘 SaaS 的基础容器：候选人、职位、投递、面试、评估、Dashboard、Agent Chat、MCP Host、知识库、记忆与通知等模块均存在。

但它还不是“懂招聘业务深度”的 Agent 系统。主要缺口集中在：

1. 没有独立的岗位画像库；现有 `job_positions` 只是职位 CRUD。
2. 没有招聘业务状态机；现有 `CandidateStatus` / `ApplicationStatus` 是粗粒度流程状态。
3. 没有结构化淘汰原因体系；淘汰原因无法稳定统计与回流。
4. 没有候选人状态历史和招聘决策审计链；候选人 timeline 是聚合展示，不是严格状态事件表。
5. 评估维度多数仍从 `match_score` 派生或文本存储，缺少岗位画像驱动的真实维度评分。
6. Agent 层已有 resume/sourcing/screening/interview/offer/onboarding 分工，但缺少受控业务工具和可验证输出 schema。

**M0 通过判断**：基础实体存在，可复用；缺口明确；第一版 MVP 应从 `Java_P7` 单岗位打穿，不应立即扩展薪酬、寻访、入职和面试官效能分析。

---

## 2. 当前能力矩阵

### 2.1 后端模型

| 能力域 | 当前文件 | 当前能力 | M1/M2 结论 |
|---|---|---|---|
| 候选人 | `apps/api/app/models/candidate.py` | `Candidate` + `CandidateStatus`，含姓名、邮箱、技能、经验、教育、公司、title、粗状态 | 可复用基础表；需新增招聘业务状态机字段或独立状态事件表 |
| 职位 | `apps/api/app/models/job_position.py` | `JobPosition` + `JobStatus`，含 title、department、description、requirements、salary_range | 可作为职位实体；不能替代岗位画像库 |
| 投递 | `apps/api/app/models/application.py` | `Application` + `ApplicationStatus`，含 candidate/job 关系、match_score、ai_summary、resume_url | 可承载候选人与岗位关系；需补维度评分和结构化评估结果 |
| 面试 | `apps/api/app/models/interview.py` | `Interview` + `InterviewStatus` + `InterviewType`，含 schedule、feedback 文本 | 可复用排期；需补面试轮次、结构化大纲、反馈强约束 |
| 面试评价 | `apps/api/app/models/interview_evaluation.py` | `InterviewEvaluation`，含 round、overall_score、verdict、dimensions、red_flags、feedback | 可作为 M3 基础；`dimensions` 当前为文本/JSON 字符串，需标准化 schema |
| 面试录音 | `apps/api/app/models/interview_recording.py` | 录音上传、转写、录音生成评价 | 可作为后续增强；不进入第一版 MVP |
| MCP Server | `apps/api/app/models/mcp_server.py` | MCP server 注册与工具缓存 | 可复用；M1 工具必须走 MCPHost/get_mcp_host 标准入口 |
| 记忆 | `apps/api/app/models/memory_fact.py` | 事实记忆 | 可后续接关系时间线；不进入 M1 必做 |
| 通知 | `apps/api/app/models/notification.py` | 通知记录 | 可后续接状态提醒；M1 只记录事件，不强做节奏通知 |
| 审计 | `apps/api/app/models/audit_log.py` | 审计日志基础能力 | 可复用为状态流转审计 |

### 2.2 后端 API

| API 域 | 当前文件 | 当前能力 | M1/M2 结论 |
|---|---|---|---|
| 路由注册 | `apps/api/app/api/router.py` | `/api/v1` 下已注册 candidates/jobs/applications/interviews/evaluations/dashboard/agent/mcp/tools 等 | 路由结构可复用 |
| 候选人 | `apps/api/app/api/candidates.py` | 候选人 CRUD + `/candidates/{id}/timeline` 聚合展示 | 需新增受控状态流转 API；timeline 可展示但不是事件源 |
| 职位 | `apps/api/app/api/jobs.py` | 职位 CRUD | 需新增 job profile API，避免污染普通职位 CRUD |
| 投递 | `apps/api/app/api/applications.py` | 投递 CRUD / 状态相关能力 | 可承载 candidate-job 关系；需补评估结果与淘汰原因 |
| 面试 | `apps/api/app/api/interviews.py` | 面试列表、创建、确认、取消、完成、录音、评价保存 | 可复用排期与评价保存；需补大纲生成和结构化反馈校验 |
| 评估 | `apps/api/app/api/evaluations.py` | 从 Application 聚合评估，维度分数由 match_score 模拟 | M2 必须替换为真实岗位画像维度评分来源 |
| 筛选 | `apps/api/app/api/screening.py`、`apps/api/app/api/pipeline.py` | AI 筛选与 pipeline | 可复用触发入口；需补风险标记/评分 schema |
| Agent | `apps/api/app/api/agent.py`、`agent_events.py` | Agent Chat / SSE | 可复用；注意 SSE 鉴权走现有标准 hook |
| MCP | `apps/api/app/api/mcp_tools.py`、`mcp_servers.py`、`mcp_ab.py` | MCP host endpoints、server 管理、AB 路由 | 可复用；新增工具必须避免裸 CRUD |
| Dashboard | `apps/api/app/api/dashboard.py`、`dashboard_reports.py` | 统计与报表 | M4 可接最小漏斗；M1/M2 不优先 |

### 2.3 Service / Agent / MCP 能力

| 能力域 | 当前文件 | 当前能力 | 缺口 |
|---|---|---|---|
| 候选人服务 | `apps/api/app/services/candidate.py` | CRUD + 状态推进到 evaluating/evaluated/interview/completed | 状态粒度不符合招聘业务状态机；无合法转换表 |
| 职位服务 | `apps/api/app/services/job.py` | 职位 CRUD | 无岗位画像模板、维度权重、行为锚定 |
| 投递服务 | `apps/api/app/services/application.py` | 投递 CRUD / 状态更新 | 缺少结构化淘汰原因与评估 evidence |
| 面试服务 | `apps/api/app/services/interview.py` | 排期、确认、取消、完成、评价保存 | 缺少岗位画像驱动面试大纲和反馈强校验 |
| 简历解析 | `apps/api/app/services/resume_parser.py`、`graphs/agents/resume_parser.py` | 简历文本解析 | 缺少稳定性/空窗期/断层风险标记 |
| 筛选 | `apps/api/app/services/screening.py`、`graphs/agents/screening.py` | 简历筛选流程 | 缺少多维评分与 evidence 输出 |
| 业务 Agent | `apps/api/app/graphs/agents/{resume_parser,sourcing,screening,interview,offer,onboarding}.py` | 已有 Agent 分层骨架 | 缺少受控业务工具、结构化 schema、人工确认边界 |
| Orchestrator | `apps/api/app/graphs/orchestrator.py`、`orchestrator_graph.py` | 编排图存在 | 目前不是“状态 + 意图 + 上下文”的招聘路由 |
| MCP Host | `apps/api/app/mcp/host.py` | `MCPHost` + `get_mcp_host()` 标准入口 | 新工具必须使用该入口，禁止直接 import module-level singleton |

### 2.4 前端页面

| 页面 | 当前文件 | 当前能力 | M1/M2 结论 |
|---|---|---|---|
| Dashboard | `apps/web/app/(dashboard)/dashboard/page.tsx` | 统计入口 | M4 接最小招聘漏斗 |
| 候选人列表 | `apps/web/app/(dashboard)/candidates/page.tsx` | 候选人列表 | M1 复用入口 |
| 候选人详情 | `apps/web/app/(dashboard)/candidates/[id]/page.tsx` | 候选人详情 | M1/M2 展示状态机、风险、评分、决策链 |
| 职位列表 | `apps/web/app/(dashboard)/jobs/page.tsx` | 职位列表 | M1 复用 |
| 职位详情 | `apps/web/app/(dashboard)/jobs/[id]/page.tsx` | 职位详情 | M1 可加岗位画像入口，但建议独立 profile 区块 |
| 筛选 | `apps/web/app/(dashboard)/screening/page.tsx` | 筛选流程页 | M2 复用为风险/评分触发与展示 |
| 评估 | `apps/web/app/(dashboard)/evaluation/page.tsx` | 评估列表 | M2 替换模拟维度为真实结构化评分 |
| 面试 | `apps/web/app/(dashboard)/interview/page.tsx` | 面试排期、评价 dialog、录音组件 | M3 复用为面试大纲和结构化反馈入口 |
| 报表 | `apps/web/app/(dashboard)/reports/page.tsx` | 报表页面 | M4 接淘汰原因分布和最小漏斗 |
| Agent Chat | `apps/web/app/(dashboard)/agent/page.tsx` | Agent 对话 | 非 M1 主路径；后续接 Orchestrator 路由 |
| MCP Servers | `apps/web/app/(dashboard)/mcp-servers/page.tsx` | MCP server 管理 | 工具调试可复用 |

---

## 3. Gap 清单

### 3.1 M1 必须补齐

| Gap | 类型 | 建议落点 | 完成后能力 |
|---|---|---|---|
| 岗位画像库 | Schema/API/UI | 新增 `job_profiles` 模型、service、API；前端在职位详情或独立配置区展示 | Java_P7 有硬性要求、软性要求、评分维度、权重、行为锚定 |
| 评分卡定义 | Schema/Service | `job_profile.evaluation_dimensions` 或独立评分卡表 | 面试和筛选共用同一套维度 |
| 淘汰原因体系 | Schema/Service/API/UI | 新增标准原因枚举/表 + candidate/application rejection record | 淘汰必须带主原因、阶段、evidence、是否可回流 |
| 招聘状态机 | Service/Tool/API | 新增状态枚举、转换表、状态历史表、`update_candidate_state` | 状态变更受控、可审计、可触发后续动作 |
| 状态历史审计 | Schema/Service | 独立事件表或复用 audit log + 专用 state_history 表 | 候选人决策链可追溯 |

### 3.2 M2 必须补齐

| Gap | 类型 | 建议落点 | 完成后能力 |
|---|---|---|---|
| 风险标记 | Service/Agent/API/UI | 简历评估 service 输出 `risk_flags` | 频繁跳槽、空窗期、学历/经历断层可解释 |
| 多维匹配评分 | Service/Agent/API/UI | Application 或新 evaluation result 表 | 分维度评分不再由 match_score 模拟 |
| Evidence 约束 | Schema/Validator | Pydantic schema 校验 | 无证据时输出“需核实”，禁止臆测 |
| Java_P7 固定样例 | Test fixture | 后端测试目录 | 重复运行输出稳定 |

### 3.3 M3/M4 后续补齐

| Gap | 类型 | 阶段 | 备注 |
|---|---|---|---|
| 面试大纲生成 | Tool/API/UI | M3 | 依赖 M1 岗位画像 + M2 风险标记 |
| 结构化反馈强校验 | API/UI/Test | M3 | 依赖评分卡 |
| 最小漏斗 Dashboard | API/UI | M4 | 依赖状态机和淘汰原因 |
| 招聘结果回流 | Schema/Analysis | M5 | 样本不足前不做趋势判断 |

---

## 4. 第一版 MVP 边界

### 4.1 必须做

```text
Java_P7 岗位画像
状态机
状态历史/audit
结构化淘汰原因
简历风险标记
岗位匹配评分
面试大纲生成
结构化反馈
候选人决策链展示
最小 Dashboard
系统健康检查
```

### 4.2 明确不做

```text
完整薪酬数据库
自动谈判 Agent
完整人才地图
外部招聘网站自动寻访
面试官偏见自动判定
试用期 180 天真实闭环
多岗位模板批量扩展
自动修改岗位画像
```

---

## 5. M1 进入条件

M0 结束后，进入 M1 的条件如下：

1. 基础实体存在：Candidate / JobPosition / Application / Interview / InterviewEvaluation 均已确认。
2. 基础 API 存在：`/candidates`、`/jobs`、`/applications`、`/interviews`、`/evaluations` 均已注册。
3. 前端入口存在：候选人、职位、筛选、评估、面试、报表页面均已确认。
4. MCP Host 标准入口存在：新增工具必须通过 `get_mcp_host()` 相关路径接入。
5. 第一版岗位冻结为 `Java_P7`，不扩展多岗位。
6. 每次代码改动后必须运行 `bash scripts/health-check.sh`。

---

## 6. M1 推荐实施切片

### Slice M1-1：招聘状态机与历史事件

- 新增招聘业务状态枚举，不直接替换现有粗粒度 `CandidateStatus`。
- 新增状态历史表：candidate_id、from_state、to_state、reason、operator、triggered_actions、created_at。
- 新增状态转换 service：只允许合法转换。
- 新增 `update_candidate_state` 受控入口。

### Slice M1-2：岗位画像与评分卡

- 新增 `job_profiles`。
- 首个 seed：`Java_P7`。
- 字段包含 hard_requirements、soft_requirements、evaluation_dimensions、salary_band、interview_focus。
- 评分维度必须包含 weight、score anchors、red flags。

### Slice M1-3：结构化淘汰原因

- 新增淘汰原因分类。
- 淘汰候选人时必须填写 reason_category、primary_reason、evidence、stage。
- 候选人详情页展示淘汰原因。

### Slice M1-4：候选人详情决策链展示

- 聚合状态历史、评估、面试、反馈、淘汰原因。
- 前端只展示真实结构化字段；缺失时明确显示“未采集”。

---

## 7. 风险记录

| 风险 | 当前状态 | 控制方式 |
|---|---|---|
| Enum 历史坑 | 代码已有 enum/UUID 决策注释 | 新 enum 必须遵守现有 schema audit / migration 约束 |
| 直接改 CandidateStatus 可能破坏旧流程 | 当前服务大量依赖 CandidateStatus | 招聘深度状态机建议新增字段/表，不直接替换旧 enum |
| 维度评分当前为模拟值 | `evaluations.py` 从 match_score 派生维度 | M2 替换为真实结构化评分前，不能用于闭环分析 |
| timeline 不是事件源 | 当前 `/candidates/{id}/timeline` 是聚合现有表 | M1 必须新增状态历史/决策事件源 |
| Agent 输出不可测 | 当前 Agent 分层存在但 schema 不强 | M2 所有 Agent 输出先过 Pydantic/JSON Schema |

---

## 8. M0 验收状态

| 验收项 | 状态 | 证据 |
|---|---|---|
| 能列出将复用的后端模型/API/前端页面/Agent 模块 | 通过 | 本文第 2 节 |
| 明确第一版只支持一个岗位模板 `Java_P7` | 通过 | 本文第 4/5 节 |
| 明确 MVP 不做范围 | 通过 | 本文第 4.2 节 |
| 明确进入 M1 的前置条件 | 通过 | 本文第 5 节 |
| 系统健康检查结果记录 | 通过 | `bash scripts/health-check.sh`：通过 11，失败 0 |

---

## 9. 下一步

若健康检查通过，下一步进入：

```text
M1-1：招聘状态机与历史事件
```

优先原因：状态机是后续岗位画像触发、面试大纲生成、淘汰原因闭环、Dashboard 漏斗统计的共同骨架。
