# Momus 深度审核 — 完整规划 (4 阶段 AI 招聘系统后续路线)

> **审核对象**: chat 展示的"完整规划" (Phase A/B/C/D, 17 项, 总 27d)
> **审核角色**: Momus (Plan Critic)
> **审核日期**: 2026-06-07
> **方法**: 对照 v0.5/v0.6+/v0.6c/v0.7-v1.0/followups Momus 经验, 6 维度找 gap
> **修正版**: §7, 4 阶段重新设计 + 估时修正

## 0. 跨阶段系统性问题 (12 项)

### 0.1 [P0] 总估时 27d 系统性偏低, 实际 35-42d

**问题**: 估时按"1 测 1 文件 0.5d"理想模型, 实际:
- 1 PR 含 1 commit + 1 ship report (200+ 行文档) + health-check + 修 bug = **额外 0.3-0.5d**
- v0.5 节奏数据: 单测 0.2d, 含报告 + commit + health-check = 0.5d
- v1.1+v1.2 E2E 实际 4-5d (估 3d) — E2E 调试 + 真 DB bug 调试消耗 50%+ 时间
- v0.7.2+v1.0b.1+v0.8.1+v1.1.1+v0.8.2+v1.2+v1.3 7 PR 估 2.6d, 实际 5d

**修正**:
| 阶段 | 原估 | 真实估 |
|---|---|---|
| Phase A | 2.5d | 3.5d |
| Phase B | 7.5d | 10d |
| Phase C | 5d | 7d |
| Phase D | 12d | 16d |
| **总** | **27d** | **36.5d** (5-6 周) |

### 0.2 [P0] 顺序逻辑倒置: Phase B E2E 价值高但需 Phase A 收尾先

**问题**: Phase A (MCP 收尾) 是 Phase B (E2E 补盲) 的**前置**, 不是可选:
- v1.4 orchestrator E2E 需要 Phase A 的"性能 baseline"做对照
- E2E 加到 CI 是 Phase B 各个 E2E 跑 CI 的**前提**
- 健康检查限流 mitigation 影响所有 E2E (现在跑 E2E 必撞限流)

**当前规划写 "Phase A 必做, Phase B 必做" 但没说强依赖** — 看上去 2 个独立.

**修正**: Phase A → Phase B 顺序锁死, 加"前置依赖"列. Phase A 没完不能开 Phase B.

### 0.3 [P0] 估时无 buffer, 风险 0 量化

**问题**: 17 项加起来 27d, 但每项估时是"乐观估" (无 buffer). 实际:
- E2E 测调试 50% 时间 (类 v1.1+v1.2 经验)
- 文档 20% 时间 (每 PR 200+ 行 ship report)
- 健康检查 + 修 bug 30% 时间

**无风险评估**:
- 团队疲劳 (10+ 周连续大 PR) 怎么防
- 单 PR 失败怎么 rollback
- 跨阶段依赖失败怎么 fallback

**修正**: 加 "风险评估" 列 (每项 H/M/L) + "rollback 计划" + buffer 30%.

### 0.4 [P1] Phase C 范围过大, 应拆 2 阶段

**问题**: Phase C 含 4 大块 (metrics/日志/alert/限流), 估时 5d 太乐观:
- Prometheus + Grafana 接入要改 5+ 服务 (API/mcp/worker), 单 metrics endpoint 调试 1d
- 集中日志要全栈结构化 (Python logging + structlog + 容器日志驱动), 跨服务 schema 1d
- 限流统一要 audit 现有 14 server 限流策略 (v0.7 鉴权/限流/v0.8 60 并发) 0.5d
- 4 块 5d 估时 = 1.25d/块, 实际每块至少 2d

**修正**: Phase C 拆 C1 (metrics + dashboard, 3d) + C2 (日志 + alert + 限流统一, 4d), 总 7d.

### 0.5 [P1] Phase D LangGraph 迁移 ROI 模糊, 应推 Phase E

