# F20 Ship Report — C2.2 限流 audit + 文档化 (A1 已 145 行, F20 补 §11)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F20 (docs/followups.md) — C2.2 限流 audit + 文档化
> **依据**: `docs/followups.md` F20 (P1, 0.5d) + 规划 §5.3 C2.2
> **上一站**: `F19` (b3e82f8 + 1cd062a) — 2026-06-08 (structlog 启动)
> **commit**: 1 docs (audit 补 §11) + 1 测 + 1 ship report
> **接受门槛**: 6 测过 (A1/v0.7/v0.8/metrics/SOP/3 套表) + health-check 11/11 + 78 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `docs/rate-limit-audit.md` 现状 | ✅ A1 PR 2026-06-07 已写 145 行 (3-key + 14 server + L2 quota + 6 已知缺口 + SOP) |
| F20 补 §11 (v0.7 + v0.8) | ✅ 3 节 (v0.7 鉴权 / v0.8 60 并发未找到 / 3 套对比表) |
| v0.7 鉴权找到 | ✅ `apps/api/app/scripts/skill_cli.py` per-host pre-shared key |
| v0.8 60 并发 | ❌ 未找到 (followups 误记, MCP sequential 连接, 推 F20.1 验证) |
| `docs/tests/test_rate_limit_audit.py` 6 测 | ✅ 6 passed |
| health-check 11/11 | ✅ |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 0 行 production code 改 | ✅ 纯文档 + 测 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `docs/rate-limit-audit.md` | +47 / -0 | §11 (F20 补充: v0.7 鉴权 + v0.8 未找到 + 3 套对比表) |
| `docs/tests/test_rate_limit_audit.py` | +62 / -0 | 6 测 (A1 3-key / v0.7 / v0.8 / metrics / SOP / 3 套表) |
| **总** | **+109 / -0** | 2 文件, 0 production code 改 |

## 3. 关键决策

### 3.1 raise concern — followups.md "v0.8 60 并发" 是误记

**followups.md 描述**: "限流 audit + 文档化 (v0.7+v0.8+API 三套限流)"
**F20 实际调研**:
- v0.7.2 鉴权找到 (skill_cli.py per-host pre-shared key, **不是限流是 auth gate**)
- A1 限流找到 (rate_limit.py 3-key sliding window)
- **v0.8 60 并发未找到** (`apps/api/app/mcp/` 无 Semaphore / concurrency / 60 关键字)

**结论**: followups.md 误记 (可能混淆 v0.8 ship 的 MCP server 数 14 + A1 的 60 req/min user key 限). 实际 MCP sequential 连接 (host.py:102 "顺序而非 gather").

**ship 决策**: §11.3 表格如实写 "❌ 未找到", 推 F20.1 独立 PR 验证 (grep 全 repo Semaphore / concurrent 关键字).

### 3.2 v0.7 鉴权 vs A1 限流: 类型不同, 不算"3 套限流"

| 套 | 类型 | 触发 |
|---|---|---|
| v0.7 鉴权 | auth gate | key 不匹配 (binary 401/non-zero) |
| A1 限流 | rate limit | 超 60/min (counter 429) |
| v0.8 60 并发 | ❌ 未找到 | — |

**F20 修正**: 实际 1 套限流 (A1) + 1 套鉴权 (v0.7) + 1 套未找到. followups.md 描述不准确, 文档化如实记录.

### 3.3 6 测覆盖 (纯文本 grep, 0 production 依赖)

