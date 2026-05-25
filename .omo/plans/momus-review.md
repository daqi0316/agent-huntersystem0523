# Momus 审查报告: V4 Completion Plan

**审查对象**: `.omo/plans/completion-plan-v4.md`
**审查标准**: Clarity / Verifiability / Completeness / Actionability
**审查结论**: ⚠️ **有条件通过 — 需修正 12 个问题后才可执行**

---

## 🔴 致命问题 (必须修复)

### F1. Phase 1 与 Phase 2 依赖关系矛盾

> 依赖图: Phase 1 → Phase 2
> 但文字又说: "Phase 1 和 Phase 2 可以并行开始"

**问题**: 如果并行开始，Phase 1 的新端点（如 evaluation 页面）不存在后端时，前端改动无意义。Phase 1 的 `1.2` 明确依赖 Phase 2 的 `2.6`。

**修复**: 拆分为两种走法之一：
- **(A) 严格串行**: Phase 2（后端端点）必须先于 Phase 1（前端对接）完成，删除"可并行"的表述
- **(B) 并行 + Mock 层**: Phase 1 期间前端仍然使用 mock，但 mock 数据改为与后端 Schema 一致的 ts 类型定义，后端端点完成后只需改一行 URL

### F2. Phase 1.4 — talent-profile 验收标准不可测量

> "调用候选人和评估 API"

**问题**: 无明确端点路径、无数据字段定义、无 UI 状态标准。执行者无法判断"完成"。

**修复**: 必须指定：
- 哪个端点返回哪些字段
- 正常/空/异常的 UI 表现分别是什么

### F3. Phase 2.6 — evaluations 端点没有数据模型

> "新端点，用 Pipeline/Aggregator 结果"

**问题**: Pipeline 和 Aggregator 是运行时执行器，不持久化结果。没有 `Evaluation` 数据库模型或存储层，这个端点要么每次重新运行 pipeline（慢且不可控），要么需要新建模型 + 迁移 + 存储逻辑。方案本身有架构缺口。

**修复**: 必须在 Phase 2 之前先行决定：
- **(A)** 新建 `evaluations` 表，pipeline 完成后写入 → 正常 API 查询
- **(B)** 直接从 candidates + applications 表按需聚合 → 轻量级方案
- **(C)** 改为 POST（触发运行）而非 GET（查询已有结果）

### F4. Phase 4.1 — 非可操作项

> "确保 CI 中实际可运行"

**问题**: 这是 check/verification，不是 action item。没有给出"如果不可运行，做什么"。

**修复**: 拆分为具体子任务：
1. 本地运行所有 13 个 spec → 记录失败项
2. 修复失败 spec
3. CI 环境重跑 → 验证通过

---

## 🟡 模糊问题 (需要澄清)

### A1. 端点路径前缀不一致

Phase 2 的端点写为 `GET /api/v1/interviews`，但实际系统是通过 `router.py` 注册的 `api_router(prefix="/api/v1")`，Route 文件内部注册相对路径。

**示例**: 如果 `interview.py` 里写 `@router.get("/interviews")`，最终 URL 是 `/api/v1/interviews`。

**修复**: 在 Phase 2 的描述中使用 `router.py include 后的相对路径`，避免歧义：
```
2.1 → interviews.py: @router.get("")        → GET /api/v1/interviews
2.2 → interviews.py: @router.post("")       → POST /api/v1/interviews
2.3 → interviews.py: @router.patch("/{id}/confirm")
2.4 → interviews.py: @router.patch("/{id}/cancel")
2.5 → interviews.py: @router.patch("/{id}/complete")
```

### A2. Phase 3 测试缺少外部依赖策略

- `test_knowledge.py` — 需要 Qdrant，测试中如何 mock？
- `test_qdrant.py` — 需要真实 Qdrant 实例还是可以用 AsyncQdrantClient mock？
- `test_llm.py` — LLM 调用需要 mock HTTP 层还是 mock `get_llm_client()`？

**修复**: 每个测试项必须写明 mock 策略：
```
3.1 test_knowledge.py — mock Qdrant 的 get_qdrant()
3.3 test_qdrant.py — 使用 unittest.mock.patch 避免真实连接
3.4 test_llm.py — mock httpx.AsyncClient 或 patch llm.chat()
```

### A3. Phase 3.8 "补边界条件" 无边界定义

> "补边界条件 + 错误路径测试"

**问题**: 哪些服务的哪些边界？"边界条件"太宽泛。

**修复**: 列出具体边界：
- CandidateService.get_by_id() — UUID 格式校验、空字符串、null
- JobService.list() — 超大 limit、负数 skip、特殊字符 search
- ApplicationsService — 重复创建、不存在的 candidate_id/job_id

### A4. Phase 5.2 "检查 docker-compose.dev.yml" 无预期状态

> "检查是否覆盖所有服务"

