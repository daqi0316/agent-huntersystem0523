# MCP v4 PR-9 工具盘点 — Type A/B/C 分类

> **盘时**: 2026-06-06
> **修订**: 2026-06-06（C-1 修复 — 统一为 38 工具 / 4 A / 34 B / 0 C）
> **目的**: 修正 v0.1 "机械迁 19 工具" 假设（M-2 Momus 反馈）
> **结论**: **38 工具 / 4 Type A / 34 Type B / 0 Type C**（以 §2 大表为唯一事实源）
> **文件**: 23 .py 文件（20 tool 文件 + 1 helper + 1 registry + 1 init）

## 1. 分类标准

| 类型 | 定义 | 迁移方式 |
|---|---|---|
| **A — 纯 tool** | 无 DB / 无外部 IO（除自己声明的）/ 无 service 依赖 | 直接迁 server（机械）|
| **B — service wrapper** | 打开 AsyncSessionLocal 调 service / 调 LLM / 调外部 API | 拆 thin wrapper 调 service 即可（仍可迁 server）|
| **C — 流式 / SSE** | handler 持续输出或长事务 | 单独设计（不在 PR-9 范围）|

## 2. 全部 38 工具盘点（事实源）

| # | 文件 | 工具名 | 类别 | DB | LLM | 外部 API | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | `calc_tool.py` | `calculate` | **A** | ❌ | ❌ | ❌ | 纯函数表达式求值 |
| 2 | `greet_tool.py` | `greet` | **A** | ❌ | ❌ | ❌ | 字符串拼接 |
| 3 | `time_tool.py` | `get_current_time` | **A** | ❌ | ❌ | ❌ | datetime.now |
| 4 | `docs_search_tool.py` | `search_documents` | **A** | ❌ | ❌ | ❌ | in-memory 8 条记录 |
| 5 | `tavily_search.py` | `tavily_search` | **B-light** | ❌ | ❌ | ✅ Tavily | 需 TAVILY_API_KEY，**必走 server**（不能让 API key 留在主进程）|
| 6 | `operation_log.py` | `log_operation` | **B** | ✅ 写 | ❌ | ❌ | 调 OperationService |
| 7 | `candidate.py` | `create_candidate` | **B** | ✅ 写 | ❌ | ❌ | CandidateService.create |
| 8 | `candidate.py` | `update_candidate` | **B** | ✅ 写 | ❌ | ❌ | CandidateService.update |
| 9 | `candidate.py` | `archive_candidate` | **B** | ✅ 写 | ❌ | ❌ | 软删除（status=ARCHIVED）|
| 10 | `candidate_search.py` | `search_candidates` | **B** | ✅ 读 | ❌ | ❌ | list + 过滤 |
| 11 | `candidate_search.py` | `get_candidate_detail` | **B** | ✅ 读 | ❌ | ❌ | 聚合 interviews + applications |
| 12 | `job.py` | `create_job` | **B** | ✅ 写 | ❌ | ❌ | JobService.create |
| 13 | `job.py` | `update_job` | **B** | ✅ 写 | ❌ | ❌ | JobService.update |
| 14 | `job.py` | `close_job` | **B** | ✅ 写 | ❌ | ❌ | status=CLOSED |
| 15 | `application.py` | `create_application` | **B** | ✅ 写 | ❌ | ❌ | ApplicationService.create |
| 16 | `application.py` | `update_application_status` | **B** | ✅ 写 | ❌ | ❌ | ApplicationService.update |
| 17 | `interview.py` | `schedule_interview` | **B** | ✅ 写 | ❌ | ❌ | InterviewService.schedule |
| 18 | `interview.py` | `cancel_interview` | **B** | ✅ 写 | ❌ | ❌ | InterviewService.cancel |
| 19 | `interview.py` | `record_feedback` | **B** | ✅ 写 | ❌ | ❌ | 直接 db.add（不走 service）— **code smell，待清理**|
| 20 | `interview_extended.py` | `reschedule_interview` | **B** | ✅ 写 | ❌ | ❌ | 直接 db.commit（**code smell**）|
| 21 | `interview_extended.py` | `complete_interview` | **B** | ✅ 写 | ❌ | ❌ | InterviewService.complete |
| 22 | `interview_extended.py` | `get_interview_detail` | **B** | ✅ 读 | ❌ | ❌ | InterviewService._get_by_id + _to_dict |
| 23 | `evaluation.py` | `save_evaluation` | **B** | ✅ 写 | ❌ | ❌ | 直接 db.add（**code smell**）|
| 24 | `evaluation.py` | `generate_evaluation_report` | **B** | ✅ 读 | ❌ | ❌ | 聚合所有 interview_evaluation |
| 25 | `dashboard.py` | `get_dashboard_stats` | **B** | ✅ 读 | ❌ | ❌ | 3 个 COUNT(*) |
| 26 | `screening.py` | `search_candidates` | **B** | ✅ 读 | ❌ | ❌ | 注意：与 candidate_search 重复 |
| 27 | `screening.py` | `get_candidate` | **B** | ✅ 读 | ❌ | ❌ | 注意：与 candidate_search 重复 |
| 28 | `screening.py` | `screen_resume` | **B** | ❌ | ✅ (调 LLM) | ❌ | ScreeningService.screen_resume |
| 29 | `screening.py` | `list_jobs` | **B** | ✅ 读 | ❌ | ❌ | JobService.list |
| 30 | `screening.py` | `get_evaluations` | **B** | ✅ 读 | ❌ | ❌ | 直接 db.execute |
| 31 | `schedule_tool.py` | `get_upcoming_interviews` | **B** | ✅ 读 | ❌ | ❌ | 复杂 join（Interview + Candidate）|
| 32 | `schedule_tool.py` | `get_schedule` | **B** | ✅ 读 | ❌ | ❌ | 月份聚合 + past/future 计数 |
| 33 | `knowledge.py` | `search_knowledge` | **B** | ❌ | ✅ (调 LLM) | ❌ | KnowledgeService.query |
| 34 | `jd.py` | `generate_jd` | **B-light** | ❌ | ✅ (调 LLM) | ❌ | get_llm_client 直接 chat |
| 35 | `resume_parser.py` | `parse_resume` | **B-heavy** | ✅ 写 | ✅ (调 LLM) | ❌ | file 下载 + LLM extract + CandidateService.create |
| 36 | `resume_parser.py` | `batch_parse_resumes` | **B-heavy** | ❌ | ✅ (调 LLM) | ❌ | 循环 parse_resume |
| 37 | `resume_parser.py` | `get_candidate_profile` | **B** | ✅ 读 | ❌ | ❌ | CandidateService.get_by_id |
| 38 | `skill_tool.py` | `install_skill_from_url` | **B-light** | ❌ | ❌ | ❌ | subprocess.run('git clone', ...) |
| — | `_file_parser_helpers.py` | (helper) | — | — | — | — | 简历下载工具函数，**非 tool，被 resume_parser 调**|
| — | `metadata.py` | (registry) | — | — | — | — | ToolMetadata + register_tool，**非 tool**|
| — | `__init__.py` | — | — | — | — | — | 初始化文件 |

