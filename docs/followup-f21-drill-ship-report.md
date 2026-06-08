<!-- ship-report-template: g5-g8-v1 -->
# F21 Ship Report — Chaos Drill 强化 (3 硬故障 trigger + timing + 结构化报告) (1d, Phase C 收尾)

> momus v2 (2026-06-08) §G12 = F21 drill 唯一剩 Phase C 核心项, 1d
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G12 详细)
> 前一 PR: G11-2/3 (689859a) 防御 check 升级

## 1. 概览

| 维度 | 详情 | 状态 |
|---|---|---|
| 范围 | 1 文件改 (scripts/chaos-drill.sh) + 1 文件新建 (test_chaos_drill.py) + 1 文件新建 (本 report) | ✅ |
| 估时 | 1d 实际 (含 5 测调试) | ✅ |
| 测试 | 5 测全过: 脚本可执行 / 单 trigger DRY_RUN / 7 trigger < 5s / 语法 / 报告 KPI | ✅ |
| 风险 | L (drill 工具, 不影响 production) | ✅ |
| 健康 | health-check 11/11 保持 | ✅ |
| 5 强约束 | 1 PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / H 风险 rollback / 顺序锁死 | ✅ |
| KPI 维度 | ✅ 3 硬故障 ✅ timing ✅ 报告 ✅ 5 测 ✅ DRY_RUN ✅ 5 强约束 | 6 ✅ |

## 2. 背景

Phase C C2.3 "drill 故障定位 <5min" 1d 估, momus v2 §G12 标"唯一剩核心项"。原 P5-7 chaos-drill.sh 有 4 load/stress trigger (5xx/p99/db_pool/llm), 但缺 3 硬故障 + timing + 结构化报告。

- **2026-06-03 事故**: 改 enum 没跑 pytest, 线上 500 — drill 应能定位
- **2026-06-04 教训**: 改 B6 没跑 e2e, 真实后端不通 — drill 应能定位
- **F21 缺口**: drill 缺"DB down / uvicorn 死 / redis disconnect" 3 硬故障 trigger, 也缺 timing (5min 阈值无法验证)

## 3. 修法

| 子项 | 修法 | 文件 |
|---|---|---|
| 3 硬故障 trigger | `trigger_db_down` (docker compose stop postgres) / `trigger_uvicorn_dies` (pkill uvicorn) / `trigger_redis_disconnect` (docker compose stop redis) | scripts/chaos-drill.sh |
| 4 老 trigger DRY_RUN | 5xx/p99/db_pool/llm 加 DRY_RUN 跳过 (否则 1000+ HTTP 请求超时) | 同上 |
| Timing 工具 | `start_timer` / `elapsed_sec` 函数 + `verify_alert_with_timing` 5min polling | 同上 |
| 恢复验证 | `verify_recovery` 5min polling /health 200 (3 硬故障 trigger 必走) | 同上 |
| 报告生成 | `generate_drill_report` 输出 markdown, 含 5 KPI 维度 + 失败列表 + 改进点留白 | 同上 |
| DRY_RUN 模式 | DRY_RUN=1 跳过所有破坏性动作 + 5min verify + trigger 间 sleep | 同上 |
| 5 测覆盖 | scripts/__init__.py + test_chaos_drill.py 5 测 | apps/api/tests/scripts/ |

## 4. 测试

测试策略: mock subprocess bash 脚本 (subprocess.run + DRY_RUN=1) / 真报告文件检查 (Path.glob /tmp/chaos-drill-report-*.md)

| 测 | 输入 | 期望 | 结果 |
|---|---|---|---|
| 测 1 | 脚本存在 + 可执行 | assert SCRIPT.exists() + S_IXUSR | ✅ PASSED |
| 测 2 | DRY_RUN 单 trigger (db-down) | 秒返 + 报告合规 + momus G12 字段 | ✅ PASSED |
| 测 3 | DRY_RUN all (7 trigger) < 5s | 7 trigger_ 函数名全在 stdout | ✅ PASSED |
| 测 4 | bash -n 语法 | exit 0 | ✅ PASSED |
| 测 5 | 报告含 momus G12 5 KPI 维度 | 正则匹配 5 pattern | ✅ PASSED |

**总: 5/5 测过, 0.30s, 0 退化解**

## 5. 退出门槛

- [x] scripts/chaos-drill.sh 加 3 硬故障 trigger
- [x] Timing 工具函数 (start_timer, elapsed_sec)
- [x] 5min verify_alert_with_timing + verify_recovery
- [x] generate_drill_report 输出结构化 markdown
- [x] DRY_RUN 模式跨 4 老 + 3 新 trigger 一致工作
- [x] 5 测全过 (subprocess + 报告检查)
- [x] health-check 11/11 保持

## 6. 未在范围

- CI 自动跑 F21 drill (G13 F12 推后, 0.3d) — 本 PR 不接
- pre-commit hook 自动跑 (G13 F11 推后, 0.5d) — 同上
- 真触发 3 硬故障演练 — 由 operator 手动跑 (本 PR 仅 DRY_RUN 验证)
- 飞书 webhook 集成验证 — 现有监控/prometheus-alerts.yml 已有, 不在本 PR

## 7. 后续

| 项 | 估时 | 优先级 | 备注 |
|---|---|---|---|
| F21 真演练 (operator 手动跑) | 0.5d | P1 | 修本 PR 准备, 验证 5min 阈值真达标 |
| G13 F11-F14 retro-fit 4 项 | 1.6d | P1 | momus v2 G13 (含 F12 CI 接 chaos-drill) |
| G14 F15 PR-1a test_server_restart_on_kill | 1-2d | P2 | 跨 (supervisor + chaos + e2e) 拆 2-3 PR |
| G15 F6 mcp_host anyio lifecycle | 0.5-1d | P2 | root cause 真解 (4 测恢复但根因未解) |

## 8. 回滚

rollback: git revert HEAD~1..HEAD (1 个 commit, 3 文件 — revert 自动删除 2 新建 + 恢复 1 改)

- 不破坏 P5-7 老 4 trigger (新增 3 trigger + 老 trigger 仅加 DRY_RUN 检查, 不改主逻辑)
- 不影响 production code (drill 工具)
- DRY_RUN 跳过是新增行为, revert 后真演练照常

## 9. 引用

- Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` (G12 F21 详细)
- Refs: `docs/followups.md` (F21 + G12)
- Refs: `689859a` (G11-2/3 前一 PR, 防御 check)
- Refs: `4d2b083` (G11-1/3 ship report 模板升级)
- Refs: `4e99d30` (momus v2 ship, 推后续起点)
- Refs: `scripts/chaos-drill.sh` (P5-7 老 4 trigger, 本 PR 强化)
- Refs: `apps/api/app/scripts/api_watchdog.py` (uvicorn watchdog, verify_recovery 用)
- Refs: `monitoring/prometheus-alerts.yml` (告警规则, verify_alert 验指标)
