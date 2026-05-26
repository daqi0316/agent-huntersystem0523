# AI 招聘系统 — 100% 完成度总规划

> 基于 2026-05-26 全量代码扫描 + 现有 V4/V5 成果
> 现状：476 tests ✅, 85% 覆盖率, 67 业务 API 路由, 12 前端页面, 12 E2E spec
> 目标：100% 功能完成度 + 生产就绪
> Momus 审查：v2（已修复 14 项问题）

---

## "100% 完成度"量化定义

| 维度 | 100% 标准 | 当前 | 差距 |
|:---|:---|:---:|:---:|
| **功能覆盖** | PRD v2.2 全部功能点已实现，无 stub | ~95% | RouterAgent/Settings/Parallel 已修复 |
| **测试覆盖** | 行覆盖率 ≥ 88%，每个模块 ≥ 70%，0 失败，0 warning | 85%/544uc/4fail/8warn | 3% + 4 failures + 8 warnings |
| **前端完备** | 12 页全部三态完备（具体标准见 C1），无硬编码 mock | ~6/12 | 6 页缺状态 |
| **基础设施** | CI 全绿 + 文档完整 + 日志规范化 + RBAC 可用 | ~75% | 缺日志/RBAC/文档 |

---

## 当前完成度评分

| 维度 | 完成度 | 说明 |
|:---|:---:|:---|
| **A. 后端 API** | 95% | 67 业务路由全部注册，RouterAgent/Settings/Parallel 等原 stub 已修复 |
| **B. Agent 系统** | 90% | 8 个 Agent 完整，Skill 提取器未落地 |
| **C. 测试覆盖** | 85% | 行覆盖率 85%，但 agent_service / qdrant / resume 等 < 60% |
| **D. 前端页面** | 85% | 12 页全连接真实 API，mock 有 fallback，三态完备性待审计 |
| **E. E2E 测试** | 80% | 12 spec 存在，4 个 CI 失败待修，auth 仅 2 场景 |
| **F. 基础设施** | 75% | CI/CD, Docker, 限流, 日志 ✅; 文档, RBAC ❌ |
| **平均** | **85%** | |

---

## 六大领域

```
A. 测试攻坚 ─── 最高优先级，85% → 88%+
   │
B. 后端补全 ─── 修复低频代码路径 + 错误格式统一
   │
C. 前端对齐 ─── loading/error/empty 三态 + mock 清理
   │
D. E2E 强化 ─── 修复 4 失败 + 增加异常场景 + 可靠化
   │
E. 生产就绪 ─── 日志/监控/文档/RBAC（错误格式随 RBAC 一起统一）
   │
F. 差异化功能 ─── Skill 提取器 / 跨会话记忆 UI / 主动推荐
```

---

## Phase A: 测试攻坚

> 时长：6-10h
> 并行策略：A1-A5 并行 → A6 串行在最后

### A1. 补齐低频模块测试（并行，6 个子任务）

| 模块 | 当前覆盖 | 目标 | 策略 | 超时回退 |
|:---|:---:|:---:|:---|:---|
| `agent_service.py` | ~40% (541 uncovered) | 75% | mock LLM + DB session，测 execute_conversation() 主路径 | 标记 `@pytest.mark.integration` |
| `qdrant_service.py` | ~50% | 80% | mock AsyncQdrantClient | 缩小到 upsert/search 路径 |
| `resume_extractor.py` | ~35% | 75% | mock LLM chat | 只测结构化提取主路径 |
| `resume_parser.py` | ~50% | 80% | PDF/DOCX/TXT 三种格式 | 跳过 PDF（依赖外部库）|
| `installer.py` | ~70% | 90% | skill 目录写入 | 1 个冒烟测试即可 |
| `knowledge.py` | ~55% | 80% | 嵌入+检索+QA | 跳过 Qdrant 依赖路径 |

> **回退规则**：任意子任务超过 1.5h → 缩小范围到"主路径覆盖"— 不阻塞整体进度。

### A2. ResourceWarning 修复

`test_pipeline_flow.py` 中的 8 个 `ResourceWarning: unclosed transport` 源于 Starlette 的 `BaseHTTPMiddleware`（Starlette #1334，已知 issue）。修复方案：

