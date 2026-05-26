# 自审报告：v4 实施计划

**审查对象**: `.omo/plans/ai-recruitment-v4-plan.md`
**审查标准**: Clarity / Verifiability / Completeness / Factual Accuracy
**审查结论**: ⚠️ **有条件通过 — 需修复 9 个问题后才可执行**

---

## 🔴 事实性错误（必须立即修复）

### F1. Phase 0.9 — OMLXClient 已存在错误处理

> Plan 原文："当前：无错误处理，LLM 不可用时直接抛 500"

**实际代码** (`apps/api/app/llm/omlx_client.py:25-38`)：

```python
async def chat(self, messages, **kwargs) -> str:
    try:
        response = await self.client.chat.completions.create(...)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.warning("LLM chat failed: %s", e)
        return "[LLM unavailable]"
```

`chat()` 已有 try/except，`embed()` 也已有。
**此任务不成立，直接删除。**

### F2. Phase 0.7 — User model 无 settings JSONB 字段

> Plan 原文："用 User 表的 settings JSONB 字段（已有或加迁移）"

**实际**：`apps/api/app/models/` 下无任何 JSONB 字段定义。不存在"已有"。要么新建 Setting model，要么给 User 加 JSONB column（需要单独 migration）。

**修复**：需增加一个迁移文件，或明确新建独立的 `user_settings` 表。

### F3. Phase 0.6 — Application model 的字段与前端不一致

Plan 说 Application model 已存在，但使用前需验证字段定义是否与前端需要的格式一致。未读 model 前下结论说有 route 缺口是对的，但表述缺少 "验证" 步骤。

---

## 🟡 依赖关系问题

### D1. Phase 0 内部 9 项不全是并行的

Plan 写："9 项完全并行"。实际上：

| 任务 | 依赖 |
|:---|:---|
| 0.1 ReportService | 无依赖（独立文件）|
| **0.2 pipeline 接入 ReportService** | **依赖 0.1 完成** |
| 0.3 InterviewService | 无依赖 |
| 0.4 parallel/data-aggregate | 无依赖 |
| 0.5 human-loop/stop | 无依赖 |
| 0.6 Application CRUD | 无依赖 |
| 0.7 Settings API | 无依赖（但 F2 待解决）|
| 0.8 Settings 端口修复 | 无依赖 |
| 0.9 ~~OMLXClient~~ | 已删除 |

0.2 必须等 0.1 完成后才能开工。**9 项并非完全并行，而是 8+1。**

### D2. Phase 2a 与 2b 的依赖关系被高估

> Plan 依赖图：Phase 2a → Phase 2b

**质疑**：Skill 提取得真的需要跨会话记忆吗？如果我用一次成功的初筛 session 就能提取 Skill（session_summaries 表已经有了），那我完全可以不等到 Phase 2a 的"混合检索+prompt 注入"机制稳定，直接在 Phase 1 完成后就启动 2b。

**建议**：
- 如果 2b 只需要单次 session 数据 → **2a 和 2b 可并行**
- 如果 2b 需要跨会话的模式识别 → **依赖成立**

这个需要在设计阶段解决。

### D3. Phase 2a 先写设计文档再 Momus 审查——但审查意见没有入口

> 2a.1："写完后用 Momus 审查再执行"

Plan 本身应该作为 Momus 审查的入口，而不是写到 Phase 2a 内部。建议在 Plan 里就明确：**Phase 2a 启动条件 = Momus 审查 memory-design.md 通过**。

---

## 🟢 模糊/不可测量问题

### V1. Phase 1 退出检查第 1 条不能自动化

> "手动走通：上传简历 → 初筛完成 → 评估报告生成 → 面试安排确认"

"手动走通" 不可重复验证。不同人操作步骤可能不同。两个月后回来看，"上次手动走通" 不说明任何问题。

**修复为**：
```
[ ] `playwright test tests/e2e/screening-flow.spec.ts` 通过
     （覆盖：上传 → 解析 → 初筛 → 报告 → 安排面试）
```
如果现在没这个 E2E 测试，那就是 Phase 1 的任务。

