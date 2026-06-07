# Ship Report 模板

> **版本**: 1.0 (2026-06-07 A6 抽)
> **适用范围**: Phase A/B/C/D 所有 PR 的 ship report (`.omo/plans/2026-06-07-roadmap-corrected.md` 后续)
> **强制**: PR 完成必须写 ship report 走此模板, lint check `scripts/check_ship_report.py` 验证 9 章节 + 5 强约束

## 模板正文

复制下面模板 → 替换 `[占位符]` → commit 即可.

```markdown
# Phase [X] · [Y] Ship Report — [一句话标题]

> **Ship 日期**: [YYYY-MM-DD]
> **依据**: [规划文件路径 + §章节]
> **上一站**: [commit_short_sha] ([一句话]) — [YYYY-MM-DD]
> **commit**: [N] 个 feat + [M] 个 docs (按 v0.5b/v0.6 风格拆 2 commit)
> **接受门槛**: [N 个量化 KPI 或测试 pass 数]

## 1. 概览

| 维度 | 状态 |
|---|---|
| [改动 1 名称] | ✅ |
| [改动 2 名称] | ✅ |
| [测试 1 名称] | ✅ N/N passed |
| [外部依赖 1] | ✅ [e.g. PR-2 引用, 已 ship] |
| [风险评估] | L (无生产代码改动) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `[相对路径 1]` | +N / -M | [一句话说明] |
| `[相对路径 2]` | +N (新) | [一句话说明] |
| **总** | **+N / -M** | [X] 文件 |

## 3. 关键决策

### 3.1 [决策标题]

[问题]: [现状 + 为什么需要决策]

[方案 A vs B vs C 简述, 选 X 的理由]

[代码示例 if 需要]

[影响 / 风险]

### 3.2 [决策标题 2]

[同上结构]

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `[测试函数名]` | [覆盖什么场景] |
| 2 | `[测试函数名]` | [覆盖什么场景] |
| **总** | **[N/M] passed** | |

**未测** (推后续 PR): [列表]

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| PR ≤ 1.5d (5 强约束 §1) | 实际 [N]d | ✅ |
| +30% buffer (5 强约束 §2) | 估 [N]d → 实际 [N]d | ✅/⚠️ 超 [M]d |
| 1 PR 必含测 (5 强约束 §3) | [N] 新测试 + [M] 端到端 | ✅ |
| H 风险 rollback (5 强约束 §4) | 风险 [L/M/H] | ✅/N/A |
| 顺序锁死 (5 强约束 §5) | Phase [X] 第 [N] 步 | ✅ |
| 量化 KPI (5 强约束 §6) | [N] KPI 全部满足 | ✅ |

## 6. 未在 [Y] 范围 (明确不做)

- ❌ [不做项 1] — [理由 / 推到哪个 PR]
- ❌ [不做项 2] — [理由]
- ❌ [不做项 3] — [理由]

## 7. 后续路径

**[下一个 PR] ([估时]d, 1 commit) — [一句话]**:
- [改动 1]
- [改动 2]

**[下下个 PR] ([估时]d, 1 commit) — [一句话]**:
- [改动 1]

**Phase [N] 修复 PR (推后) — [总述]**:
- [修复 1]
- [修复 2]

## 8. 回滚方法

```bash
git revert <commit>
# 改动 [N] 文件
git checkout HEAD~1 -- \
  [文件 1] \
  [文件 2] \
  ...
```

**回滚影响**:
- [影响 1]
- [影响 2]
- **风险**: [L/M/H]

## 9. 引用

- 规划: [规划文件 + §章节]
- Momus 审核: [审核文件 + §章节] (如有)
- 上站: [commit_short_sha] ([一句话])
- 历史: [相关 PR 列表]
- 数据: [测脚本/报告/JSON 路径]

**下一步**: [下一项 PR 名称 + commit 链接]
```

## 9 章节必填