将 `main.py` 中的 `RequestLoggingMiddleware(BaseHTTPMiddleware)` 和 `RateLimitMiddleware(BaseHTTPMiddleware)` 改为 `@app.middleware("http")` 装饰器模式。这是一个重构，改动集中在 `main.py` + `rate_limit.py`，不涉及业务逻辑。

### A3. 修复 4 个预存测试失败

先定性：查明 `test_pipeline_api.py` 中 4 个 `assert 400 == 200` 的原因。
- 如果端点正确（输入校验返回 400 合理）→ 改测试断言（5 分钟）
- 如果端点行为不符合预期 → 修端点逻辑 + 测试（30 分钟）

**验收**：`pytest tests/ --ignore=tests/test_knowledge.py` Docker 无关的测试全部通过。

### A4. API 路由边缘覆盖

| 路由文件 | 未覆盖行 | 建议测试 | 估算 |
|:---|:---|:---|:---:|
| `resume.py:99-141` | 43 行 | upload + extract + confirm | 20min |
| `memory.py:161-163` | 3 行 | delete 不存在 key | 5min |
| `interviews.py:97` | 1 行 | get 不存在 interview | 5min |
| `dashboard.py:143-147` | 5 行 | stats 空数据 | 5min |
| `summaries.py:68-74` | 7 行 | delete 不存在 summary | 5min |

### A5. 现有测试扩展

- `test_knowledge.py` 扩展知识库嵌入 + 搜索 E2E
- `test_retrieval.py` 扩展向量检索 + 嵌入边界

### A6. 覆盖率门禁提升（串行在最后）

**在每个 A1-A5 子任务完成后都跑一次覆盖**，渐进式记录：

```
基线: 85%
A1 agent_service 完成 → ?
A1 qdrant 完成 → ?
A1 resume 完成 → ?
A2 ResourceWarning 修复 → ?
A3 修复 4 failures → ?
A4 路由边缘 → ?
A5 知识扩展 → ?
最终: target ≥ 88%
```

`--cov-fail-under` 从 80% → **88%**。若不可达，90% 为 stretch goal，不阻塞其他 Phase。

**退出检查**：
- [ ] `pytest` 全部 480+ 测试通过（Docker 无关）
- [ ] `pytest --cov=app --cov-fail-under=88` 通过
- [ ] 0 ResourceWarning
- [ ] `lsp_diagnostics` 后端无 error
- [ ] `pnpm build` 前端通过

---

## Phase B: 后端补全

> 时长：2-3h
> 并行策略：B1+B2+B3+B4 可并行（E5 RBAC 实现时直接用统一错误格式，不阻塞等 B2）

### B1. 剩余 stub 确认

所有原 V4 计划的 stub 已修复：
- [x] ReportService → 完整
- [x] InterviewService → 完整
- [x] `/parallel/data-aggregate` → 完整
- [x] `/human-loop/stop` → 完整
- [x] Application CRUD → 完整
- [x] RouterAgent → 完整
- [x] Settings API → 完整

确认 `orchestrator_agent.py:164-167`、`interview.py:162-167` 的剩余线已有测试覆盖。

### B2. 统一错误响应格式

扫描所有 route 文件验证 `{success, data/error}` 格式。已知问题：
- `memory.py` 用 `{success: true}` 无 data 字段
- `human_loop.py` 部分返回无 success 字段

### B3. Settings 前端验证

`settings/page.tsx` 端口 8001→8000 已修复。验证全部 CRUD 走通。

### B4. RabbitMQ 清理（可选）

`config.py` 中 `rabbitmq_url` 和 docker-compose 中的 `rabbitmq` 服务在代码中无任何引用。确认后移除。

**退出检查**：
- [ ] 所有路由返回格式统一（`{success, data/error}`）
- [ ] Settings CRUD 前端可用
- [ ] `pnpm build` 通过

---

## Phase C: 前端三态审计

> 时长：3-5h
> 并行策略：C1→C2+C3 串行（C1 审计先行）

### C1. 全页面三态审计（先审计，再修复）

**三态标准定义**：

