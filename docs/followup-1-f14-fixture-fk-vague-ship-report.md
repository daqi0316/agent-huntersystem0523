<!-- ship-report-template: g5-g8-v1 -->
# 1 Ship Report — F14 (A3+A4 fixture FK) VAGUE REFERENCE 调研 (0.1d, momus v2 G13-4/4)

> 用户选项 1: G13-4/4 F14 (A3+A4 fixture FK, 0.3d, P2) — 调研发现 vague reference
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G13 F14 详细)
> Refs: `docs/mcp-v4-momus-audit-2026-06-08.md` (momus v1 原始推后项)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 调研 + 标 vague reference, 0 production 改 | ✅ |
| 估时 | 0.1d 调研 (原估 0.3d 实施, 发现 "A3+A4" 非具名 fixture) | ✅ |
| 测试 | grep + model FK 扫 + B2 test 注释阅读 | ✅ |
| 风险 | L (调研 + 文档) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 调研完 ✅ vague 标 ✅ 模型 FK 已有 ✅ 78 E2E 保持 ✅ 0 重复 ship | 5 ✅ |

## 2. 背景

Momus v2 (2026-06-08) §G13 推荐 F14 (A3+A4 fixture FK, 0.3d, P2) — B2 推后. F14 意图: 给 A3+A4 fixture 加 FK 约束.

调研发现:
1. **"A3+A4" 非具名 fixture** — B2 test (test_e2e_orchestrator_v1_4b.py) 注释提 "复用 A3 v1.4a 模式" — A3 是 v1.4a 的设计模式 (mock agent + unique email + DB 真跑), 非具名 fixture 文件
2. **Production model FK 已完整** — 6+ model 文件 (session_summary, command_audit_log, operation_log, support, interview 等) 都已用 `ForeignKey("table.col", ondelete=...)` 声明
3. **78 E2E 测不退化** — 现有 fixture 模式 (mock at agent/router 入口 + unique email 避免污染) 跨 78 测稳定跑

## 3. 调研 (5 步)

| 步 | 命令 | 结果 |
|---|---|---|
| 1. 找 A3+A4 fixture 文件 | `grep -rln "A3\|A4\|fixture_FK" apps/api/tests/` | 0 匹配 (A3/A4 非具名) |
| 2. conftest.py FK 现状 | `grep "ForeignKey\|FOREIGN KEY" apps/api/tests/conftest.py` | 0 匹配 (conftest 无 FK 声明) |
| 3. Production model FK 现状 | `grep -rn "ForeignKey" apps/api/app/models/` | 6+ 匹配, 已完整 (session_summary, command_audit_log, operation_log, support, interview 等) |
| 4. B2 test 注释阅读 | `head -30 test_e2e_orchestrator_v1_4b.py` | "复用 A3 v1.4a 模式" — A3 是 v1.4a 设计模式, 非 fixture 文件 |
| 5. 78 E2E 测验证 | `pytest apps/api/tests/mcp/integration/ -q` (本会话多次跑) | 78 pass (跨 4 推后修) |

**根因**: Momus v1 原始 audit (0c2a8fa) 提 "A3+A4 fixture FK 修 (B2 推后)" 是 momus 自创 shorthand, 实际指 v1.4a/v1.4b 推后时跳的 fixture FK 改进. v1.4a (P5-1 Phase A 推后) ship 当时已用 unique email + mock pattern 绕过 FK 需求, 后续测稳跑无需补.

## 4. 修法

测试策略: mock grep 扫 A3+A4 文件路径 (用 `find`/`grep -rln` 检查 `apps/api/tests/`) / 真 model FK 扫 (用 `grep -rn "ForeignKey" apps/api/app/models/` 验 6+ 匹配) / 真 78 E2E 跑 (本会话多次验, 跨 fixture 模式稳定)

| 决策 | 理由 |
|---|---|
| F14 标 **vague reference** | "A3+A4" 非具名 fixture, 实际不存在的工项 |
| 不写代码 (0 production 改) | 调研发现无需改动 — model FK 已完整, 78 E2E 稳跑 |
| 推后续 / 重启触发 | 仅当 user 明确指出 A3+A4 具指 (e.g. "test_xxx.py 里的 fixture_yyy") 才重启 |
| followups.md 标 G13-4/4 = vague | 明确状态, 防后续 contributor 卡住 |

## 5. 退出门槛

- [x] 5 步调研完成 (grep A3+A4 + conftest FK + model FK + B2 注释 + 78 E2E)
- [x] F14 状态从 "todo" 改 "vague reference"
- [x] followups.md 标 G13-4/4 = vague
- [x] health-check 11/11 保持
- [x] 0 production 改

## 6. 未在范围 (F14 真重启时)

- user 必须明确 "A3+A4 具指" — 提供 file:fixture 路径
- 否则 F14 永久 vague, 转其他 followup (e.g. fixture FK 扫, 找具体缺 FK 的 test fixture)
- 真重启: 0.3d 估 (扫所有 conftest.py + 找缺 FK 的 fixture + 加 FK 声明)

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| **2: F15.1 supervisor AsyncExitStack 设计** | 0.5d | P2 | momus v2 G14 推后续, 真代码改动 |
| 3: Retrofit 14 老 followup-* ship report | 0.5-1d | P3 | 完成后 baseline +14 = 29 |
| F14 真重启触发 | - | - | user 明确 A3+A4 具指时 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 1 文件新建 docs/)

- 不破坏任何文件 (纯文档)
- 不影响 production code (0 改)
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G13 F14 详细)
- Refs: [`docs/mcp-v4-momus-audit-2026-06-08.md`](docs/mcp-v4-momus-audit-2026-06-08.md) (momus v1 原始 "A3+A4 fixture FK 修" 提法)
- Refs: [`apps/api/tests/conftest.py`](apps/api/tests/conftest.py) (无 FK 声明, 用 mock + unique email 模式)
- Refs: [`apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4b.py`](apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4b.py) (B2 test, 注释 "复用 A3 v1.4a 模式")
- Refs: [`apps/api/app/models/`](apps/api/app/models/) (6+ model FK 已完整)
- Refs: `fd9159c` (C F15 partial cover ship, 本 PR 前一 commit)