| # | 章节 | 必填 | 长度建议 |
|---|---|---|---|
| 1 | 概览 | ✅ | 5-10 行表格 |
| 2 | 改动 diff | ✅ | N 行表格 (跟文件数) |
| 3 | 关键决策 | ✅ | 2-5 个 3.x 小节 |
| 4 | 测试 | ✅ | 表格 + 未测说明 |
| 5 | 退出门槛验证 | ✅ | 6 行 5 强约束 |
| 6 | 未在范围 | ✅ | 3-5 个 ❌ 项 |
| 7 | 后续路径 | ✅ | 2-3 个后续 PR |
| 8 | 回滚方法 | ✅ | git 命令 + 影响 |
| 9 | 引用 | ✅ | 3-5 个 markdown 链接 |

## 5 强约束必填 (退出门槛表)

每行必须填, 不允许 `TBD` / `TODO` / 留空:

| 强约束 | 必填字段 |
|---|---|
| §1 PR ≤ 1.5d | 实际估时 |
| §2 +30% buffer | 规划估时 + 实际估时 (含 buffer 状态) |
| §3 1 PR 必含测 | 测试数 + 通过数 |
| §4 H 风险 rollback | 风险评级 (L/M/H) |
| §5 顺序锁死 | Phase 名 + 步数 |
| §6 量化 KPI | KPI 数 (每阶段 ≥ 3) |

## 命名约定

| 元素 | 命名 |
|---|---|
| 文件名 | `docs/mcp-v4-v[X.Y]-[a/b/c]-ship-report.md` (沿用 v0.5b/v0.6 风格) |
| 章节标题 | `## 1. 概览` (数字 + 点 + 标题) |
| 子节 | `### 3.1 [决策标题]` (3.1 格式) |
| 引用 | markdown 链接, 文本用 commit_short_sha 或文件名 |
| 表格 | 必须有表头, 至少 2 列 |

## 与历史 ship report 关系

| 历史 PR | 文件 | 符合模板? |
|---|---|---|
| v0.5b retry | docs/mcp-v4-v0.5b-ship-report.md | 部分 (缺 §5 5 强约束) |
| v0.6a RQ | docs/mcp-v4-v0.6a-ship-report.md | 部分 |
| v0.6b WS | docs/mcp-v4-v0.6b-ship-report.md | 部分 |
| v0.6c force | docs/mcp-v4-v0.6c-ship-report.md | ✅ 完全符合 |
| v1.0b datetime | docs/mcp-v4-v1.0b-ship-report.md | 部分 |
| v1.1 phase D | docs/mcp-v4-v1.1-ship-report.md | 部分 |
| v1.2 cross-server | docs/mcp-v4-v1.2-ship-report.md | 部分 |
| v1.3 model scan | docs/mcp-v4-v1.3-ship-report.md | 部分 |
| **A1 rate limit** | **docs/mcp-v4-v1.4-a1-ship-report.md** | ✅ **完全符合 (本模板原型)** |
| **A2 E2E CI** | **docs/mcp-v4-v1.4-a2-ship-report.md** | ✅ |
| **A3 v1.4a** | **docs/mcp-v4-v1.4-a3-ship-report.md** | ✅ |
| **A4 v1.4b** | **docs/mcp-v4-v1.4-a4-ship-report.md** | ✅ |
| **A5 perf baseline** | **docs/mcp-v4-v1.4-a5-ship-report.md** | ✅ |

**后续 PR 强制**: A6+ 全部 ship report 走此模板 + lint 通过.

## Lint 验证

`scripts/check_ship_report.py [ship_report.md]` 验证:
- 9 章节存在 (## 1, ## 2, ..., ## 9)
- 5 强约束 6 行在退出门槛表
- 命名符合 `mcp-v4-v[X.Y]-[a/b/c]-ship-report.md` 格式
- 引用 ≥ 3 个 markdown 链接

## 引用

- 抽 5 个 ship report 共性: A1+A2+A3+A4+A5 (Phase A)
- 历史模板演进: v0.5b (8 章) → v0.6c (10 章加 bug 决策) → A1 (9 章加回滚)
- 5 强约束来源: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §7