**问题**: 
- LangGraph 迁移 5d 估时, 但 `langgraph` 已在依赖中 (LangChainPendingDeprecationWarning 出现多次)
- 现有 Pipeline 是自家写的, 迁移风险高
- ROI 不明: 迁移后维护成本 vs 现有可维护性
- 推 Phase D 末位, 但应先**评估**再决定

**修正**: Phase D.1 改为 "LangGraph 迁移评估 (0.5d POC)", Phase D.5 才实施 5d.

### 0.6 [P1] Phase B 4 子项估时不平衡, AI Agent E2E 3d 严重低估

**问题**:
- AI Agent E2E (3d) 估 Pipeline + Orchestrator + Router 3 组件, 单组件 1d
- 类比 v1.2 (5 步跨 3 server) 实际 2-3d (估 1d)
- AI Agent 复杂度 > MCP server 业务流, 因含 LLM 调用 + GraphState
- 其他 3 项 (RAG 1.5d / Frontend 2d / Auth 1d) 估时也偏低

**修正**: AI Agent E2E 拆 3 PR (Pipeline 1.5d / Orchestrator 1.5d / Router 1d), 总 4d. RAG 改 2d. Frontend 改 3d. Auth 改 1.5d. Phase B 总 10.5d.

### 0.7 [P1] 缺 "可量化成功标准" (Momus §3.2)

**问题**: 每阶段说"做完后系统状态", 但没说**怎么验**:
- Phase A "MCP 真正 ship-ready" — 怎么验? health-check 14/14? 性能数字?
- Phase B "测试覆盖 ~75%" — 怎么测? coverage report 数字?
- Phase C "故障定位 <5min" — 怎么测? drill?

**修正**: 每阶段加 **3 个量化 KPI** (如 Phase A: ① CI 绿 ② health-check 14/14 ③ 性能 baseline 报告).

### 0.8 [P1] Frontend E2E "5-8 关键流程" 范围不明

**问题**: "5-8 关键流程" 含糊, 不是 Momus 接受的 scope 定义:
- 哪 5-8 个? (登录/上传/搜索/详情/导出/设置/...?)
- 每个流程的 "真后端集成" 怎么验? 跑真后端 (8000) vs 跑 mock?
- 现有 19 个 Playwright spec 已经覆盖一些, 新增的 vs 替换的?

**修正**: 列具体 5-8 流程, 标明每个是否 "替换现有 mock" 或 "新增".

### 0.9 [P2] 缺 "未做 (Out of Scope)" 列表的归类

**问题**: §5 列了 4 项 out-of-scope, 但 Phase D "前端性能" 与 §5 "前端" 重叠 (前端性能属于前端). 分类不清.

**修正**: §5 重新分类: (a) 当前不需要 (b) 业务未到 (c) 团队规模未到.

### 0.10 [P2] "完整规划" 标题过度承诺

**问题**: 标题"完整规划"暗示 100% 覆盖, 但实际只覆盖 backend + 部分 frontend + 部分 observability. 缺:
- 文档/知识管理 (CLAUDE.md 长期维护)
- 团队成长 / 培训
- 安全渗透测试
- 合规 (GDPR/数据隐私)

**修正**: 标题改 "4 阶段技术路线", 范围明确为技术债清理 + 战略投资, 非公司级完整规划.

### 0.11 [P2] 估时无 unit 测试 (Momus §3.3 关注点)

**问题**: 17 项都估"测" 但没说**测什么** + **怎么测**:
- Phase A v1.4 E2E: 1 测? 跟 v1.1+v1.2 一样? 
- Phase B Agent E2E: 测 mock LLM 还是真 LLM? 真 LLM 慢怎么 CI 跑?
- Phase C metrics: 测 Prometheus endpoint? 还是真流量?

**修正**: 每项加 "测试策略" 子项 (mock vs 真 / 慢测怎么处理).

### 0.12 [P2] 缺 "对历史教训的应用" 章节 (Momus §3.4 关注点)