**问题**: 什么算"覆盖"？缺少什么服务？没有 pass/fail 标准。

**修复**: 明确列出需要检查的服务列表：
```
必须包含: postgres, redis, qdrant, minio, rabbitmq
可选包含: api (dev模式), web (dev模式)
未覆盖风险: vllm (需 GPU)
```

### A5. Phase 5.7 "endpoint description 补全" 范围过大

> "Swagger 中 endpoint description 补全"

**问题**: 18 个路由文件，数十字点。没有优先级或分类。

**修复**: 按重要性排序：
```
高: auth, candidates, jobs (面向用户)
中: pipeline, screening, interview (业务核心)
低: tools, retrieval (内部工具)
```

---

## 🔵 遗漏问题 (可以增加)

### M1. 缺少 git 分支策略

多个 Phase 可并行/串行时，没有 git 分支和工作流指导。建议：
```
main ← develop
    ├── feature/v4-backend-endpoints  (Phase 2)
    ├── feature/v4-frontend-api       (Phase 1, 依赖 Phase 2)
    └── feature/v4-test-coverage      (Phase 3, 无依赖, 可随时进行)
```

### M2. 缺少 CI pipeline 变更

Phase 2 新增端点后，现有 CI 中 `Check import health` 步骤会自动验证。但如果新增了数据库表（evaluations），需要对应的 migration 步骤。Plan 未提及。

### M3. 缺少回退策略

每个 Phase 如果中途发现问题，如何回退？
- Phase 1: `git revert` 前端文件？
- Phase 2: 新增端点发现架构设计错误怎么办？

建议每个 Phase 增加 "Risks & Rollback" 小节。

### M4. 工作量估计不合理

```
Phase 1: 6 pages × 1-2h = 6-12h (合理，简单 CRUD 对接)
Phase 2: 8 endpoints × 0.5-1h = 4-8h (低估，含新建文件 + 注册路由 + 测试)
         尤其 2.6 evaluations 涉及架构决策，至少 2-4h
Phase 3: 8 test files × 0.5h = 4h (严重低估，单个 test file 含 mock/fixture 搭建至少 1-2h)
Phase 4: 2-3 specs × 0.5h = 1-1.5h (低估，auth E2E flow 含 setup 至少 2h)
```

**修正估计**: 约 **38-60h**（5-8 个工作日），而非 2-4 天。

### M5. 没有代码审查标准

完成后的 PR 需要什么审查标准？以下缺失：
- TypeScript: 无 `as any`、无 `@ts-ignore`
- Python: Ruff pass、类型标注完整
- 测试: 新代码必须有对应测试
- API: 符合现有 error response 格式

---

## 📋 问题汇总

| 严重度 | 编号 | 简述 | 建议 |
|--------|------|------|------|
| 🔴 F1 | 依赖矛盾 | Phase 1→2 串行 vs 并行矛盾 | 二选一并明确 |
| 🔴 F2 | 不可验收 | talent-profile 无具体端点/字段 | 补充数据契约 |
| 🔴 F3 | 架构缺口 | evaluations 无数据模型 | 先做架构决策 |
| 🔴 F4 | 不可操作 | "确保CI可运行"不是 actionable | 拆解为具体修复 |
| 🟡 A1 | 路径歧义 | `/api/v1/` 前缀 vs 相对路径 | 统一使用相对路径 |
| 🟡 A2 | mock 策略 | 测试缺 mock 方案 | 每个测试指定 mock 策略 |
| 🟡 A3 | 边界模糊 | "边界条件"不具体 | 列出具体边界 case |
| 🟡 A4 | 无标准 | docker-compose 检查无预期 | 列出预期服务列表 |
| 🟡 A5 | 范围过大 | endpoint description 太泛 | 按重要性排序 |
| 🔵 M1 | 遗漏 | 无 git 分支策略 | 增加分支模型 |
| 🔵 M2 | 遗漏 | 无 CI pipeline 变更评估 | 评估 migration 需求 |
| 🔵 M3 | 遗漏 | 无回退策略 | 增加 Risk & Rollback |
| 🔵 M4 | 偏差 | 工作量低估 2-3x | 修正为 5-8 工作日 |
| 🔵 M5 | 遗漏 | 无代码审查标准 | 补充 PR 质量标准 |

---

## ✅ 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **Clarity** | 6/10 | 大部分 API 路径清晰，但 talent-profile 和 Phase 4 模糊 |
| **Verifiability** | 5/10 | Phase 2 验收可验证，Phase 1/4 的验收标准太模糊 |
| **Completeness** | 4/10 | 遗漏 git 策略、回退策略、CI 影响、代码审查标准 |
| **Actionability** | 6/10 | 多数条目可直接开工，但 evaluations 架构缺口会阻塞执行 |

**修复后**: 可提升至 8+/10。建议修正所有 🔴 和 🟡 问题后开始执行。