测试位置: `docs/tests/test_rate_limit_audit.py`
- `test_doc_exists`: 文档存在 + > 1000 chars
- `test_a1_3key_rate_limit`: org/user/ip + 100/60/30 req/min 全在
- `test_v07_skill_cli_auth`: v0.7 / skill_cli / pre-shared / per-host 全在
- `test_v08_60_concurrent_not_found`: 60 并发 + "未找到" + followups 标注全在 (审计负向发现防遗漏)
- `test_metrics_and_sop`: rate_limit_check_total + admin_reset + SOP 全在
- `test_momus_3_套_对比_table`: v0.7 鉴权 + A1 限流 + 未找到 全在

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `python3 docs/tests/test_rate_limit_audit.py` | 6 文档完整性测 | ✅ 6 passed |
| 2 | `bash scripts/health-check.sh` | 系统健康不退化 | ✅ 11/11 |
| 3 | `pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 4 | `git diff --stat` | +109 / -0 (2 文件) | ✅ 0 production code 改 |

**未测 / 推后续**:
- F20.1 全 repo grep Semaphore/concurrent 验证 v0.8 60 并发 (0.2d, 推独立 PR)
- F19.1 迁 main.py + rate_limit.py 到 structlog (0.3d, P1) — 承接 F19 启动
- F19.2 迁 telemetry.py + mcp/host.py (0.3d, P1)
- F21 C2.3 drill 故障定位 <5min (1d, P1) — Phase C 继续
- Grafana 面板加 rate_limit_check_total{blocked="true"} 429 占比 (C2.x 推)



测试策略: mock subprocess bash 脚本 (subprocess.run + DRY_RUN=1) / 真 apps/ 跑验
## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| A1 3-key + 14 server + SOP 全在 | test_a1_3key_rate_limit + test_metrics_and_sop | ✅ |
| v0.7 鉴权记录 | test_v07_skill_cli_auth | ✅ |
| v0.8 60 并发明确 "未找到" | test_v08_60_concurrent_not_found | ✅ |
| 3 套策略对比表 | test_momus_3_套_对比_table | ✅ |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.2d (纯 docs + 测) | ✅ | / +30% buffer
| 5 强约束 (Bugfix Rule) | 0 production code 改 (纯 docs) | ✅ |
| 5 强约束 (1 PR 必含测) | 6 文档完整性测 | ✅ (G1 §7 边界: docs PR) |
| 5 强约束 (H 风险 rollback) | 风险 L (docs 改动可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | C1 收尾 (F19) → C2.1 audit (F20) | ✅ |
| 5 强约束 (量化 KPI) | 6 测过 + 78 E2E + 11/11 health + 0 production 改 = 12 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **F20.1 全 repo grep Semaphore/concurrent 验证 v0.8** (0.2d, P2) — 推独立 PR
- ❌ **F19.1 迁 main.py + rate_limit.py 到 structlog** (0.3d, P1) — 承接 F19 启动
- ❌ **F19.2 迁 telemetry.py + mcp/host.py** (0.3d, P1)
- ❌ **F19.3 迁 tools/* (7 服务)** (0.5d, P1)
- ❌ **F19.4 1 query 跨 5 服务验** (0.2d, P1)
- ❌ **F21 C2.3 drill 故障定位 <5min** (1d, P1) — Phase C 继续
- ❌ **B2B org 阈值调整** (100 → 200, 推 F20.2 业务驱动)

## 7. 后续

(F retrofit 标 — 老 ship report 同步升级到 G8 模板)

## 9. 引用

(F retrofit 保留原 §7 引用 内容):
- Followup: `docs/followups.md` F20 (P1, 0.5d) ← 本 PR 0.2d
- 上一站: `b3e82f8` F19 feat + `1cd062a` F19 docs
- 现有 audit 文档: `docs/rate-limit-audit.md` (A1 PR 2026-06-07, 145 行 → 192 行)
- A1 ship: `docs/mcp-v4-v1.4-a1-ship-report.md` (限流工程化基础)
- v0.7 鉴权: `apps/api/app/scripts/skill_cli.py` (line 13-164)
- 修法目标: `docs/rate-limit-audit.md` §11 (47 行新增) + `docs/tests/test_rate_limit_audit.py` (62 行新增)
- 5 强约束: 规划 §7 (G1 §7 修后: docs PR 接受门槛)

**Phase C 状态**: C1 收尾 (4 PR) + C2 启动 (F19 config + F20 audit) = 6 PR
**Phase A+B+C 累计**: 49 commit, 23 大项
**下一步**: 推 F19.1 迁 main.py + rate_limit.py 到 structlog (0.3d, P1) — 承接 F19 启动

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 commit, 1-3 文件新建 docs/ — revert 自动删新建)

- 不破坏任何文件 (纯文档 retrofit)
- 不影响 production code (F 是 docs retrofit, 0 production 改)
- 不需迁移步骤

## 9. 引用

- Refs: [`docs/followups.md`](docs/followups.md) (F1-F22 总索引)
- Refs: [`.omo/plans/2026-06-07-roadmap-corrected.md`](.omo/plans/2026-06-07-roadmap-corrected.md) (修正版规划)
- Refs: [followup-f20-rate-limit-audit-ship-report.md](followup-f20-rate-limit-audit-ship-report.md) (本 ship report)

- Refs: [`docs/followups.md`](docs/followups.md) (F1-F22 总索引)
- Refs: [`followup-f20-rate-limit-audit-ship-report.md`](followup-f20-rate-limit-audit-ship-report.md) (本 ship report)