**注：23 .py 文件 = 20 tool 文件（含 38 个工具） + 1 helper + 1 registry + 1 init**

## 3. 分类汇总

| 类型 | 数量 | 文件 |
|---|---|---|
| **A 纯 tool** | 4 | calc_tool, greet_tool, time_tool, docs_search_tool |
| **B service wrapper** | **34**（含 B-light 4 + B-heavy 2）| 其余所有 |
| **C 流式** | 0 | — |
| **Helper / Registry** | 2 | _file_parser_helpers, metadata |

## 4. 关键发现（修正 v0.1）

### 4.1 v0.1 假设错了

v0.1 计划说"机械迁 19-21 工具" — **错的**。实际 38 个 tool 中 34 个是 Type B，**不是纯函数**。

但好消息：**Type B 也是可迁的**——它们是 stateless wrapper（每次打开 session、调 service、关 session），subprocess 边界不影响正确性。**只是不能"机械"迁，需要保证**：
- 每个 subprocess 自己管 DB connection pool
- LLM client 初始化
- 外部 API key 注入

### 4.2 重名工具（潜在 bug）

发现 2 处重名（CI 没守住）：
- `screening.search_candidates` vs `candidate_search.search_candidates`（实现略不同，前者简化版）
- `screening.get_candidate` vs `candidate_search.get_candidate_detail`（前者缺 interviews/applications 聚合）

**风险**：agent 看到两个 search_candidates schema 不知道调哪个，LLM 可能随机选。
**修法**：PR-9 阶段合并重名工具，保留 1 个（建议 `candidate_search.py` 版本更完整）。

### 4.3 Code smell（不走 service）

3 个工具直接 `db.add/commit`，不走 service：
- `interview.record_feedback`
- `interview_extended.reschedule_interview`
- `evaluation.save_evaluation`

**风险**：跨 org 数据泄漏 / 业务规则绕过（service 才有 RLS + 业务校验）。
**修法**：PR-9 阶段一并补 service 调用，不只是迁移。

### 4.4 B-heavy 工具（DB + LLM + 文件 IO）

2 个重型：
- `resume_parser.parse_resume`（下载 + LLM + 创建 candidate + 多步 service）
- `resume_parser.batch_parse_resumes`（循环 + 错误聚合）

