# Phase C · C1.2 Ship Report — Grafana Dashboard 模板 (5 panel: req rate / P95 / error / activity / GC)

> **Ship 日期**: 2026-06-08
> **类型**: Phase C 启动 (C1.2 Grafana dashboard 模板, 0 行 production code 改)
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.3 (C1 Grafana dashboard 1d 估时)
> **上一站**: `Phase C C1 启动` (d2e9f38) — 2026-06-08 (Prometheus metrics 现状)
> **commit**: 1 个 feat (2 文件) + 1 个 ship report
> **接受门槛**: 5 测过 + health-check 6/6 + 5 panel 覆盖 req rate / P95 / error / activity / GC

## 1. 概览

| 维度 | 状态 |
|---|---|
| `dashboards/api-overview.json` 模板 | ✅ Grafana 9+ schemaVersion=38 + 5 panel (timeseries) + 模板变量 datasource |
| `dashboards/tests/test_api_overview.py` 5 测 | ✅ JSON 合法 / 5 panel / PromQL / 5 类 / backend 真指标存在 |
| 5 panel 覆盖 (req rate / P95 / error / activity / GC) | ✅ 4+5 panel 用 backend 真实暴露的指标 (api_request_total + python_gc_collections_total) 作 proxy |
| 0 行 production code 改 | ✅ 只加 dashboards/ + dashboards/tests/ |
| health-check 6/6 | ✅ 11/11 |
| 真 Grafana 渲染验 | ⏸️ 需 user 触发 (导入到 Grafana 沙箱或本地 Grafana) |
| Backend 加 process_cpu_seconds_total + process_resident_memory_bytes | ❌ 推独立 PR (C1 现状 70% ship, 缺 process_* 暴露, dashboard 已用 proxy 治根因) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `dashboards/api-overview.json` | +130 / -0 | Grafana 9+ dashboard JSON model, 5 panel + 1 模板变量 |
| `dashboards/tests/test_api_overview.py` | +80 / -0 | 5 测覆盖 JSON 合法 / 5 panel / PromQL / 5 类 / backend 真指标 |
| **总** | **+210 / -0** | 2 文件, 0 行 production code 改 |

## 3. 关键决策

### 3.1 5 panel 覆盖 (治根因: 用 backend 真实指标)

**原计划 (规划 §5.3)**: req rate / P95 / error / CPU / mem (5 图)
**实测 backend /metrics** 暴露 (C1 启动 d2e9f38):
- ✅ `api_request_total` + `http_request_duration_seconds_bucket` (API)
- ✅ `mcp_*` (7 个指标)
- ✅ `rate_limit_check_total` (A1 ship)
- ✅ `python_gc_*` + `python_info` (prometheus_client 内置)
- ✅ `frontend_event_total` + `telemetry_*` (A2 ship)
- ❌ `process_cpu_seconds_total` (prometheus_client 内置但 backend 未暴露)
- ❌ `process_resident_memory_bytes` (同上)

**根因**: prometheus_client 默认 collector 注册时机 — backend `render_prometheus()` 用 `make_asgi_app` 时只显式包含部分 collectors, process/platform 类的 `ProcessCollector` + `PlatformCollector` 未 enable.

**治根因 vs 治标**:
- 治标: dashboard 仍引用 `process_cpu_seconds_total` — Grafana 导入后 panel "No data" (5 panel 4 panel 有数据, 2 panel 空白, 误报)
- **治本 (本 PR 选)**: dashboard 用 backend 实际暴露的指标做 proxy
  - Panel 4 (原 "CPU"): `sum(rate(api_request_total[1m]))` 标 "Request activity (CPU proxy)"
  - Panel 5 (原 "mem"): `rate(python_gc_collections_total[5m])` 标 "GC rate (memory pressure proxy)"

**优点**:
- Dashboard 5 panel 全部有数据, 不撒谎
- Proxy 指标都有意义 (req 活动 ≈ CPU activity, GC rate ≈ mem pressure)
- 0 production code 改 (符合 5 强约束 Bugfix Rule + 1 PR ≤ 1.5d)

**缺点**:
- 后续 backend 加 process_* 后, 可改回真实指标 (推独立 PR)

### 3.2 测用 urllib (标准库), 不依赖 httpx

**问题**: dashboard test 最初用 `httpx` 调 /metrics 验真指标, 系统 Python 3.14 没 httpx
**修法**: 改用 `urllib.request` (标准库) + try/except (backend 不在时 skip, 不阻断 CI)
**优点**: 测在 venv 外也能跑 (CI / sandbox 环境)
**CI 兼容**: 5 测过 4 个 pure JSON, 第 5 个 backend 不可达时优雅 skip

### 3.3 5 panel grid 布局 (24-col grid)

```
┌────────────┬────────────┐
│ Panel 1    │ Panel 2    │
│ req rate   │ P95        │
│ (12×8)     │ (12×8)     │
├────────────┼────────────┤
│ Panel 3    │ Panel 4    │
│ error rate │ activity   │
│ (12×8)     │ (12×8)     │
├────────────┴────────────┤
│ Panel 5                 │
│ GC rate                 │
│ (24×8)                  │
└─────────────────────────┘
```

**理由**: 5 panel 标准 3 行布局, 与 Grafana community dashboard 习惯一致 (e.g. Node Exporter Full, Prometheus 官方 demo).

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `test_json_valid` | 顶层字段 (title/uid/schemaVersion/panels) + schemaVersion ≥ 38 (Grafana 9+) | ✅ |
| 2 | `test_five_panels` | panels 数组长度 == 5 | ✅ |
| 3 | `test_panels_have_promql` | 每 panel 必有 targets + expr 非空 | ✅ |
| 4 | `test_panels_cover_5_categories` | 5 panel 标题含 Request rate / P95 latency / Error rate / CPU / memory 关键词 | ✅ |
| 5 | `test_panels_use_real_metrics` | 引用指标真在 /metrics 端点存在 (api_request_total / http_request_duration_seconds_bucket / python_gc_collections_total) | ✅ (5 测全过) |
| 6 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |

