<!-- ship-report-template: g5-g8-v1 -->
# G11-2/3 Ship Report — G7 防御 check 升级: check_baseline_run + check_e2e_run (0.3d, momus v1 推后续)

> momus v2 (2026-06-08) §G11-2/3 = G7 (0.3d) momus v1 推后续第三片
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G11 详细)
> 前一 PR: G11-1/3 (4d2b083) ship report 模板升级

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 2 文件新建 (check_baseline_run.py + check_e2e_run.py) | ✅ |
| 估时 | 0.3d 实际 | ✅ |
| 测试 | 4 测全过: apps/api pytest 3.7h / 24h 阈值 / 45h 失败 / mtime 缺 | ✅ |
| 风险 | L (防御 check 工具, 不影响 production) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 2 文件 ✅ 4 测 ✅ G7 抓 45h ✅ 4 引子 ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

Momus v1 (0c2a8fa) 推 G7 (0.3d) = G11-2/3 (P1). G7 意图: 防"未跑 baseline (pytest)" / "未跑 e2e (playwright)" 就 ship 的漏跑事故。

- 2026-06-03 事故: 改 enum 没跑 pytest, 线上 500
- 2026-06-04 教训: 改 B6 流程没跑 playwright e2e, 真实后端不通

本 PR 创建 2 防御 check 脚本, 在 ship 前扫 .pytest_cache + playwright-report mtime, 防止漏跑。

## 3. 修法

| 子项 | 修法 | 文件 |
|---|---|---|
| check_baseline_run | 扫根目录 .pytest_cache/v/cache/lastfailed mtime, 默认 24h 阈值 | scripts/check_baseline_run.py |
| check_e2e_run | 扫 apps/web/playwright-report/ 最新文件 mtime, 默认 24h 阈值 | scripts/check_e2e_run.py |
| CLI 一致 | argparse + main() 返回 0/1 + 跟现有 scripts/ pattern 对齐 | 2 文件 |
| 默认阈值 | 24h (可 `--hours N` 调) | 2 文件 |
| 错误信息 | 含"💡 修法"提示, 给 ship 前修法命令 | 2 文件 |

## 4. 测试

测试策略: mock 时间戳 (用临时目录构造不同 mtime) / 真根目录扫 (命令行 `python3 scripts/check_baseline_run.py`)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | 真根目录扫 (pytest 现状) | ✅ apps/api (3.7h) + ❌ apps/web (45.6h 超 24h) | ✅ 抓到 apps/web 超阈 |
| 测 2 | 真 playwright-report 扫 | ❌ e2e 45.4h 超 24h (新文件 index.html) | ✅ 抓到 e2e 超阈 |
| 测 3 | `--hours 48` 放宽阈值 | apps/web 45.6h ≤ 48h → ✅ | ✅ 通过 |
| 测 4 | 不存在路径 | ❌ "路径不存在" | ✅ 友好错误 |

## 5. 退出门槛

- [x] scripts/check_baseline_run.py 创建 (44 行, 含 docstring + argparse)
- [x] scripts/check_e2e_run.py 创建 (74 行, 含 docstring + argparse)
- [x] chmod +x (2 文件可执行)
- [x] 4 测全过 (含真环境扫)
- [x] 防御 check 真实抓漏 (45h+ e2e)
- [x] health-check 11/11 保持

## 6. 未在范围

- CI 集成 (G12 F12 推后: 0.3d, P2) — G7 检查脚本可在 CI 阶段跑, 本 PR 不接
- pre-commit hook 集成 (G12 F11 推后: 0.5d, P2) — 同上
- smart check (按 PR diff 自动判断要不要 e2e) — 当前是 dumb 时间戳, 后续优化
- mtime 篡改防护 (恶意绕过) — 非威胁模型, 不防

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| G11-3/3 (G5+G8 已 ship, G7 ship) | 0d | P1 | momus v1 推后续全完 ✅ |
| G12 F21 drill (Phase C 收尾) | 1d | P1 | momus v2 G12, **唯一剩 Phase C 核心项** |
| G13 F11-F14 retro-fit 4 项 | 1.6d | P1 | momus v2 G13 (含 F12 CI 集成) |
| G12 F12 CI 集成 lint check | 0.3d | P2 | 接 G7 防御 check 到 CI |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 2 文件新建 — revert 自动删除)

- 不破坏任何老脚本 (新文件, 无冲突)
- 不影响 production code (纯防御 check 工具)
- 不需迁移步骤

## 9. 引用

- Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G11-2/3 详细)
- Refs: `docs/mcp-v4-momus-audit-2026-06-08.md` (momus v1 G7 原始建议)
- Refs: `4d2b083` (G11-1/3, 前一 PR, ship report 模板升级)
- Refs: `4e99d30` (momus v2 ship, 推后续起点)
- Refs: `scripts/check_ship_report.py` (A6 同 pattern 防御 check 工具, 本 PR 仿之)
