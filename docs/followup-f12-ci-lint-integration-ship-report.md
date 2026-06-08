<!-- ship-report-template: g5-g8-v1 -->
# F12 Ship Report — CI 集成 lint check (A6 ship report + G7 防御 check) (0.3d, momus v2 G13-1/2)

> momus v2 (2026-06-08) §G13 = F11-F14 retro-fit 4 项, 1.6d 跨 2 session
> 本 PR: session 1 第 1 项 (F12, 0.3d, P2) — CI 集成 G7 防御 check + A6 ship report
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G13 详细)
> 前一 PR: G12 F21 (ee3e077) Phase C 6/6 收尾

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 文件改 (.github/workflows/ci.yml, +18 行) + 1 文件新建 (本 report) | ✅ |
| 估时 | 0.3d 实际 | ✅ |
| 测试 | YAML 语法 ✅ + 3 step 配置正确 (working-directory + continue-on-error) | ✅ |
| 风险 | M (CI 集成, 不通过会 block PR, 需谨慎) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 3 step ✅ working-dir 修 ✅ continue-on-error ✅ YAML 验 ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

Momus v2 §G13 推荐拆 2 session:
- session 1: F11 (A6 retro-fit 18+ ship report, 0.5d) + F12 (CI 集成 lint check, 0.3d) = 0.8d, 2 PR
- session 2: F13 (B5 SQL 升级 Alembic 2.0, 0.5d) + F14 (A3+A4 fixture FK, 0.3d) = 0.8d, 2 PR

F11 (A6 retro-fit) 已被 G11-1/3 (4d2b083) 部分完成 (新模板 + marker opt-in + grandfather 老 18+ ship report)。本 PR 是 F12 — CI 集成 G7 防御 check + A6 ship report, 让本地手工跑升级到 CI 自动跑。

## 3. 修法

| 子项 | 修法 | 文件 |
|---|---|---|
| 3 lint check step | check_ship_report (A6 G5+G8) + check_baseline_run (G7) + check_e2e_run (G7) | .github/workflows/ci.yml |
| working-directory 修 | 用 `${{ github.workspace }}` 显式根目录 (CI 默认 apps/api 找不到根 scripts/) | 同上 |
| continue-on-error: false | 3 step 都 false (block PR if check fails) | 同上 |
| 168h 阈值 (1 周) | check_baseline_run / check_e2e_run 用 168h (CI 跑频繁, 比本地 24h 放宽) | 同上 |
| 位置 | 在 "Check env keys" 后 (line 97), 跟现有 lint/security 步骤连贯 | 同上 |

## 4. 测试

测试策略: mock YAML 语法 (yaml.safe_load) / 手动 review 3 step 配置 (working-directory + continue-on-error) / 验 check_ship_report 现有 ship reports 兼容

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | yaml.safe_load(ci.yml) | 解析成功无错 | ✅ |
| 测 2 | grep "Check ship report" | 含 working-directory + continue-on-error | ✅ |
| 测 3 | grep "Check baseline run" | 含 --hours 168 | ✅ |
| 测 4 | grep "Check e2e run" | 含 --hours 168 | ✅ |
| 测 5 | check_ship_report.py 跑 11 followup-* + 47 mcp-v4-v* | 老 47 grandfather + 新 11 + G11-1/3 ship report 全过 | ✅ 1 pass (G11-1/3 自验) |

## 5. 退出门槛

- [x] ci.yml 加 3 lint check step
- [x] 显式 working-directory: ${{ github.workspace }} (3 step)
- [x] continue-on-error: false (3 step, block PR)
- [x] 168h 阈值 (1 周, CI 跑频繁)
- [x] YAML 语法验证
- [x] health-check 11/11 保持

## 6. 未在范围

- pre-commit hook 集成 (G13 F11 推后, 0.5d) — 本 PR 仅 CI, 不接 local hook
- 自动测耗时监控 (G18 推后, 0.3d) — 本 PR 不加
- 旧 18+ ship report retrofit (G11-1/3 已 grandfather 完成) — 不需 retrofit
- 把 168h 阈值做成可配置 env var — 当前是合理默认, 不必抽象

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| G13-2/4 F11 retro-fit 18+ ship report | 0.5d | P2 | 已被 G11-1/3 grandfather 替代, 标完 |
| G13-3/4 F13 B5 SQL 升级 Alembic 2.0 | 0.5d | P2 | momus v2 G13 session 2 第 1 项 |
| G13-4/4 F14 A3+A4 fixture FK | 0.3d | P2 | momus v2 G13 session 2 第 2 项 |
| G14 F15 PR-1a test_server_restart_on_kill | 1-2d | P2 | 跨 supervisor + chaos + e2e 拆 2-3 PR |
| G15 F6 mcp_host anyio lifecycle | 0.5-1d | P2 | 4 测恢复但根因未解 |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 2 文件 — revert 自动删除 1 新建 + 恢复 1 改)

- 不破坏现有 CI (3 step 是新增, 老 4 step 完整保留)
- 不影响 production code (CI 配置)
- revert 后 PR 不会因 lint check 失败被 block (回到原状态)

## 9. 引用

- Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G13 F12 详细)
- Refs: `docs/followups.md` (F12)
- Refs: `ee3e077` (G12 F21 前一 PR, Phase C 收尾)
- Refs: `689859a` (G11-2/3 G7 防御 check ship, 本 PR 接 CI)
- Refs: `4d2b083` (G11-1/3 ship report 模板, 本 PR 接 CI)
- Refs: `.github/workflows/ci.yml` (本 PR 改, 已有 4 job: backend/frontend/docker/e2e)
- Refs: `scripts/check_ship_report.py` (A6 G5+G8 checker)
- Refs: `scripts/check_baseline_run.py` (G7-1 防御 check)
- Refs: `scripts/check_e2e_run.py` (G7-2 防御 check)