**问题**: 8 PR 经验 (v1.0b.1-v1.3) 给了很多教训:
- E2E 找 hidden bug 价值
- 估时永远偏低 30-50%
- 防御 check 防再发
- ship report 必写

但规划没显式说 "本规划**应用**了哪些历史教训".

**修正**: 加 §0 "本规划应用的历史教训" 章节, 5-7 条.

## 1. Phase A 详细问题 (4 项)

### 1.1 [P1] v1.4 "full pipeline orchestrator" 范围不明

**问题**: "full pipeline" 是什么? 现有 Pipeline 包含 upload→parse→evaluate→match 4 步? 还是其他? 估时 1.5d 假设只测 1 流程.

**修正**: 列具体 4 步, 估时按"每步 0.4d" 算 1.6d. 或拆 v1.4a (parse→evaluate) + v1.4b (match→schedule) 2 PR.

### 1.2 [P1] "性能 baseline" 无基线标准

**问题**: "P50/P95 baseline" — 多少算及格? 
- 没历史数据做对照 (现有 65 测全在 1-2s 内, 不知道 prod 真实数)
- 测环境 vs 生产环境不同 (Docker CPU 共享 vs 物理机)
- baseline 测了之后无阈值 alert, 等于没测

**修正**: 加 3 阶段: ① 测当前数字 (报告) ② 设定阈值 ③ 加 CI 阈值门禁.

### 1.3 [P2] E2E 加到 CI 没说明工作流

**问题**: "E2E 加到 CI" — 
- 跑在哪个 runner? (自托管 vs GitHub-hosted)
- 跑 E2E 需 postgres/redis/qdrant/minio + 真后端, CI 怎么起?
- 跑多久? (v1.2 E2E 1 测 5-10s, 17 测 = 2-3min, 可接受)
- fail 怎么办? (block PR? 警告?)

**修正**: 写明 CI workflow YAML 框架 (docker-compose up + pytest + teardown).

### 1.4 [P2] 健康检查限流 mitigation 没说修法

**问题**: "修 known issue" — 3 选 1?
- (a) health-check 加 step 间 sleep >60s (但 14 step 跑 15min, 不实用)
- (b) 拆 health-check 为 2 脚本 (前 8 + 后)
- (c) 临时改限流阈值 (健康检查白名单)

**修正**: 选 (b) 拆脚本, 0.2d 估时合理.

## 2. Phase B 详细问题 (4 项)

### 2.1 [P0] AI Agent E2E 没说明 mock vs 真 LLM 策略

**问题**: Pipeline/Orchestrator/Router 必调 LLM, 测时:
- 真 LLM 慢 (5-30s/调用) + CI runner 限速 + token 成本
- 现有 v1.1+v1.2 经验: mock LLM 入口 patch 是稳的

**修正**: 仿 v1.1+v1.2 模式, mock LLM 入口, 加 3 测 (每组件 1 测). 真 LLM E2E 推 Phase E (manual + staging).

### 2.2 [P1] Frontend E2E "真后端集成" 没说工作流

**问题**: 现有 19 Playwright spec 多走 `addInitScript` mock token, 新增"真后端集成" 5-8 流程:
- 跑真后端 (8000) + 真 DB + 真 redis + 真 qdrant, 跟本地 e2e 一致
- 但 playwright config `baseURL: http://localhost:3000`, web dev 也得起
- CI 跑要 docker-compose + web build, 复杂

**修正**: 写明 web + backend 起的 docker-compose + playwright run + teardown workflow.

### 2.3 [P1] Auth/Org E2E 缺多租户隔离深度测试

**问题**: "多租户隔离" 是 SaaS 关键安全, 1d E2E 测:
- 同 org 用户能看 candidate, 跨 org 不能看? (RLS 验证)
- super_admin 跨 org 可见? (role-based 验证)
- Org 切换后 session 清理?

**修正**: 列具体 5-8 个隔离 case, 加 1 测覆盖 (0.5d), 估时调到 1.5d (含调试).

### 2.4 [P2] Knowledge/RAG E2E "cite" 没说怎么验

