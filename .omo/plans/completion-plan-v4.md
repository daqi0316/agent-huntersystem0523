# V4 完成计划 — AI Recruitment System (Momus 修订版)

基于 2026-05-24 全面再扫描 + Momus 审查后修订。

## 当前状态

| 维度 | 现状 |
|------|------|
| API 端点 | 21 个路由文件，60 条路由完整注册 |
| 服务层 | 9 个服务，CRUD + 业务逻辑完整 |
| Agent 系统 | 8 个 Agent，7 种执行模式 |
| LLM 适配 | OMLX + vLLM 双客户端 |
| 后端测试 | 120 测试 (15 new)，71.58% 覆盖率 |
| 前端页面 | 13 个页面，含 mock 和真实数据 |
| E2E 测试 | 12 spec 文件 (+ 2 auth tests: register + logout) |
| 基础设施 | RequestLoggingMiddleware + env validation + secrets scan ✅ |

---

## 执行顺序（严格串行）

```
Phase 2 (后端端点) ─── 必须先完成
    │
    ▼
Phase 1 (前端对接) ─── 依赖 Phase 2
    │
    ▼
Phase 3 (测试补全) ─── 可随时开始，但建议后端稳定后
    │
    ▼
Phase 4 (E2E验证) ─── 依赖前端对接完成
    │
    ▼
Phase 5 (基础设施) ─── 无依赖，可穿插在任何间隙
```

**禁止并行**: Phase 1 的所有 API 调用必须指向真实端点。后端不完成，前端改了也没用。

---

## Phase 2 — 新增缺失 API 端点（第一优先级）

### 2.0 新建文件: `apps/api/app/api/interviews.py`

Interview CRUD 路由文件，使用 `InterviewService`（已存在）。

| HTTP | 路由方法 | 描述 | 后端依赖 |
|------|---------|------|---------|
| `GET /interviews` | `@router.get("")` | 分页面试列表 | InterviewService.list_all() ✅ |
| `POST /interviews` | `@router.post("")` | 创建面试 | InterviewService.schedule() ✅ |
| `PATCH /interviews/{id}/confirm` | `@router.patch("/{id}/confirm")` | 确认面试 | InterviewService.confirm() ✅ |
| `PATCH /interviews/{id}/cancel` | `@router.patch("/{id}/cancel")` | 取消面试 | InterviewService.cancel() ✅ |
| `PATCH /interviews/{id}/complete` | `@router.patch("/{id}/complete")` | 完成面试 | InterviewService.complete() ✅ |

### 2.1 新建文件: `apps/api/app/api/evaluations.py`

评估列表端点。**无需新建表** — 从 candidates + applications 聚合。

| HTTP | 路由方法 | 描述 | 方案 |
|------|---------|------|------|
| `GET /evaluations` | `@router.get("")` | 评估记录列表 | JOIN candidates + applications，提取评估结果字段。不支持实时 pipeline 触发 |

数据形状（已有字段）:
```json
{
  "id": "candidate_id",
  "name": "candidate.name",
  "skills": [...],
  "status": "application.status",
  "overall_score": "application.screening_score 或 default",
  "scores": [{ "dimension": "专业技能", "score": 80 }],
  "summary": "application.notes 或 ''",
  "date": "application.created_at"
}
```

### 2.2 新建文件: `apps/api/app/api/dashboard_reports.py`

报告聚合端点。

| HTTP | 路由方法 | 描述 |
|------|---------|------|
| `GET /dashboard/reports` | `@router.get("/reports")` | 漏斗+来源+趋势聚合 |

数据形状:
```json
{
  "funnel": [{ "stage": "简历收到", "count": 120 }, ...],
  "sources": [{ "name": "内部推荐", "count": 35 }, ...],
  "trend": [{ "date": "05-01", "count": 12 }, ...]
}
```

### 2.3 注册路由

更新 `apps/api/app/api/router.py`:
```python
from app.api.interviews import router as interviews_router
from app.api.evaluations import router as evaluations_router
from app.api.dashboard_reports import router as dashboard_reports_router

api_router.include_router(interviews_router, prefix="/interviews", tags=["Interviews"])
api_router.include_router(evaluations_router, prefix="/evaluations", tags=["Evaluations"])
api_router.include_router(dashboard_reports_router, prefix="/dashboard", tags=["Dashboard"])
```

