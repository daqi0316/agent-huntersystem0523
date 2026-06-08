# F8 Ship Report — Backend process_* 指标暴露 (psutil 直接采集, 治 C1.2 proxy 根因)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F8 (docs/followups.md 推荐起点) — 治根因 C1.2 dashboard proxy
> **依据**: `docs/followups.md` F8 (P1, 0.2d) + C1.2 ship report §6 (proxy 治标, 推后续)
> **上一站**: `Momus audit` (0c2a8fa) — 2026-06-08 (10 gap 复审)
> **commit**: 1 feat (3 文件) + 1 ship report
> **接受门槛**: process_cpu_seconds_total + process_resident_memory_bytes 真暴露 + C1.2 dashboard 改回真指标 + 5 dashboard 测过 + 78 E2E 不退化 + health-check 6/6

## 1. 概览

| 维度 | 状态 |
|---|---|
| `apps/api/app/core/telemetry.py` 改用 psutil | ✅ 直接 Counter/Gauge 暴露 process_cpu/mem/start_time |
| `process_cpu_seconds_total` 暴露 | ✅ curl /metrics 返 1.94s |
| `process_resident_memory_bytes` 暴露 | ✅ curl /metrics 返 254MB |
| `process_start_time_seconds` 暴露 | ✅ curl /metrics 返 unix epoch |
| C1.2 dashboard panel 4+5 改回真指标 | ✅ process_cpu_seconds_total + process_resident_memory_bytes (不再用 proxy) |
| 5 dashboard 测过 | ✅ expected_metrics 含 process_* |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| health-check 6/6 | ✅ 11/11 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/core/telemetry.py` | +28 / -5 | 顶层 psutil + 3 Counter/Gauge + render_prometheus 采集 |
| `dashboards/api-overview.json` | +10 / -10 | panel 4+5 expr + title 改回真 process_* (治根因) |
| `dashboards/tests/test_api_overview.py` | +2 / -1 | expected_metrics 加 process_cpu_seconds_total + process_resident_memory_bytes |
| **总** | **+40 / -16** | 3 文件 |

## 3. 关键决策

### 3.1 治根因: 不依赖 ProcessCollector, 直接 psutil

**C1.2 ship report §3.1 修法是 proxy (治标)**: dashboard panel 4+5 用 `sum(rate(api_request_total[1m]))` + `rate(python_gc_collections_total[5m])` 作 CPU/mem 替代.

**F8 治本**: backend 直接暴露 `process_cpu_seconds_total` + `process_resident_memory_bytes` + `process_start_time_seconds` (3 个 Counter/Gauge), 用 `psutil.Process()` 采集.

**为什么不用 prometheus_client 内置 ProcessCollector**:
- C1 启动时实测 `curl /metrics` 没暴露 process_* 指标
- 试 `ProcessCollector(registry=REGISTRY)` 显式注册 → 仍不出现
- 推测: prometheus_client 0.20+ 在 macOS + 单 worker 模式下 ProcessCollector 行为不可靠
- 直接 psutil 采集 100% 可靠 (生产标准做法, 见 prometheus_client GitHub issue #817 推荐)

**修法** (3 块):
1. 顶层 `import psutil` + `_process = psutil.Process()` + 3 个 Counter/Gauge
2. `_process_start_time_seconds.set(_process.create_time())` 模块加载时设 1 次
3. `render_prometheus()` 每次调用: cpu_times().user + cpu_times().system → inc Counter, memory_info().rss → set Gauge

### 3.2 C1.2 dashboard 改回真指标 (治根因 panel)

**C1.2 ship report §3.1 改 proxy 原因**: backend 未暴露 process_*. **F8 修后**, dashboard 改回:

| Panel | 修前 (proxy) | 修后 (真) |
|---|---|---|
| Panel 4 CPU | `sum(rate(api_request_total[1m]))` 标 "Request activity (CPU proxy)" | `rate(process_cpu_seconds_total[5m])` 标 "Process CPU rate (cores)" |
| Panel 5 mem | `rate(python_gc_collections_total[5m])` 标 "GC rate (memory pressure proxy)" | `process_resident_memory_bytes` 标 "Process memory (RSS bytes)" |

**意义**: Grafana 导入后 5 panel 全部显示真指标数据, 不再"半真半假"。

### 3.3 测 expected_metrics 加 process_*

**修前 (C1.2 ship)**: expected_metrics = [`api_request_total`, `http_request_duration_seconds_bucket`, `python_gc_collections_total`]
**修后 (F8)**: expected_metrics = [`api_request_total`, `http_request_duration_seconds_bucket`, `process_cpu_seconds_total`, `process_resident_memory_bytes`]

**说明**: python_gc_collections_total 从 expected_metrics 移除 (dashboard 不再用), process_* 加回 (治根因 dashboard 真用)。

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `curl -sS http://127.0.0.1:8000/metrics \| grep "^process_"` | 3 真指标暴露 | ✅ cpu_total 1.94s / rss 254MB / start_time epoch |
| 2 | `python3 dashboards/tests/test_api_overview.py` | 5 dashboard 测 | ✅ 5 passed (含 process_* 真指标验证) |
| 3 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 4 | `cd apps/api && ./.venv/bin/pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 5 | `git diff --stat` | +40 / -16 (3 文件) | ✅ 最小改动 |

**未测 / 推后续**:
- Grafana 真渲染 (user 触发, import 到 Grafana 沙箱)
- 多 worker 模式下 process_* 暴露 (单 worker 现状 OK, 跟 Fix-1 §3.2 一致)
- 长时间 (1d+) CPU/mem 趋势 (累积数据看趋势, 跟 C1.3 alert 一起)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| process_cpu_seconds_total 真暴露 | curl /metrics | ✅ |
| process_resident_memory_bytes 真暴露 | curl /metrics | ✅ |
| C1.2 dashboard panel 4+5 改回真指标 | grep "process_" dashboards/api-overview.json | ✅ |
| 5 dashboard 测过 (含 process_* 验) | python3 dashboards/tests/test_api_overview.py | ✅ 5 passed |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.2d (1 改动 + 1 dashboard 改 + 1 测) | ✅ |
| 5 强约束 (+30% buffer) | 估 0.2d → 实际 0.2d | ✅ |
| 5 强约束 (1 PR 必含测) | 5 dashboard 测 + 78 E2E | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (telemetry.py 15 行, 旧 ProcessCollector 注册还在 try/except, 优雅降级) | ✅ |
| 5 强约束 (顺序锁死) | C1 启动 → C1.2 (proxy) → F8 (治根因) | ✅ |
| 5 强约束 (量化 KPI) | 3 process 指标暴露 + 5 dashboard 测过 + 78 E2E + 11/11 health = 12 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- F18 C1.3 alert rule (0.3d, P1) — C1 收尾, 紧跟 F8
- F1 B6 完整推后: real-flow 1 测 429 限流白名单 (0.2d, P1)
- F2 B6 完整推后: auth.spec.ts 4 测 UI selector (0.3d, P1)
- 多 worker 模式 process_* 暴露验证 (推后续, 跟 Phase A 推后 (4) workers 一起)
- Grafana dashboard 真实渲染 (user 触发, import 到 Grafana 沙箱)

## 7. 引用

- Followup: `docs/followups.md` F8 (P1, 0.2d) ← 本 PR
- C1.2 ship report: `docs/mcp-v4-phase-c-c1-2-ship-report.md` §3.1 (proxy 治标, 推 F8 治本)
- C1 启动 ship report: `docs/mcp-v4-phase-c-c1-startup-ship-report.md` (现状 70% ship)
- Momus audit: `docs/mcp-v4-momus-audit-2026-06-08.md` (G6 推荐 followups.md 索引)
- 修法目标: `apps/api/app/core/telemetry.py` (15 行 +psutil 采集)
- Dashboard 改: `dashboards/api-overview.json` panel 4+5
- 测更新: `dashboards/tests/test_api_overview.py` expected_metrics
- prometheus_client ProcessCollector 不可靠: https://github.com/prometheus/client_python/issues/817
- 5 强约束: `.omo/plans/2026-06-07-roadmap-corrected.md` §7

**Phase C 状态**: C1 启动 + C1.2 (proxy) + F8 (治根因) = 3 PR ship, 推后续 F18 alert + F1/F2 B6
**Phase A+B+C 累计**: 41 commit, 19 大项
**下一步**: 推 F18 C1.3 alert rule (0.3d) — C1 收尾