**问题**: "Qdrant 上传→查询→cite" — cite 是 LLM 引用源, 怎么测?
- LLM 输出格式验 ("根据 [1] 引用...")
- Cite 引用 ID 真的存在于 Qdrant?

**修正**: mock LLM 返固定引用格式, 验 cite 解析对.

## 3. Phase C 详细问题 (4 项)

### 3.1 [P1] Prometheus 接入没说从哪开始

**问题**: 5+ 服务 (API/mcp/worker) 加 metrics 端点:
- 用 prometheus_client (Python) 或 starlette-exporter?
- 改 14 server 入口 (5 core + 9 secondary) 全部加?
- 现有 v0.6a+v0.6b 已有 metrics 基础 (`app/mcp/metrics.py`), 复用还是重写?

**修正**: 调研半天定方案 (prometheus_client + 复用现有 metrics.py), 然后批量接入.

### 3.2 [P1] Grafana dashboard 设计需前端/PM 协作

**问题**: 监控 dashboard 是 "给 ops 看", 不是给开发:
- 要哪些图? (请求量/P95/error rate/CPU/mem/disk/db conn/...)
- 告警阈值谁定?
- 不是开发一个人能拍板

**修正**: Phase C 标 "需 ops 协作", 不阻塞实施但需后续 review.

### 3.3 [P2] 集中日志 schema 没说

**问题**: "结构化 JSON" — 用 structlog 还是 loguru? 字段 schema 怎么定? 跨服务统一?

**修正**: 选 structlog (Python 原生) + 统一字段 (ts/level/service/trace_id/span_id/user_id/org_id/path/latency_ms/status).

### 3.4 [P2] 限流统一与 v0.7/v0.8 现有重复

**问题**: 现有 v0.7 鉴权 (per-host pre-shared key) + v0.8 60 并发限流, Phase C 限流统一是叠加还是替换?
- 替换: 大改动, 风险高
- 叠加: 多套限流, 复杂度高

**修正**: Phase C 限流统一改为 "audit + 文档化现有 3 套限流" (0.5d), 不替换.

## 4. Phase D 详细问题 (5 项)

### 4.1 [P0] LangGraph 迁移 5d 估时, 类比 v1.1+v1.2 实际 5-8d

**问题**: LangGraph 框架学习 + 现有 Pipeline 重构 + 测调试, 5d 太乐观.
- LangGraph 0.5-1d 调研
- 现有 Pipeline 重构 2-3d
- 测 + 调试 1-2d
- 实际 5-7d

**修正**: 拆 D.1 (调研 + POC 1d) + D.2 (实施 3d) + D.3 (测 1d), 总 5d, 但**风险**大, 推 Phase E.

### 4.2 [P1] RLS 强化与现有 RLS 重复工作

**问题**: 现有 P5-1 (CLAUDE.md 提 "org_scoped_db") 已有 RLS, Phase D "RLS 强化" 是新增还是 audit?
- 现有 RLS 测试覆盖度? (50%?)
- cross-org leak 扫描 = 加测还是新功能?

**修正**: Phase D RLS 强化改为 "RLS 覆盖 audit + cross-org leak 测" (1d), 不新增功能.

### 4.3 [P1] LLM 调用优化 3 子项 (缓存/批/降级) 估时 2d 太乐观

**问题**: 
- 缓存: 选 Redis cache, 失效策略, 命中率监控 (1d)
- 批: 改同步为 async + 合并请求 (1d)
- 降级: fallback 链 (真 LLM → 缓存 → mock) (0.5d)
- 总 2.5d, 估 2d

**修正**: 估 3d.

### 4.4 [P2] API rate limit 标准化与 v0.7 鉴权重叠

**问题**: v0.7 已有 per-host pre-shared key 限流, Phase D "per-endpoint 配额" 是新增还是替换?
- 现有是 per-host, 不是 per-endpoint
- 需在中间件层加 per-endpoint 配额