**风险**：subprocess crash 会丢失中间结果（已 LLM 解析但未落库）。
**修法**：PR-8 pilot 不迁 B-heavy（先验 supervisor 对 Type A/B 有效），PR-9 阶段再迁，需设计"事务边界"（先落 raw_text，再异步解析）。

## 5. PR-8 pilot 选型复核

v0.2 §3.1 选了 calc + weather：
- calc: Type A ✓
- weather (skill): 不在 `app/tools/` 根目录，是 skill server（`apps/api/app/skills/`）

**复核结论**：选型仍然对。calc 是最纯的 Type A 验证通路；weather 验 B 轨道（skill）+ 网络失败注入。

## 6. PR-9 范围建议（基于本盘点）

| 阶段 | 范围 | 估时 |
|---|---|---|
| **PR-9a** | Type A 全 4 工具 + code smell 修（3 处）| 2d |
| **PR-9b** | Type B 业务服务（candidate/job/application/interview 8 文件 16 工具）| 3d |
| **PR-9c** | Type B LLM 工具（knowledge/jd/resume_parser/screening.screen_resume）| 2d |
| **PR-9d** | Type B-light 外部 API（tavily_search）| 0.5d |
| **PR-9e** | Type B-light 子进程（skill_tool）| 0.5d |
| **PR-9f** | Type B 调度工具（schedule_tool/dashboard/screening.get_evaluations）| 1d |
| **PR-9g** | 重名工具合并（screening vs candidate_search）| 0.5d |
| **总计** | — | **9.5d** |

> **比 v0.1 估时 2-3d 多 3x**。原因为 Momus M-2 预见的"机械迁"是错的。

## 7. 服务拆分建议（13 server）

| Server ID | 含工具 | 业务域 | 估时 |
|---|---|---|---|
| `mcp-utils` | calc/greet/time/log_operation（4+1=5）| 通用工具 + 审计 | PR-8 pilot 已含 4，log_operation PR-9a 补 |
| `mcp-search` | search_documents/tavily_search（1+1=2）| 文档/网络搜索 | PR-9d |
| `mcp-skill-mgr` | install_skill_from_url（1）| skill 元操作 | PR-9e |
| `mcp-candidate` | candidate/candidate_search/screening 重名合并后（5）| 候选人 CRUD + 搜索 | PR-9b + PR-9g |
| `mcp-job` | job/screening.list_jobs（3+1=4）| 职位 CRUD | PR-9b |
| `mcp-application` | application（2）| 申请流 | PR-9b |
| `mcp-interview` | interview/interview_extended/screening.get_evaluations（3+3+1=7）| 面试流 + 评估查询 | PR-9b + PR-9f |
| `mcp-evaluation` | evaluation（2，含 save 走 service 修）| 评估 | PR-9b（修 code smell）|
| `mcp-screening` | screening.screen_resume（1）| AI 简历筛选 | PR-9c |
| `mcp-knowledge` | knowledge（1）| RAG 问答 | PR-9c |
| `mcp-jd` | jd（1）| JD 生成 | PR-9c |
| `mcp-resume` | resume_parser（3，B-heavy 需事务边界）| 简历解析 | PR-9c（独立 PR）|
| `mcp-dashboard` | dashboard（1）| 看板聚合 | PR-9f |
| **合计** | **13 server / 35 工具（post-PR-9g 去重）** | — | — |

> 注意：本表是 **PR-9 完成后** 的目标态。当前（pre-PR-9g）仍是 **38 工具**（2 重名 + 1 重复登记未去）。35 = 38 - 3 dedup（PR-9g 工作）。与 §3 "34 Type B" 数字不冲突：34 是当前 B 数，35 是 post-merge 13 server 含 tool 数。

## 8. 与 macOS 资源测的对应

§7 测出 5 subprocess ≈ 438 MB。本盘点建议 13 server。

按 88MB/server 推算：13 × 88 = **1.14 GB**（**仍在 §5 2GB 预算内**）。

如果 PR-9 后真要扩到 20+ server（如远程 MCP 集成），需重测。

## 9. 下一步

1. PR-8 Day 1 起：改 host.py 接 supervisor（dual-track，§3.3）
2. PR-8 Day 2-3：pilot 2 工具 + 4 故障注入
3. PR-8 Day 4：收尾 + ship
4. PR-9a-g：按本盘点 7 阶段机械执行（每阶段 ship 后跑 §8 资源测 + §6 6 指标验证）

## 10. 附录：本盘点的方法学

- **数据源**：`apps/api/app/tools/*.py` 21 文件
- **分类标准**：handler 第一行 import 什么（DB / LLM / 外部 API）
- **不读**：业务逻辑（迁移不改变 handler 行为，只改 deployment shape）
- **CI 守门**：`scripts/check_mcp_servers.py` 现有 3 类检查外，**加一类**：重名工具检测（grep `name=` 找重复）