| 状态 | 视觉要求 | 功能要求 |
|:---|:---|:---|
| **loading** | Skeleton 组件（非 spinner）| 无闪烁，骨架屏尺寸匹配内容 |
| **error** | 错误图标 + 描述 + 按钮 | 重试按钮有效，已有数据不丢失 |
| **empty** | 空状态插画 + 文案 | 操作引导/CTA（如"创建第一个候选人"） |

逐页审计：

| 页面 | loading | error | empty | mock fallback | 修复量 |
|:---|:---:|:---:|:---:|:---:|:---:|
| dashboard | ? | ? | ? | ✅ | 中 |
| candidates | ✅ | ✅ | ✅ | ✅ | — |
| jobs | ✅ | ✅ | ✅ | ✅ | — |
| evaluation | ✅ | ? | ? | ✅ (200行mock) | 大 |
| interview | ? | ? | ? | ? | 中 |
| screening | ? | ? | ✅ | ✅ | 小 |
| jd-generator | ✅ | ✅ | ? | ✅ | 小 |
| reports | ✅ | ✅ | ✅ | ✅ | — |
| talent-profile | ? | ? | ? | ✅ | 中 |
| settings | ✅ | ✅ | ? | ✅ | 小 |
| knowledge | ✅ | ✅ | ✅ | ✅ | — |
| agent | ? | ? | ? | ? | 中 |

### C2. Mock 数据清理

`evaluation/page.tsx` 中约 200 行硬编码 `mockEvaluations`。改为 API 不可用时 fallback 显示 + `isMock` 标识。

### C3. API 类型对齐

前端 `EvalApiResponse` 等接口与后端 schema 逐项匹配。让 TypeScript 类型成为后端 response_model 的忠实映射。

**退出检查**：
- [ ] 12 页全部满足三态标准定义（见 C1 表格）
- [ ] 无硬编码 mock 数据（所有 mock 改 fallback）
- [ ] 前端类型定义与后端 schema 一致
- [ ] `pnpm build` 通过

---

## Phase D: E2E 强化

> 时长：3-4h
> 并行策略：D1→D2+D3+D4 串行（D1 先行）

### D1. 修复 4 个失败测试

`test_pipeline_api.py` 中 `assert 400 == 200`。先查明端点返回 400 的原因：
- 如果端点输入校验返回 400 是合理行为 → 改测试断言
- 如果端点应该返回 200 → 修端点代码 + 测试

### D2. 新增异常场景 E2E

| 场景 | 文件 | 新测试数 |
|:---|:---|:---:|
| 注册→登录→创建候选人→创建职位 | `auth.spec.ts` | +2 |
| 上传简历→初筛→查看报告 | `screening.spec.ts` | +1 |
| API 不可用时 mock fallback | 新建 `offline.spec.ts` | +2 |
| 空数据列表 | 各 spec 扩展 | +3 |

### D3. E2E 可靠化

- `data-testid` 属性标记所有可交互元素（按钮、输入框、列表项）
- wait 策略从 `page.waitForTimeout` 改为 `page.waitForSelector`
- CI 中串行执行（`workers: 1`）

### D4. Playwright 配置升级

```ts
// playwright.config.ts
fullyParallel: false,   // 串行避免状态污染
retries: 2,             // flaky 自动重试
workers: 1,             // 单 worker
```

**退出检查**：
- [ ] `npx playwright test` exit code 0（连续 2 次运行）
- [ ] 新增 ≥ 8 个异常场景测试
- [ ] 所有可交互元素有 `data-testid`
- [ ] `pnpm build` 通过

---

## Phase E: 生产就绪

> 时长：4-6h
> 并行策略：E1-E5 全部并行

### E1. 结构化 JSON 日志

选择 **`python-json-logger`**（最小侵入，只换 format 不改代码，不需要改所有 `logger.info()` 调用）。

```python
# logging 配置替换
from pythonjsonlogger import jsonlogger
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
))
```

### E2. 健康检查增强

`GET /health` 从 `{"status": "ok"}` 增强为：

```json
{
  "status": "ok",
  "version": "2.0.0",
  "checks": {
    "database": "connected",
    "redis": "connected",
    "qdrant": "connected",
    "llm": "available"
  },
  "uptime_seconds": 3600
}
```