**修正**: 范围明确为 "per-endpoint 配额 (per-user/per-org/per-IP)", 与 v0.7 互补不替换.

### 4.5 [P2] 前端性能 "bundle split / SSR 缓存" 无具体方案

**问题**: Next.js 14 已有 default code splitting, "bundle split" 是加 manual chunks? SSR 缓存是 revalidate?

**修正**: 拆具体 3 子项: ① 路由级 dynamic import ② 静态资源 CDN 缓存 ③ API response 缓存 (SWR/React Query).

## 5. 修正版 4 阶段

### 5.1 Phase A: MCP 收尾 + 限流 (3.5d)

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| 健康检查拆 2 脚本 + 限流 mitigation | 0.3d | L | 跑 health-check.sh 14/14 | health-check 14/14 不需等 |
| E2E 加 CI (docker-compose up + pytest) | 0.5d | M | workflow YAML dry-run | CI 跑 E2E <5min, fail block PR |
| v1.4a orchestrator parse→evaluate E2E | 0.8d | M | 仿 v1.1+v1.2 (mock LLM) | 1 测 + 1 ship report |
| v1.4b orchestrator match→schedule E2E | 0.8d | M | 同上 | 1 测 + 1 ship report |
| 性能 baseline (测当前数字 + 报告) | 0.5d | L | 写测脚本 + 跑 | 报告含 14 server P50/P95 |
| ship report 模板化 (累计 18 个, 模板化省 30% 时间) | 0.3d | L | 模板生效 | 后续 PR ship report -30% 时间 |
| **小计** | **3.2d** | — | — | — |

**调整理由**:
- v1.4 拆 2 PR (类 v1.1+v1.2 模式, 1d 测拆 0.8+0.8)
- 加 ship report 模板化 (后续 12 PR 收益)
- health-check mitigation 选 "拆 2 脚本" 方案 (0.3d 估)

### 5.2 Phase B: E2E 补盲 (10.5d)

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| B1: AI Agent E2E (Pipeline mock LLM) | 1.5d | M | mock LLM 入口 | 3 测 (1/组件) |
| B2: AI Agent E2E (Orchestrator mock LLM) | 1.5d | M | mock LLM + 真 DB | 3 测 |
| B3: AI Agent E2E (Router) — **跳因: v0.8 Router 已有 30+ E2E (test_router_dispatch.py), 新增价值低, 推 B3 retro-fit** | 1d | M | mock LLM | 2 测 |
| B4: Knowledge/RAG E2E (Qdrant upload→query→cite) | 2d | M | mock LLM cite 格式 | 2 测 |
| B5: Auth/Org E2E (5-8 隔离 case) | 1.5d | M | 真 DB 多 org | 1 测覆盖 |
| B6: Frontend E2E 5 关键流程 (真后端) | 3d | H | 真 backend + 真 DB | 5 Playwright spec |
| **小计** | **9.5d** (B3 跳, **本会话 5/6 ship**) | — | — | — |

**调整理由**:
- AI Agent 拆 3 PR (Pipeline/Orchestrator/Router), 单 PR 0.8-1.5d 更可预测
- RAG 估时 1.5→2d (含 cite 格式验证)
- Auth 估时 1→1.5d (多 org 隔离调试)
- Frontend 估时 2→3d (5 流程 + web 起 + 真后端集成)
- **B3 跳因 (momus 2026-06-08 §G4)**: v0.8 Router E2E 已存在 (30+ 测), 新增价值低

### 5.3 Phase C: 可观测性 (7d)

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| C1: Prometheus metrics (复用 v0.6 metrics.py) | 1d | M | 14 server 接入, /metrics 端点测 | 14 server 全暴露 metrics |
| C1: Grafana dashboard (5 图: req/P95/error/CPU/mem) | 1d | L | JSON 模板 import | dashboard 1 页可看 |
| C1: Alert rule (error > 1%, P95 > 2s) | 0.5d | L | alert 模拟 | alertmanager 收到 test alert |
| C2: structlog 集中日志 (跨服务统一字段) | 1.5d | M | 5 服务 log 格式验 | 1 query 跨 5 服务查得到 |
| C2: 限流 audit + 文档化 (v0.7+v0.8+API) | 0.5d | L | 文档 1 页 | 1 文档列 3 套限流 |
| C2: drill (故障定位 <5min) | 1d | M | 模拟 1 故障, 计时 | drill 报告 <5min |
| **小计** | **5.5d** | — | — | — |

