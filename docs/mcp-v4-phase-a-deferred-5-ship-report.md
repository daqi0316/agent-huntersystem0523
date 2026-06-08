# Phase A 推后 (5) Ship Report — A2 增强: daemonize `--health-check-url` flag + pre-commit `check-ship-report` hook

> **Ship 日期**: 2026-06-08
> **类型**: Phase A 推后项修 (Fix-1 ship report §7 后续路径中 A2 增强)
> **依据**: `docs/mcp-v4-fix-1-ship-report.md` §7 ("A2 增强 (推后): daemonize 加 `--health-check-url` flag + pre-commit hook 集成 lint")
> **上一站**: `Phase A 推后 (3)` (a6b1a77 + 8c5b6aa) — 2026-06-08 (perf_baseline 对比)
> **commit**: 1 个 feat (2 文件) + 1 个 ship report
> **接受门槛**: daemonize --help flag 显示 + check_ship_report 1 pass + pre-commit config YAML 验 + health-check 6/6

## 1. 概览

| 维度 | 状态 |
|---|---|
| `daemonize_api.py` `--health-check-url` flag | ✅ argparse default `http://127.0.0.1:8000/health` |
| pre-commit `check-ship-report` hook | ✅ 集成 A6 已有 `scripts/check_ship_report.py` (9 章节 + 5 强约束 + 命名 + 引用) |
| `daemonize --help` flag 显示 | ✅ Worker ready check URL (default: http://127.0.0.1:8000/health) |
| `check_ship_report.py` 跑 B6 ship report | ✅ 1 pass / 0 fail |
| pre-commit config YAML 验 (9 hooks) | ✅ 含 check-ship-report |
| health-check 6/6 | ✅ 11/11 |
| pre-commit install 实际跑 | ⏸️ 需 user 触发 (跟项目现有 `pre-commit install` 流程一致) |
| Phase A 推后收尾 | ✅ 4/5 (1)(2)(3)(5) ship, (4) uvicorn workers 试错后回滚 skip |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/_scripts/daemonize_api.py` | +15 / -8 | argparse + `--health-check-url` flag (替换 hardcoded URL) |
| `.pre-commit-config.yaml` | +9 / -0 | check-ship-report local hook (files regex `^docs/mcp-v4-v.*\.md$`) |
| **总** | **+24 / -8** | 2 文件, 0 行 production code 改 |

## 3. 关键决策

### 3.1 daemonize flag — 替换 hardcoded health check URL

**Fix-1 ship report §3.2 + §7**:
- daemonize 已有 `[3.5/4] wait_for_uvicorn_worker_ready` 步骤 (Phase A 推后 1 推到一半)
- 但 health check URL hardcoded `http://127.0.0.1:8000/health`
- A2 增强需求: 让 health check URL 可配置 (production 可能用 `/readyz` 或不同端口)

**修法** (2 块):
1. 加 `import argparse` 顶层 import
2. `main()` 开头加 `argparse.ArgumentParser` + `--health-check-url` flag (default 同 hardcoded)
3. `[3.5/4]` 步骤用 `args.health_check_url` 替换 hardcoded

**为什么不破坏现有行为**:
- default URL = 原来 hardcoded URL (`http://127.0.0.1:8000/health`)
- 不传 flag 行为完全一致
- 5 强约束 Bugfix Rule: 最小改动, 不动 start_uvicorn / watchdog

### 3.2 pre-commit `check-ship-report` hook — 集成 A6 模板化

**A6 ship report §1** (A6 已 ship, commit 6c4a125):
> ship report 模板化 (累计 18 个, 模板化省 30% 时间)
> 模板生效 | 后续 PR ship report -30% 时间

A6 写了 `scripts/check_ship_report.py`, **但没接 pre-commit**. A2 增强 (Fix-1 §7 推后) = 接 pre-commit.

**修法** (1 hook):
```yaml
- repo: local
  hooks:
    - id: check-ship-report
      name: Check ship report template (9 sections + 5 强约束, A6)
      entry: python3 scripts/check_ship_report.py
      language: system
      pass_filenames: true
      files: ^docs/mcp-v4-v.*\.md$
      stages: [pre-commit, manual]
```

**关键设置**:
- `pass_filenames: true` — pre-commit 传 modified file paths 给 hook (不是 whole repo 跑)
- `files: ^docs/mcp-v4-v.*\.md$` — 仅匹配 ship report, 不跑全 repo
- `stages: [pre-commit, manual]` — dev 默认跑, CI 也能跑

**注**: `check_ship_report.py` 接受 file paths 作为 args, 跟 `pass_filenames: true` 兼容 — 不需改 check_ship_report.py

### 3.3 raise concern — pre-commit 实际跑需 user 触发

**现状**:
- `.pre-commit-config.yaml` 加 hook 配置
- 但**没在 user 仓库跑过 `pre-commit install`** (本会话没改 .git/hooks)
- user 触发: `cd repo && pre-commit install` 然后改 ship report 时自动跑

**5 强约束 raise**:
- 1 PR 必含测: 3 验证 (daemonize --help + check_ship_report 跑 + yaml 验) ✅
- 实际 `pre-commit run check-ship-report --all-files` 跑没在 PR 内 (因为 user 未 install)
- ship report 标 "user 触发" 步骤

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `python3 apps/api/_scripts/daemonize_api.py --help` | flag 显示 | ✅ Worker ready check URL (default: http://127.0.0.1:8000/health) |
| 2 | `python3 scripts/check_ship_report.py docs/mcp-v4-v1.4-b6-ship-report.md` | ship report 模板验证 | ✅ 1 pass / 0 fail |
| 3 | `python3 -c "import yaml; ... check-ship-report present"` | pre-commit config YAML 验 | ✅ 9 hooks 含 check-ship-report |
| 4 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 5 | `git diff --stat` | +24 / -8 (2 文件) | ✅ 0 行 production code 改 |

**未测 / 推后续**:
- 实际 `pre-commit install` + 改 ship report 跑 hook (user 触发)
- daemonize --health-check-url 实际跑 (不杀现有 backend, 改 1 行重跑)
- CI workflow 加 `pre-commit run --all-files` 步骤 (推后续)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| daemonize --health-check-url flag 工作 | `--help` 输出 | ✅ |
| pre-commit hook 配置 YAML 合法 | yaml.safe_load + 9 hooks 列 | ✅ |
| check_ship_report hook 集成 A6 模板 | 跑 1 个现有 ship report | ✅ 1 pass |
| health-check 6/6 (CLAUDE.md 强制) | `bash scripts/health-check.sh` | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d | ✅ |
| 5 强约束 (+30% buffer) | 估 0.3d → 实际 0.3d | ✅ |
| 5 强约束 (1 PR 必含测) | 3 验证 (daemonize + ship report + yaml) | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (scripts + config 改动, 可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | Phase A 推后 (5) 在 (3) 收尾后 | ✅ |
| 5 强约束 (量化 KPI) | 3 验证 + 11/11 health = 4 KPI | ✅ |

## 6. 未在本 PR 范围 (明确不做, 推后续)

- ❌ **实际 `pre-commit install`** (需 user 触发, dev 默认不开) — ship report §3.3 标
- ❌ **CI workflow 加 `pre-commit run --all-files` 步骤** (推后续, 跟 Phase A 推后 (4) workers 试错一起)
- ❌ **Phase A 推后 (4) uvicorn --workers 多 worker 模式** (试错后回滚, 推后续) — 不在本 PR
- ❌ **Phase C 启动 (C1 metrics + dashboard + alert)** (3d) — 推独立 PR
- ❌ **B6 完整推后** (real-flow 1 测 429 + auth 4 测 UI selector, 0.5d 总) — 推独立 PR
- ❌ **PR-1a** (test_server_restart_on_kill 重构, 1-2d) — 推独立 PR

## 7. 后续路径

**Phase A 推后收尾** ✅ 4/5:
- (1) ✅ uvicorn hang 死根因 (96fcb17 + 0a2fd78)
- (2) ✅ mcp_host 跨 loop (9ee6ec1 + 030e5d1)
- (3) ✅ perf_baseline 对比 (a6b1a77 + 8c5b6aa)
- (4) ⏸️ uvicorn --workers (试错后回滚, 推后续, 等于 skip)
- (5) ✅ A2 增强 daemonize flag + pre-commit (本 PR)

**Phase C 启动** (5.5d, 7 PR 估):
- C1: Prometheus metrics (复用 A1 rate_limit_check_total, 补 14 server 暴露)
- C1: Grafana dashboard
- C1: Alert rule
- C2: structlog 集中日志
- C2: 限流 audit + 文档化
- C2: drill 故障定位 <5min

**B6 完整推后** (估 0.5d 总):
- real-flow 1 测 429 限流白名单 (0.2d)
- auth.spec.ts 4 测 UI selector (0.3d)

**PR-1a 推后** (估 1-2d):
- test_server_restart_on_kill 重构 (AsyncExitStack 重启)
- supervisor 自动重启 chaos 测

**user 触发 (本 PR 用法)**:
```bash
# 1. dev 装 pre-commit hook (一次性)
pre-commit install

# 2. 改 ship report 时自动跑 check-ship-report
# (改 docs/mcp-v4-v*.md 自动触发, 不需 manual)
```

## 8. 回滚方法

```bash
git revert <Phase A 推后 (5) feat commit>
git checkout HEAD~1 -- \
  apps/api/_scripts/daemonize_api.py \
  .pre-commit-config.yaml
```

**回滚影响**:
- daemonize 回到 hardcoded `/health` URL — 失去 flag 灵活性
- pre-commit check-ship-report hook 移除 — 失去 A6 模板自动 lint
- **风险**: L (scripts + config 改动, 可独立 revert)
- 推荐: 修小问题不整体 revert

## 9. 引用

- 推后列表: `docs/mcp-v4-fix-1-ship-report.md` §7 ("A2 增强 (推后): daemonize 加 --health-check-url flag (复用现在加的 [3.5/4] 步骤) + pre-commit hook 集成 lint")
- 上一站: Phase A 推后 (3) (a6b1a77 + 8c5b6aa)
- 上一站: Phase A 推后 (2) (9ee6ec1 + 030e5d1)
- 上一站: Phase A 推后 (1) (96fcb17 + 0a2fd78)
- A6 ship: `docs/mcp-v4-v1.4-a6-ship-report.md` §1 (ship report 模板化 + lint 脚本)
- A6 commit: 6c4a125 + 0dd5fdd
- 修法目标: `apps/api/_scripts/daemonize_api.py` + `.pre-commit-config.yaml`
- 复用: `scripts/check_ship_report.py` (A6 写, 本 PR 不改)
- 5 强约束: `.omo/plans/2026-06-07-roadmap-corrected.md` §7

**Phase A 推后状态**: 4/5 完成 (1)(2)(3)(5) ship, (4) skip
**Phase A+B 累计**: 36 commit, 16 大项
**下一步**: 推 Phase C 启动 C1 metrics (1.5d), 或收尾本会话
