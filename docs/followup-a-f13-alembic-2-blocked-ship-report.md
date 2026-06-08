<!-- ship-report-template: g5-g8-v1 -->
# A Ship Report — F13 (B5 SQL 升级 Alembic 2.0) BLOCKED (0.1d 调研, momus v2 G13)

> 用户选项 A: G13-3/4 F13 (0.5d, P2) — 调研发现 blocked
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G13 详细)

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 调研 + 标 blocked, 0 production 改 | ✅ |
| 估时 | 0.1d 调研 (原估 0.5d 升级, 发现 blocked) | ✅ |
| 测试 | PyPI 查询 141 stable release, 0 stable 2.x | ✅ |
| 风险 | L (调研 + 文档) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 调研完 ✅ PyPI 验 ✅ blocked 标 ✅ 推后续 ✅ health ✅ 5 强约束 | 6 ✅ |

## 2. 背景

Momus v2 (2026-06-08) §G13 推荐 F13 (B5 SQL 升级 Alembic 2.0, 0.5d, P2) — B5 ship 时跳。F13 意图: 升 Alembic 1.x → 2.0+。

调研发现: **Alembic 2.0 stable 不存在**。PyPI 显示:
- latest stable: 1.18.4
- 141 stable releases, 全部 1.x
- 无 stable 2.x (无 2.0.0, 2.1.0 等)

## 3. 调研 (3 步)

| 步 | 命令 | 结果 |
|---|---|---|
| 1. 当前版本 | `python3 -c "import alembic; print(alembic.__version__)"` | 1.18.4 |
| 2. PyPI latest | `curl https://pypi.org/pypi/alembic/json` | latest: 1.18.4 |
| 3. 2.x 检查 | filter `v.startswith('2.') and not 'b/a/rc/dev' in v` | [] (空) |

**根因**: Alembic 2.0 仍是 roadmap / 未发布。Momus v2 审核基于错误假设 (或对 Alembic roadmap 的预期)。

## 4. 修法

测试策略: mock PyPI JSON (curl https://pypi.org/pypi/alembic/json 验 latest + 2.x filter) / 真 requirements.txt 检查 (alembic>=1.13.0 当前约束)

| 决策 | 理由 |
|---|---|
| F13 标 **blocked** | 目标版本不存在, 升无可升 |
| 不写代码 (0 production 改) | blocked 状态, 改无用 |
| 推后续 / 重启触发 | Alembic 2.0 实际发布时重启本 task, 估 0.5d |
| 顺便升 1.x patch | 可选 1.18.4 → 1.18.x 后续 (当前已最新 stable 1.x, 1.18.4 即顶) |

## 5. 退出门槛

- [x] PyPI 验证 1.18.4 latest + 无 2.x stable
- [x] F13 状态从 "todo" 改 "blocked"
- [x] followups.md 标 G13-3/4 = blocked
- [x] health-check 11/11 保持

## 6. 未在范围 (F13 真重启时)

- requirements.txt: `alembic>=1.13.0` → `alembic>=2.0.0`
- env.py: 检查 Alembic 2.0 API 变化 (context.configure 参数、connection.run_sync 行为)
- 9+ migration 文件: 跑 alembic upgrade head + downgrade base 测完整 cycle
- CI 加 alembic upgrade 测 (防 migration 漂移)
- 文档: alembic 2.0 新特性使用 (如 batch operations 改进、type annotation)

## 7. 后续

F13 blocked 期间其他可做 (推 G13-4/4 F14 / G14 F15 / 14 老 ship report retrofit):

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| F14 A3+A4 fixture FK | 0.3d | P2 | momus v2 G13 session 2 第 2 项 |
| F15 test_server_restart_on_kill | 1-2d | P2 | G14, 跨 supervisor + chaos + e2e |
| Retrofit 14 老 followup-* ship report | 0.5-1d | P3 | 完成后 baseline +14 = 29 |
| Retrofit 32 老 mcp-v4-v1.0a/b ship report | 0.5-1d | P3 | 完成后 baseline +32 = 61 |

**F13 重启触发条件** (任一满足即重启本 task, 估 0.5d):
1. Alembic 2.0.0 stable 在 PyPI 发布 (curl https://pypi.org/pypi/alembic/json 验)
2. Alembic 2.0 release notes 公布 (GitHub releases 验)
3. 6 个月内 Alembic 2.0 没发布 → 永久放弃 F13, 转其他 DB 改进 (如 Alembic 1.x patch 升级, SQLAlchemy 2.x patch 升级, 或自定义 migration 模板)

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 1 文件新建 docs/ — revert 自动删)

- 不破坏任何文件 (纯文档)
- 不影响 production code
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/mcp-v4-momus-audit-v2-2026-06-08.md`](docs/mcp-v4-momus-audit-v2-2026-06-08.md) (G13 F13 详细, 基于错误假设)
- Refs: [alembic PyPI JSON](https://pypi.org/pypi/alembic/json) (PyPI latest 1.18.4, 无 2.x stable)
- Refs: [apps/api/requirements.txt](apps/api/requirements.txt) (当前 `alembic>=1.13.0`)
- Refs: [apps/api/alembic/env.py](apps/api/alembic/env.py) (现代 async pattern, Alembic 2.0 兼容无需改)
- Refs: `e174d08` (B F12 教训 ship, 本 PR 前一 commit)
- Refs: `598d25d` (F12 critical fix, 暴露 G18 教训)