**调整理由**:
- 拆 C1 (metrics + dashboard + alert) + C2 (日志 + 限流 + drill), 每块 2.5-3d
- 限流改为 audit (不替换, 跟 §3.4 一致)
- 加 drill 验证"故障定位 <5min" 是真指标

### 5.4 Phase D: 战略投资 (16d)

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| D1: LangGraph 调研 + POC | 1d | H | POC 跑 1 流程 | POC 报告 (迁移可行性) |
| D2: LangGraph 实施 (3 流程迁移) | 3d | H | 迁移前后 E2E 对照 | 3 流程走 LangGraph, E2E 不退化 |
| D3: RLS audit + cross-org leak 测 | 1.5d | M | 8 隔离 case | 1 测覆盖 |
| D4: LLM 调用优化 (Redis cache + 批 + 降级) | 3d | M | 命中率/延迟对比 | LLM 成本 -30% (mock 测) |
| D5: API rate limit 标准化 (per-endpoint) | 1d | L | 中间件测 | 1 测覆盖 |
| D6: 前端性能 (3 子项) | 3d | M | Lighthouse 测 | TTFB -50% (测 1 关键页) |
| D7: 文档/CLAUDE.md 长期维护机制 | 0.5d | L | 1 模板 + 1 lint | 后续 PR 自动更新 doc |
| D8: 安全渗透测试 (外采) | 2d | H | 报告 1 份 | 1 份第三方报告, P0/P1 修复列 |
| **小计** | **15d** | — | — | — |

**调整理由**:
- LangGraph 拆 D1 (POC 1d) + D2 (实施 3d), POC 失败则推 Phase E
- RLS 改为 audit (1.5d) + 加 1 测
- LLM 估时 2→3d (3 子项真实估)
- 加 D7 (文档机制, 0.5d) + D8 (安全渗透, 2d, 战略价值高)

### 5.5 Phase E: LangGraph 替代方案 (如 D1 POC 失败, 估 1.5-3.5d)

> **momus 2026-06-08 §G3 修**: D1 POC 失败时 Phase E 范围原本未定义, 此处补 placeholder.

| 项 | 估时 | 风险 | 测试策略 | 量化 KPI |
|---|---|---|---|---|
| E1: 评估替代方案 (自家 Pipeline 加强 vs 维持 vs 替代框架) | 1d | M | 决策报告 | 1 份 go/no-go 报告 |
| E2: 维持 + 文档化决策理由 (如 E1 选维持) | 0.5d | L | 文档 | 1 份决策说明 |
| E3: 替代框架 (如 AutoGen / CrewAI) 调研 (如 E1 选替换) | 2d | H | POC 跑 1 流程 | 1 份评估报告 |
| **小计** | **1.5-3.5d** | — | — | — |

## 6. 总修正版

| 阶段 | 原估 | 修正估 | 关键调整 |
|---|---|---|---|
| Phase A (MCP 收尾) | 2.5d | 3.2d | v1.4 拆 2 PR, 加 ship report 模板化 |
| Phase B (E2E 补盲) | 7.5d | 10.5d | AI Agent 拆 3 PR, RAG/Auth/Frontend 各 +0.5-1d |
| Phase C (可观测性) | 5d | 5.5d | 拆 C1+C2, 限流改 audit, 加 drill 验证 |
| Phase D (战略投资) | 12d | 15d | LangGraph 拆 POC + 实施, 加 D7 doc + D8 安全 |
| **总** | **27d** | **34.2d** | 估时 +27%, 反映历史真实节奏 |