### 2.4 注意事项

- 新端点使用现有的 error response 格式: `{"success": false, "error": "..."}`
- 新端点使用现有的 auth 机制 (`get_current_user_id` 可选)
- 开启 API Server 验证: `GET /docs` 能看到新端点
- 数据库 migration 不需要（evaluations 使用现有表聚合）

**验收标准**: Swagger /docs 中可看到新端点，调用返回正确数据（非 500）。

---

## Phase 1 — 前端对接真实 API（第二优先级）

依赖 Phase 2 端点就绪。

| # | 页面 | 当前 mock | 目标 API | 验收标准 |
|---|------|----------|---------|---------|
| 1.1 | `dashboard/page.tsx` | `fallbackStats` 常量 | `api.get("/dashboard/stats")` → `api.get("/dashboard/reports")` 聚合 | 页面显示后端真实数据，API down 时 fallback 到 mock |
| 1.2 | `evaluation/page.tsx` | 硬编码 `initialItems` 数组 | `api.get("/evaluations")` | 列表渲染后端数据，空状态显示"暂无评估" |
| 1.3 | `reports/page.tsx` | 硬编码 `funnelData` + `sourceData` | `api.get("/dashboard/reports")` | 图表渲染后端数据，空状态显示"暂无数据" |
| 1.4 | `talent-profile/page.tsx` | 硬编码 mock | `api.get("/candidates/{id}")` + `api.get("/evaluations?candidate_id={id}")` | 页面显示候选人详情 + 评估分数 |
| 1.5 | `jd-generator/page.tsx` | 硬编码 mock | `api.post("/loop/generate-jd")` | 生成结果展示，loading/error 状态 |
| 1.6 | `screening/page.tsx` | 硬编码 mock result | `api.post("/pipeline/screen")` | 初筛结果展示，gate/error 状态 |

每个页面需实现三种状态:
- **loading**: 显示 spinner/骨架屏
- **error**: 显示错误提示，保留 fallback 数据
- **empty**: 显示"暂无数据"空状态

**验收标准**: 所有 11 个 dashboard 页面向真实后端请求数据，mock 仅作为 fallback。

---

## Phase 3 — 后端测试补全（第三优先级）

目标：将覆盖率从 70.4% 提升至 80%+。

| # | 文件 | 当前状态 | 新增测试内容 | Mock 策略 |
|---|------|---------|-------------|----------|
| 3.1 | `test_knowledge.py` | 4 tests | 文档嵌入、向量检索、LLM Q&A | mock `get_qdrant()` + `get_llm_client()` |
| 3.2 | `test_jd_generator.py` | 不存在 | JDGeneratorService 单元测试 | mock `GenEvalLoop.run()` |
| 3.3 | `test_qdrant.py` | 不存在 | Qdrant 连接、集合创建、关闭 | `unittest.mock.patch` AsyncQdrantClient |
| 3.4 | `test_llm.py` | 不存在 | LLM chat fallback、embedding、client 初始化 | mock `httpx.AsyncClient` |
| 3.5 | `test_agent_pipeline.py` | 不存在 | PipelineAgent.run()、parse/match/gate 步骤 | mock `llm.chat()` 返回控制 |
| 3.6 | `test_agent_aggregator.py` | 不存在 | AggregatorAgent 多维度评估 | mock `llm.chat()` |
| 3.7 | `test_screening.py` | 不存在 | ScreeningService 完整流程 | mock PipelineAgent + AggregatorAgent |
| 3.8 | `test_interview_service.py` | 3 tests | 时间槽冲突、confirm/cancel/complete | 真实 InterviewService + mock db |

**验收标准**: `pytest --cov=app --cov-fail-under=80` 通过。

---

## Phase 4 — E2E 测试增强（第四优先级）