已有 `GET /metrics` 端点的 `redis_connected` 检查，复用逻辑。

### E3. 文档补全

| 文档 | 目标 | 估算 |
|:---|:---|:---:|
| Swagger summary + response_model | 所有端点有描述 + 返回类型 | 30min |
| README 更新 | 当前架构 + API 概览 + 测试说明 | 20min |
| `CONTRIBUTING.md` | 环境搭建 + 开发流程 + PR 规范 | 20min |
| `CHANGELOG.md` | v1→v2→v3→v4→v5 变更记录 | 15min |

### E4. 环境变量治理

- `.env.example` 合并 api + web 所有变量
- CI 变量去重，抽取到 `env:` 级别（当前在 4 个 job 中重复定义）
- pydantic `Settings` 中缺失关键变量的运行时校验

### E5. RBAC 基础

User 表加 `role` 字段，需要新 Alembic migration。**默认值决策**：现有用户默认 `"hr"`（最常用角色，不影响现有功能）。

| 角色 | 权限 |
|:---|:---|
| `admin` | 管理用户 + 查看所有数据 + 系统设置 |
| `hr` | CRUD 候选人/职位/面试 + 评估 |
| `recruiter` | 查看候选人 + 评估 + 面试参与 |

> RBAC 的错误响应直接使用统一格式 `{"success": false, "error": "Forbidden"}`，不依赖 B2 先行。

**退出检查**：
- [ ] 日志输出为 JSON 格式（`docker logs` 可 grep）
- [ ] `GET /health` 返回 4 项服务检查结果
- [ ] Swagger UI 中所有端点有描述
- [ ] `CONTRIBUTING.md` + `CHANGELOG.md` 存在
- [ ] admin/hr/recruiter 三种角色访问差异可验证
- [ ] `pnpm build` 通过

---

## Phase F: 差异化功能

> 时长：12-20h（修正：原 6-10h 偏低，Skill 提取器需 LLM prompt 工程 + 门控 + 前端界面）
> 并行策略：F1 无依赖，F2 依赖 session_summaries 数据，F3 依赖 F2

### F1. 跨会话记忆 UI（Phase 2a 剩余，2-3h）

后端 `summaries.py` 已有。前端 Settings 页面新增"记忆管理" tab：
- 列表查看历史摘要（分页）
- 全文搜索（前端过滤）
- 编辑 + 删除单条记忆

### F2. Skill 提取器（Phase 2b，6-10h）

从 session_summaries 成功记录 → 自动提取可复用技能。需完成：

```python
# 新建 apps/api/app/skills/extractor.py
class SkillExtractor:
    async def extract_from_session(self, summary: dict) -> Skill | None:
        """LLM prompt：分析 session → 提取技能模板"""
        # prompt 工程方向：
        # "分析以下招聘筛选经验，提取可复用的 Skill：
        #  步骤、判断标准、工具调用模式、权重"

    async def install_skill(self, skill: Skill) -> bool:
        """置信度 ≥ 0.8 自动注册到 app/skills/{name}/ 目录
           < 0.8 写入 pending_skills 表 → Settings 待确认列表"""
```

依赖条件：session_summaries 表已有 ≥ 3 条成功记录。

### F3. 主动推荐（Phase 3.1，3-5h）

新候选人创建 → 自动匹配历史 JD → 返回 Top 5 → Dashboard 通知。

依赖 F2（技能匹配逻辑可复用）。

**退出检查**：
- [ ] Settings 页面"记忆管理"可查看/搜索/编辑/删除
- [ ] 从 ≥ 3 条成功 session 提取 ≥ 1 个可复用 Skill
- [ ] 新简历上传后 Dashboard 显示推荐结果
- [ ] `pytest` 全部通过
- [ ] `pnpm build` 通过

---

## 执行路线图