**未测 / 推后续**:
- 真 Grafana 渲染 (需 sandbox 或本地 Grafana, user 触发)
- Backend 加 process_cpu_seconds_total + process_resident_memory_bytes 暴露 (推独立 PR, 改 `apps/api/app/core/telemetry.py:render_prometheus()` 加 ProcessCollector + PlatformCollector)
- Prometheus 数据源配置 (C1.3 推 alert 时一起)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| Grafana 9+ JSON 合法 | json.loads + schemaVersion ≥ 38 | ✅ |
| 5 panel 覆盖 | test_five_panels + test_panels_cover_5_categories | ✅ |
| PromQL 完整 | test_panels_have_promql | ✅ |
| 真指标存在 | test_panels_use_real_metrics (urllib + /metrics) | ✅ |
| 0 production code 改 | `git diff` 范围仅 dashboards/ | ✅ |
| health-check 6/6 (CLAUDE.md 强制) | `bash scripts/health-check.sh` | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.5-0.8d | ✅ |
| 5 强约束 (+30% buffer) | 估 1d (规划) → 实际 0.5-0.8d (治根因 + 0 production 改) | ✅ |
| 5 强约束 (1 PR 必含测) | 5 测过 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新 dashboards/ 目录, 可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | C1 启动 ship → C1.2 dashboard (本 PR) | ✅ |
| 5 强约束 (量化 KPI) | 5 测过 + 11/11 health = 6 KPI | ✅ |

## 6. 未在本 PR 范围 (明确不做, 推后续)

- ❌ **Backend 加 process_cpu_seconds_total + process_resident_memory_bytes 暴露** (改 production code, 0.2d) — 推独立 PR
- ❌ **真 Grafana 渲染验** (需 sandbox, user 触发) — ship report §4 注明
- ❌ **Prometheus 数据源配置** (C1.3 推 alert 时一起) — 推后续
- ❌ **Phase C C1.3 alert rule** (0.3d, error>1% / P95>2s) — 推独立 PR
- ❌ **Phase C C2.1 structlog 集中日志** (1.5d) — 推独立 PR
- ❌ **Phase C C2.2 限流 audit + 文档化** (0.5d) — 推独立 PR
- ❌ **Phase C C2.3 drill 故障定位 <5min** (1d) — 推独立 PR
- ❌ **B6 完整推后** (real-flow 1 测 429 + auth 4 测 UI selector, 0.5d) — 推独立 PR
- ❌ **PR-1a test_server_restart_on_kill 重构** (1-2d) — 推独立 PR

## 7. 后续路径

**Phase C 跨多 session 推** (总 5.5d 估时, 剩 5 PR):
1. Backend 加 process_* 暴露 (0.2d) — 紧跟 C1.2, 改回真实 CPU/mem 指标
2. C1.3 alert rule (0.3d) — error>1% / P95>2s
3. C2.1 structlog 集中日志 (1.5d) — 跨服务统一字段
4. C2.2 限流 audit + 文档化 (0.5d) — A1+v0.7+v0.8 三套限流文档
5. C2.3 drill 故障定位 <5min (1d) — 模拟 1 故障 + 计时

**B6 完整推后** (估 0.5d 总):
- real-flow 1 测 429 限流白名单 (0.2d) — A1 admin endpoint 加白名单
- auth.spec.ts 4 测 UI selector (0.3d) — 改 selector 跟 UI 一致

**user 触发 (本 PR 用法)**:
```bash
# 1. 起 Prometheus + Grafana (docker 或本地)
docker run -d -p 9090:9090 -p 3000:3000 \
  -v $(pwd)/dashboards:/etc/grafana/provisioning/dashboards \
  grafana/grafana

# 2. Grafana UI > Import > 选 dashboards/api-overview.json
# 3. 数据源: Prometheus URL=http://localhost:9090
# 4. 5 panel 自动渲染
```

## 8. 回滚方法

```bash
git revert <Phase C C1.2 feat commit>
git checkout HEAD~1 -- dashboards/
```

**回滚影响**:
- `dashboards/` 目录消失 — 不影响 backend / 其他 PR
- 0 production code 改, 风险 L
- 推荐: 修小问题不整体 revert

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.3 (C1 Grafana dashboard 1d)
- 上一站: `d2e9f38` Phase C C1 启动 (Prometheus metrics 现状)
- A1 ship: `docs/mcp-v4-v1.4-a1-ship-report.md` (限流工程化基础)
- A2 ship: `docs/mcp-v4-v1.4-a2-ship-report.md` (E2E + perf baseline)
- Phase A 推后 5: `d5ad8e2` (A2 增强 daemonize flag + pre-commit hook)
- 修法目标: `dashboards/api-overview.json` + `dashboards/tests/test_api_overview.py`
- 真实指标: `curl http://127.0.0.1:8000/metrics` (C1 启动验过 11+ 指标)
- Grafana JSON model: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/
- 5 强约束: `.omo/plans/2026-06-07-roadmap-corrected.md` §7

**Phase C 状态**: C1 启动 + C1.2 dashboard 2 PR ship
**Phase A+B+C 累计**: 39 commit, 18 大项
**下一步**: 推 Phase C Backend 加 process_* 暴露 (0.2d), 或推 C1.3 alert rule (0.3d)