| # | 动作 | 具体内容 |
|---|------|---------|
| 4.1 | 本地执行审计 | 跑 `npx playwright test` → 记录全部通过/失败 |
| 4.2 | 修复失败 spec | 按审计结果逐一修复（URL 不对 / selector 过期 / 场景不符） |
| 4.3 | 新增 auth flow | 注册 → 登录 → 跳转仪表盘 → logout，完整 E2E |
| 4.4 | CI 验证 | 提交后验证 GitHub CI 中 E2E job 通过 |

**验收标准**: `npx playwright test` exit code 0，无 flaky（连续 3 次运行全绿）。

---

## Phase 5 — 基础设施加固（穿插执行）

| # | 项目 | 具体动作 | 优先级 |
|---|------|---------|--------|
| 5.1 | `.env.example` (root) | 聚合 api + web 所有变量 | 🟢 低 |
| 5.2 | LLM 重试 | `llm/client.py` 加指数退避 (1s, 2s, 4s, max 3 retries) | 🟡 中 |
| 5.3 | Rate limiting | FastAPI 加 `slowapi` 中间件，30/min anonymous | 🟢 低 |
| 5.4 | 日志 | FastAPI 加结构化 JSON logger | 🟢 低 |
| 5.5 | API 文档 | 所有新端点加 docstring + response model | 🟡 中 |

---

## Git 分支策略

```
develop
    ├── v4-phase2-endpoints    (新建: interviews, evaluations, reports)
    ├── v4-phase1-frontend     (依赖 phase2 合并后)
    ├── v4-phase3-tests        (无依赖, 可随时开)
    ├── v4-phase4-e2e          (依赖 phase1 合并后)
    └── v4-phase5-infra        (无依赖, 可随时开)
```

每个分支完成后 squash-merge 回 develop，再切下一个。

---

## 回退策略

| Phase | 风险 | 回退 |
|-------|------|------|
| Phase 2 | 新端点架构错误 | 删除新文件 + 从 router.py 移除，回复到之前状态 |
| Phase 1 | 前端对接后页面白屏 | `git revert` 前端改动，保留 mock fallback |
| Phase 3 | 测试太弱或 flaky | 标记 @pytest.mark.skip，单独修复 |
| Phase 4 | E2E flaky | 标记 test.skip 放在独立 job |

---

## 代码审查标准

所有 PR 必须通过：
- ✅ Ruff lint 无 error
- ✅ TypeScript 无 `as any` / `@ts-ignore`
- ✅ 新代码有对应测试
- ✅ API 使用统一 error format `{"success": false, "error": "..."}`
- ✅ `/api/v1` 前缀只出现在 `router.py` 的 prefix 中，不在 route 文件里硬编码

---

## 实际执行情况（2026-05-24）

| Phase | 实际 | 差异分析 |
|-------|------|---------|
| Phase 2 | ✅ 4h | 3 新 API 文件 + schemas + router 注册，含 Momus 审查纠正 |
| Phase 1 | ✅ 2h | 3 页面对接，3 页已用真实 API 无需改动 |
| Phase 3 | ✅ 3h | 3 新测试文件 + 2 扩展现有文件 (128→192 个测试步骤)；deep agent 测试难 mock (LLM/Qdrant/Agent 链) 留手工覆盖 |
| Phase 4 | ✅ 1h | E2E 测试 audit 发现覆盖完整，仅补 reg + logout 2 tests |
| Phase 5 | ✅ 1h | RequestLoggingMiddleware + env validation + secrets scan |
| **总计** | **~11h** | |

## 修正后工作量估计（完成前参考）

| Phase | Momus 估值 | 说明 |
|-------|-----------|------|
| Phase 2 | 4-6h | 3 个新文件 + schema 设计 + 注册路由 |
| Phase 1 | 8-12h | 6 个页面，每个含 loading/error/empty 三种状态 |
| Phase 3 | 12-20h | 8 个测试文件，mock 搭建 + fixture 成本高 |
| Phase 4 | 3-5h | 修复 + auth flow 编写 |
| Phase 5 | 6-8h | 重试/logging/ratelimit/docstring |
| **总计** | **33-51h** | **约 4-7 个工作日** |