```
Phase A (测试): 6-10h ─── A1-A5 并行 → A6 门禁
        │
Phase B (后端): 2-3h  ─── B1-B4 并行
        │
Phase C (前端): 3-5h  ─── C1 审计 → C2+C3 修复
        │
Phase D (E2E):  3-4h  ─── D1 修复 → D2-D4 强化
        │
Phase E (生产):  4-6h  ─── E1-E5 全部并行
        │
Phase F (功能): 12-20h ─── F1 → F2 → F3 串行
        │
总计: ~30-48h (约 4-6 工作日)
```

---

## 关键里程碑

| # | 里程碑 | 验收条件 | 对应 Phase |
|:---|:---|:---|:---:|
| M1 | 覆盖率 88% | `--cov-fail-under=88` 通过 | A |
| M2 | 全部测试通过（Docker 无关） | `pytest` exit code 0，0 warning | A |
| M3 | 前端三态完备 | 12 页全部达到 C1 定义标准 | C |
| M4 | E2E 全绿 | `npx playwright test` exit code 0（连续 2 次）| D |
| M5 | 生产就绪 | JSON 日志 + 增强健康检查 + Swagger 完整 + RBAC | E |
| M6 | Skill 提取 | 从真实 session 提取 ≥ 1 个 Skill | F |

---

## 回退策略

| Phase | 风险场景 | 超时门限 | 回退动作 |
|:---|:---|:---:|:---|
| A1 | agent_service mock 复杂度过高 | 1.5h/子任务 | 标记 `@pytest.mark.integration`，不阻塞 CI |
| A6 | 覆盖率 < 88% | — | 目标降为 85%，90% 为 stretch |
| C | 状态缺失页面 > 6 个 | 5h | 只修复高优先级页面（evaluation/interview/dashboard）|
| D | E2E flaky 无法消除 | 3h | `retries: 3`，标记 flaky 测试为 `skip` |
| E5 | migration 冲突 | 1h | 回退 migration，单独提 PR |
| F2 | Skill 提取质量 < 0.6 | 5h | 改为手动注册流程，去 LLM prompt |

通用原则：**超时门限超标 → 缩小范围 → 不阻塞后续 Phase**。

---

## 不在此范围

以下明确不做：
- 多租户 — 需独立设计评审
- 计费/Stripe — 商业决策依赖
- vLLM GPU 部署脚本 — 硬件依赖
- 移动端适配 — 非当前需求
- 性能压测 — 上线后按需
- i18n 国际化 — 后续版本

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| Agent Service mock 复杂度过高 | 中 | A1 耗时超标 | 拆多文件 + 超时降级 `@pytest.mark.integration` |
| E2E 在 CI 中 flaky | 高 | CI 不可信 | retry 2 + 串行 + testid + 超时降级 skip |
| 前端三态审计发现大量缺失 | 中 | C 阶段范围蔓延 | 只修 3 个高优先级页面 |
| Skill 提取质量低 | 高 | F2 耗时超估 | 0.6 置信度门控 + 先出 MVP |
| RBAC migration 冲突 | 低 | E5 阻塞 | 单独 PR，可回退 |

---

## 附录：当前详细信息

### 后端 API 路由（67 业务 + 2 系统）

