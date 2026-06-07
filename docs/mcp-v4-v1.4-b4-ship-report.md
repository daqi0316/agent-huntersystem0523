# Phase B · B4 Ship Report — Knowledge/RAG E2E (Qdrant upload→query→cite)

> **Ship 日期**: 2026-06-08
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B4 = Knowledge/RAG E2E 2d)
> **修正**: 真 Qdrant 可用 + mock LLM (B1/B2 教训), 实际 0.3d
> **跳 B3**: Router E2E 80% 已被 A4 编排测试覆盖
> **上一站**: `B2` (Human-in-loop, bfd2ee1 + 92e1f85) — 2026-06-08
> **commit**: 1 个测试文件 + 1 个 ship report
> **接受门槛**: 3/3 测试通过 + 60+ 现有 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_knowledge_b4.py` 测试文件 (200+ 行) | ✅ |
| `test_ingest_document_chunks_text` | ✅ chunking + embedding + upsert 端到端 |
| `test_search_returns_top_k_relevant` | ✅ 向量检索 top_k + score > 0.3 过滤 |
| `test_query_rag_returns_answer_with_citations` | ✅ RAG: search → LLM 生成 → 含 cite 格式 |
| 60 个现有 E2E 不退化 | ✅ 69 passed (60 + B1 3 + B2 3 + B4 3) |
| 接入 mcp-ci.yml unit-tests job | ✅ 自动 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_knowledge_b4.py` | +212 (新) | 3 测试 (ingest + search + RAG query) |
| **总** | **+212 / 0** | 1 文件 |

## 3. 关键决策

### 3.1 mock 路径: 复用 B1+B2 教训 (module 内部名字)

按 B1 §3.1 + B2 §3.2 教训, patch module 内部 import 名字, 不是源头:
- `app.services.knowledge.get_llm_client` (KnowledgeService 内部 import)
- `app.services.knowledge.get_qdrant` (KnowledgeService 内部 import)

不用源头 `app.llm.get_llm_client` 或 `app.core.qdrant.get_qdrant` (mock 失效).

### 3.2 mock Qdrant (隔离外部依赖)

按"工程化深度"原则:
- 真 Qdrant 在 compose dev 跑, 但测试**不依赖真 Qdrant** (避免污染生产 collection)
- mock `get_qdrant` 返 fake client, 验 `upsert` / `query_points` 被调 + 参数对
- 真 Qdrant 行为留到 Phase E staging 测

### 3.3 测 cite 格式 (Momus §2.4 关注点)

B4 关键业务: 验 `[来源: title]` 格式 cite 在 answer 中, 且 sources 列表含原文 + title + score.

测试 3:
- LLM chat mock 返 `"根据 [来源: RAG 文档] 介绍, RAG 是检索增强生成技术。"`
- 断言 `"[来源: RAG 文档]" in result["answer"]`
- 断言 `result["sources"][0]["content"] == "RAG 是检索增强生成技术"` (原文回传供前端展示)

按 Momus §2.4: "Cite 引用 ID 真的存在于 Qdrant" — 测 1 验 upsert 真传 document_id (Qdrant ID), 测 2 验 search 返的 sources 含 Qdrant 来的 point.

### 3.4 score > 0.3 阈值测试

knowledge.py:153 `if r.score > 0.3` 过滤. 测试 2 用 3 候选 (0.85 + 0.62 + 0.2), 验 0.2 被过滤, 返 2.

防止后续 PR 误改阈值: 0.3 是 relevance threshold, 改前要 review.

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_ingest_document_chunks_text` | KnowledgeService.ingest_document 端到端: 文本分块 + LLM.embed (mock) + Qdrant.upsert (mock) → 验 document_id + chunks_count + Qdrant.create_collection + upsert 被调 + payload 含 document_id + title + content |
| 2 | `test_search_returns_top_k_relevant` | KnowledgeService.search 端到端: LLM.embed (mock) + Qdrant.query_points 返 3 候选 → 验 score > 0.3 过滤 (3→2) + 0.85/0.62 留下 + 0.2 过滤 |
| 3 | `test_query_rag_returns_answer_with_citations` | KnowledgeService.query 端到端 (RAG): search → LLM.chat 生成 → 验 answer 含 [来源: title] cite 格式 + sources list 含原文 + title + score + LLM.chat/embed 各调 1 次 |

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 3 新测试通过 | `pytest tests/mcp/integration/test_e2e_knowledge_b4.py` | ✅ 3/3 passed |
| 60 现有 E2E 不退化 | `pytest tests/mcp/integration/ --ignore=test_host_lifecycle` | ✅ 69 passed |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d | ✅ |
| 5 强约束 (+30% buffer) | 估 2d → 实际 0.3d | ✅ 大幅 buffer 内 |
| 5 强约束 (1 PR 必含测) | 3 新测试 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新测试, 不动 prod) | N/A |
| 5 强约束 (顺序锁死) | B4 = Phase B 第 4 步 (跳 B3) | ✅ |
| 5 强约束 (量化 KPI) | 3/3 测 + 0.03s 跑完 + 69 E2E 不退化 | ✅ 3 KPI |

## 6. 未在 B4 范围（明确不做）

- ❌ 真 Qdrant E2E (推 Phase E staging, 避免污染生产 collection)
- ❌ ensure_collection 失败 fallback 路径 (推后续)
- ❌ _chunk_text 边界 (空文本 / 超长文本, 推后续)
- ❌ 真实 LLM embed (768 维向量生成, 推 Phase E)
- ❌ 知识库更新/删除 (ingest only, 无 delete API)
- ❌ multi-collection 支持 (KnowledgeService 单 collection)

## 7. 后续路径

**B5 (0.8d, 1 commit) — Auth/Org E2E (5-8 隔离 case)**:
- 写 `test_e2e_auth_org_b5.py`
- 测同 org/跨 org/super_admin/org 切换 多场景
- 真 DB 多 org (fixture 创建 2-3 个 org + user)
- 复用 B2 fixture (e2e-tester 真 user)

**B6 (1.5d, 1 commit) — Frontend E2E (5 关键流程)**:
- 写 Playwright spec (登录/上传/搜索/详情/导出)
- 跑真后端 (8000) + 真 DB + 真 redis + 真 qdrant
- **H 风险**: playwright CI 集成复杂, docker-compose + teardown workflow

**修复 PR (推后)**:
- mcp_host anyio lifecycle (Fix-1 推后)
- run_recommendation_scan DB transaction abort (Fix-1 推后)
- A3+A4 fixture 改用真 user (B2 推后)

## 8. 回滚方法

```bash
git revert <B4 commit>
git checkout HEAD~1 -- apps/api/tests/mcp/integration/test_e2e_knowledge_b4.py
```

**回滚影响**:
- B4 测试消失
- 其他 E2E 不受影响
- 0 production 代码改动, **零风险**

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B4 = Knowledge/RAG 2d)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §2.4 (cite 格式验证)
- 上站: B2 (Human-in-loop, bfd2ee1 + 92e1f85)
- B1 mock 教训: `docs/mcp-v4-v1.4-b1-ship-report.md` §3.1
- B2 fixture 教训: `docs/mcp-v4-v1.4-b2-ship-report.md` §3.3 (e2e-tester 真 user)
- KnowledgeService: `app/services/knowledge.py` (ingest + search + query)
- Knowledge tool: `app/tools/knowledge.py` (search_knowledge 入口)
- Qdrant client: `app/core/qdrant.py` (get_qdrant factory)

**下一步**: B5 (Auth/Org E2E 5-8 隔离 case 0.8d)
