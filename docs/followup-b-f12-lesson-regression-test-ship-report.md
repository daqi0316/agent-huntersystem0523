<!-- ship-report-template: g5-g8-v1 -->
# B Ship Report — F12 教训沉淀: NAME_PATTERN 改不破坏老 ship report 测 (0.1d, momus v2 G18)

> 用户选项 B: F12 教训沉淀 (0.1d, P3) — 防 F12-style critical bug 再发
> Refs: 598d25d (F12 critical bug fix ship report)
> Refs: 178865f (F12 ship, 暴露本 bug)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 文件改 (scripts/check_ship_report.py) + 1 文件新建 (本 test) + 1 文件新建 (本 report) | ✅ |
| 估时 | 0.1d 实际 (含调试 1 bug) | ✅ |
| 测试 | 1 测 pass (锁 baseline 15 pass >= 15) | ✅ |
| 风险 | L (测 + checker 修正, 不影响 production) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 1 测 ✅ baseline 15 ✅ NAME_PATTERN 修 ✅ subprocess ✅ 5 强约束 | 5 ✅ |

## 2. 背景

F12 (178865f) ship 后暴露 critical bug: 加 followup-* 到 NAME_PATTERN 时, 14 老 followup-* ship report 不合规 5 强约束, CI 必 fail. 立即 ship fix (598d25d) 用 advisory mode.

教训: 任何 NAME_PATTERN 改 (扩 family) 必须先验现有文件不 fail — 应有自动化测锁。

本 PR 加 1 测 + 修 1 隐性 bug (NAME_PATTERN 只接受 relative 路径, subprocess 传 absolute 路径会全 fail)。

## 3. 修法

| 子项 | 修法 | 文件 |
|---|---|---|
| 隐性 bug 修 | NAME_PATTERN `^docs/...` 改 `^(mcp-v4-v\|followup-)-...` 匹配文件名, 改用 `path.name` (而非 str(path)) — 支持 absolute 路径 | scripts/check_ship_report.py |
| NEW_NAME_PATTERN 同改 | 同步去 `^docs/` 前缀, 匹配文件名 | 同上 |
| Regression 测 | subprocess 跑 CLI 解析 "摘要: N pass, M fail", 断言 pass >= 15 baseline | apps/api/tests/scripts/test_check_ship_report_regression.py |
| Baseline 锁 15 | 当前 11 mcp-v4-v1.4 + 4 followup-* 新模板 = 15, 14 老 followup-* + 32 mcp-v4-v1.0a/b 不计 | 同上 |
| 失败回滚指南 | 失败信息含 3 修法: 撤回 / 修老 / 升 baseline | 同上 |

## 4. 测试

测试策略: mock subprocess CLI 跑 (subprocess.run + re 解析摘要) / 真实 docs/ 扫 (CLI 行为)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | subprocess 跑 check_ship_report docs/ (absolute 路径) | pass=15 >= baseline 15 | ✅ PASSED |

**总: 1/1 测过**

**调试过程** (3 阶段):
1. 初始 import-based 测: pass=0 fail=51 (诡异, 手动 CLI pass=15)
2. 改 subprocess 测: pass=0 fail=51 (仍 0)
3. 修 NAME_PATTERN 隐性 bug (用 path.name 而非 str(path)): pass=15 ✅

**根因**: NAME_PATTERN `^docs/...` 只匹配 relative 路径, subprocess 传 absolute (`/Users/.../docs/...`) 全不 match → 全 fail。手动 CLI 传 `docs/` (relative) 才 work。修后 absolute/relative 都 work。

## 5. 退出门槛

- [x] scripts/check_ship_report.py NAME_PATTERN 改用 path.name (支持 absolute)
- [x] NEW_NAME_PATTERN 同步改
- [x] test_check_ship_report_regression.py 创建 (subprocess + baseline 15)
- [x] 1 测过 (pass=15)
- [x] health-check 11/11 保持

## 6. 未在范围

- Retrofit 14 老 followup-* ship report (估 0.5-1d, 推独立 PR)
- Retrofit 32 老 mcp-v4-v1.0a/b ship report (估 0.5-1d, 推独立 PR)
- 14 老 retrofit 后 baseline 可升 16, 32 retrofit 后再升 17 (一次性 +15, 推 G18 推后续)
- 改 NAMING 路径以 docs/ 开头 (当前 absolute OK, 不必改)

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| A G13-3/4 F13 B5 SQL 升级 Alembic 2.0 | 0.5d | P2 | momus v2 G13 session 2 第 1 项 |
| C G14 F15 test_server_restart_on_kill | 1-2d | P2 | 跨 supervisor + chaos + e2e 拆 2-3 PR |
| Retrofit 14 老 followup-* ship report | 0.5-1d | P3 | 完成后 baseline +14 = 29 |
| Retrofit 32 老 mcp-v4-v1.0a/b ship report | 0.5-1d | P3 | 完成后 baseline +32 = 61 |
| G18 跨 PR KPI + 测耗时 | 0.3-0.5d | P3 | momus v2 G18, 测耗时 16s 累积瓶颈 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 3 文件 — revert 自动删 2 新建 + 恢复 1 改)

- 不破坏 check_ship_report.py 现有 CLI 行为 (manual 跑仍 pass 15/36)
- 不影响 production code (纯 lint 工具)
- NAME_PATTERN 改是 bug 修复, revert 会恢复 隐性 bug (CLI absolute 路径全 fail)

## 9. 引用

- Refs: docs/mcp-v4-momus-audit-v2-2026-06-08.md (G18 推后续)
- Refs: 598d25d (F12 critical bug fix, 暴露本教训)
- Refs: 178865f (F12 ship, 暴露 critical bug)
- Refs: scripts/check_ship_report.py (A6 原始 9 章节 + 5 强约束检查, 本 PR 修 1 隐性 bug)
- Refs: apps/api/tests/scripts/test_chaos_drill.py (本 PR subprocess 模式参考)