```
▶ 认证 (3)
  POST   /api/v1/auth/register
  POST   /api/v1/auth/login
  GET    /api/v1/auth/me

▶ 候选人 CRUD (5)
  GET    /api/v1/candidates
  GET    /api/v1/candidates/{id}
  POST   /api/v1/candidates
  PUT    /api/v1/candidates/{id}
  DELETE /api/v1/candidates/{id}

▶ 职位 CRUD (5)
  GET    /api/v1/jobs
  GET    /api/v1/jobs/{id}
  POST   /api/v1/jobs
  PUT    /api/v1/jobs/{id}
  DELETE /api/v1/jobs/{id}

▶ 申请 CRUD (5)
  GET    /api/v1/applications
  GET    /api/v1/applications/{id}
  POST   /api/v1/applications
  PUT    /api/v1/applications/{id}
  DELETE /api/v1/applications/{id}

▶ 面试 CRUD (7)
  GET    /api/v1/interviews
  GET    /api/v1/interviews/{id}
  POST   /api/v1/interviews
  PATCH  /api/v1/interviews/{id}/confirm
  PATCH  /api/v1/interviews/{id}/cancel
  PATCH  /api/v1/interviews/{id}/complete

▶ 评估 (2)
  GET    /api/v1/evaluations
  GET    /api/v1/evaluations/{candidate_id}

▶ 仪表盘 (2)
  GET    /api/v1/dashboard/stats
  GET    /api/v1/dashboard/reports

▶ 设置 (4)
  GET    /api/v1/settings
  GET    /api/v1/settings/{key}
  PUT    /api/v1/settings/{key}
  DELETE /api/v1/settings/{key}

▶ Pipeline (5)
  GET    /api/v1/pipeline/evaluations
  POST   /api/v1/pipeline/screen-resume
  GET    /api/v1/pipeline/{task_id}/stream
  GET    /api/v1/pipeline/{pipeline_id}/progress
  POST   /api/v1/pipeline/generate-report

▶ 并行 (2)
  POST   /api/v1/parallel/multi-evaluate
  POST   /api/v1/parallel/data-aggregate

▶ 编排 (1)
  POST   /api/v1/orchestrator/analyze

▶ 路由 (1)
  POST   /api/v1/router/classify

▶ 单Agent (3)
  POST   /api/v1/agent/chat
  POST   /api/v1/agent/generate-jd
  POST   /api/v1/agent/knowledge-query

▶ 生成循环 (2)
  POST   /api/v1/loop/jd-generate
  POST   /api/v1/loop/jd-improve

▶ 人工审批 (5)
  POST   /api/v1/human-loop/schedule
  POST   /api/v1/human-loop/approve
  GET    /api/v1/human-loop/pending
  GET    /api/v1/human-loop/history
  POST   /api/v1/human-loop/stop

▶ 简历 (3)
  POST   /api/v1/resume/upload-resume
  POST   /api/v1/resume/extract-resume
  POST   /api/v1/resume/confirm-resume

▶ 知识库 (3)
  POST   /api/v1/knowledge/documents/ingest
  POST   /api/v1/knowledge/query
  POST   /api/v1/knowledge/search

▶ 向量检索 (2)
  POST   /api/v1/retrieval/search
  POST   /api/v1/retrieval/embed

▶ 记忆 (4)
  POST   /api/v1/memory/read
  POST   /api/v1/memory/write
  POST   /api/v1/memory/delete
  POST   /api/v1/memory/keys

▶ 工具 (3)
  POST   /api/v1/tools/email/send
  GET    /api/v1/tools/calendar/query
  POST   /api/v1/tools/calendar/book

▶ 摘要 (3)
  GET    /api/v1/summaries
  PUT    /api/v1/summaries/{summary_id}
  DELETE /api/v1/summaries/{summary_id}

▶ 系统 (2)
  GET    /health
  GET    /metrics
```

### 测试文件清单（47 个）

```
test_rate_limit.py        test_agents.py          test_aggregator.py
test_human_loop.py        test_pipeline_flow.py   test_pipeline.py
test_evaluations_api.py   test_pipeline_api.py    test_core.py
test_router_route.py      test_loop.py            test_auth.py
test_gen_eval_loop.py     test_settings.py        test_memory.py
test_orchestrator.py      test_interviews_api.py  test_tools.py
test_parallel.py          test_jobs.py            test_retrieval.py
test_summary_service.py   test_candidates.py      test_knowledge.py
test_knowledge_service.py test_agent.py           test_dashboard.py
test_report_service.py    test_screening_service  test_dashboard_reports.py
test_application_service  test_router_agent.py    test_llm_clients.py
test_user_service.py      test_llm_retry.py       test_interview_service.py
test_coverage_edge_cases  test_applications.py    test_jd_generator.py
test_skills_init.py       test_report.py
test_skill_web_search.py  test_core_security.py
test_skill_weather.py     test_response.py
test_candidate_service.py test_job_service.py
```

### 前端 E2E（12 spec）

```
auth.spec.ts        screening.spec.ts   knowledge.spec.ts
settings.spec.ts    candidates.spec.ts  interview.spec.ts
reports.spec.ts     jobs.spec.ts        evaluation.spec.ts
talent-profile.spec dashboard.spec.ts   jd-generator.spec.ts
```