### V2. Phase 2a.2 — FTS 索引对中文无效

> `to_tsvector('simple', summary_text)`

PostgreSQL 的 `simple` 配置按空格分词。**中文不按空格分词**，所以这个索引对中文内容基本无效。

**三个方案**：

| 方案 | 说明 | 成本 |
|:---|:---|:---|
| A. `pg_bigm` / `pg_trgm` 扩展 | 基于 2-gram/3-gram 模糊匹配，不需要分词器 | 中等（需安装扩展）|
| B. 仅用 Qdrant 向量检索 | 放弃 FTS，只依赖向量相似度 | 低（0 额外工作）|
| C. 混合检索前端加上 Jieba 分词 | 后端存储分词后的文本到 tsvector | 高（需引入 jieba 库）|

**建议**：直接用方案 B（纯向量），因为 Qdrant 已经能处理中文语义。只有向量检索精度不足时才考虑加入 FTS。

### V3. Phase 0 退出检查说 "覆盖率 70%"

当前：50%。Phase 0 只加了几个新测试文件，不考虑核心覆盖率提升。Phase 1 的 1.6（补关键路径测试）目标也是 70%。**两处写重复了但各自又不够**。

**修复**：Phase 0 退出检查不提覆盖率（不是 Phase 0 的目标）。Phase 1 的 1.6 改目标为 "Pipeline 和 Aggregator 模块行覆盖率 ≥ 80%"，而不是全局 70%。

---

## ⚠️ 遗漏问题

### M1. 没有定义"不做什么"

Phase 1 只说做什么，没说"不做"的边界。例如：

> Phase 1 是做数据流闭环，那 UI 重做吗？不做。
> Phase 1 包括数据库优化吗？不，除非有性能瓶颈。
> Phase 1 包括前端重构（比如从 fetch 迁到 tRPC）吗？不。

缺少这个界限，执行者会 scope creep。

### M2. RouterAgent 是 stub——哪个 Phase 修？

PRD 里在"已知问题"中提到了，但 Plan 里没有对应的任务。RouterAgent 是全局路由的分发器，如果它是 stub，那前端的 `/router` 页面就没意义。

### M3. Phase 4 多租户方案未选型

"Schema-per-tenant" 是一个方案，但不是唯一方案。还有：

- Row-level security（RLS）：同一张表，policy 控制可见性
- Database-per-tenant：极端隔离
- Schema-per-tenant：中等隔离

都需要在 Phase 4 前决策。Plan 直接选了 Schema-per-tenant 但没有论证。

### M4. 前端 build 验证只在 Phase 0 写了

Phase 1/2a/2b/3/4 的退出检查里没有 `pnpm build`。如果后端 API 改动导致前端类型不匹配，build 可能挂。

---

## 总结：修复优先级

| 严重程度 | 问题 | 操作 |
|:---|:---|:---|
| 🔴 F1 | Phase 0.9 不存在 | 直接删除该条目 |
| 🔴 F2 | Settings JSONB 不存在 | 改为新建 model 或加 migration |
| 🔴 F3 | Application model 未验证 | 加读 model 步骤 |
| 🟡 D1 | Phase 0 并行描述不准 | 改为 "8+1，同一 sub-phase" |
| 🟡 D2 | Phase 2a→2b 依赖需确认 | 设计阶段决策 |
| 🟡 D3 | Momus 审查流程不完整 | 在 Plan 头部明确 Momus gate |
| 🟢 V1 | "手动走通"不可测量 | 改为 E2E 测试 |
| 🟢 V2 | 中文 FTS 无效 | 改用 Qdrant 纯向量 |
| 🟢 V3 | 覆盖率目标冲突 | 拆成模块级目标 |
| ⚠️ M1 | 缺少"不做什么" | 每个 Phase 加边界说明 |
| ⚠️ M2 | RouterAgent stub 未安排 | 加到 Phase 0 |
| ⚠️ M3 | 多租户未选型 | Phase 4 前出设计 |
| ⚠️ M4 | 前端 build 检查遗漏 | 所有 Phase 退出检查加 `pnpm build` |

要我按这个审查结果直接修 plan 吗？