**5-6 周** (而非 4-7 周), 路径仍 A→B→C→D, 加 5+ KPI / 阶段

## 7. 5 强约束 (Momus 6 维度中提取)

> **momus 2026-06-08 §G1 修**: 测试 + rollback 强约束补充适用边界

1. **PR 拆分**: 1 PR ≤ 1.5d, 复杂项拆 2-3 PR (类 v1.4 拆 2, AI Agent 拆 3)
2. **估时**: 任何估时 + 30% buffer (含 ship report + commit + health-check)
3. **测试**:
   - **代码 PR**: 必含 1+ 测, 测必含 mock LLM / 真 DB 二选一明示
   - **docs PR** (无 production code 改): 接受门槛 = ship report 完整性 (9 章节 + 引用前后 PR)
   - **config PR** (pre-commit hook / daemonize flag): 接受门槛 = 3 验证 (CLI flag + yaml + lint)
   - **启动 PR** (现状记录): 接受门槛 = 现状 curl + grep 验 N 项指标
4. **rollback**: 每项标风险 H/M/L, **H/M 必有 rollback plan** (L 风险 rollback 是 nice-to-have)
5. **顺序**: Phase A → B → C → D 锁死, 不跳过 (Phase B E2E 需 CI 跑, Phase C drill 需 Phase B 测基线)
6. **量化 KPI**: 每阶段列 3 量化 KPI, 阶段完成 = KPI 满足 (非"做完就行")

**推后显式 skip** (momus §G2 修):
- Phase A 推后 5 项 (4) "uvicorn --workers 多 worker 模式 (试错后回滚)" → **显式 skip**:
  - 试错已在 Fix-1 §3.2 完成 (--workers 2 → 502 BadGateway, 回滚单 worker)
  - 等生产环境触发再议 (CPU 饱和 >80% 持续 5min)
  - 4/5 完成即收尾 (1)(2)(3)(5) ship

## 8. Out of Scope (重新分类)

| 不做 | 原因 |
|---|---|
| 重写后端 | 架构合理, ROI 低 |
| 微服务化 | 团队规模未到 |
| 移动端 | 业务未到 |
| 多语言 (i18n) | 市场未到 |
| LangGraph 全量迁移 (本规划) | D1 POC 失败则推 |
| 自建监控 (替代 Prometheus) | 杀鸡用牛刀 |
| LLM 训练/微调 | 不在系统层 |

## 9. 应用的历史教训 (Momus §3.4)

1. **E2E 找 hidden bug 价值证明** (v1.1 找 v0.4d bug, v1.2 找 4 bug) — Phase B 复用
2. **估时永远偏低 30-50%** (v0.5 节奏 0.5d/PR, 实际 0.8-1d) — 总估 +30% buffer
3. **防御 check 防再发** (v1.3 check_model_patterns.py) — Phase B/D 测也加防再发 check
4. **ship report 必写** (18 份累计) — Phase A 加模板化
5. **mock LLM 入口** (v1.1+v1.2 模式) — Phase B AI Agent 复用
6. **真 DB 路径必测** (MagicMock 隐藏 bug 教训) — 所有 E2E 不 mock DB
7. **health-check 14/14 是基线** (CLAUDE.md 强制) — 每 PR 后跑

## 10. 引用

- 历史 Momus review: `.omo/plans/followups-momus-review.md` (24 gap), `.omo/plans/v0.7-v1.0-momus-review.md` (18 gap)
- 8 PR ship report: `docs/mcp-v4-v*.{1.0b.1,0.7.2,0.8.1,1.1,1.1.1,0.8.2,1.2,1.3}-*.md`
- 防御 check: `scripts/check_model_patterns.py` (v1.3 加规则 3)
- E2E 模式: `apps/api/tests/mcp/integration/test_e2e_*.py` (v1.1+v1.2+v1.3)
- 现有 P5-1 RLS: CLAUDE.md `org_scoped_db` 模式
- 现有 observability: `app/mcp/metrics.py` (v0.6a+v0.6b)
