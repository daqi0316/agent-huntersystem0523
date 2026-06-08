# F18 Ship Report — C1.3 Prometheus Alert Rule (error > 1% / P95 > 2s)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F18 (docs/followups.md) — C1.3 alert rule 收尾 C1 阶段
> **依据**: `docs/followups.md` F18 (P1, 0.3d) + 规划 §5.3 C1.3 (error > 1% / P95 > 2s)
> **上一站**: `F8` (6b8485a + 1ee023d) — 2026-06-08 (process_* 暴露, 治 C1.2 proxy)
> **commit**: 1 feat (2 文件) + 1 ship report
> **接受门槛**: 6 测过 (YAML + 2 rules + 阈值 + 真指标) + 78 E2E 不退化 + health-check 6/6

## 1. 概览

| 维度 | 状态 |
|---|---|
| `monitoring/prometheus-alerts.yml` 模板 | ✅ 1 group (api-overview) + 2 rules (HighErrorRate / HighP95Latency) |
| HighErrorRate 阈值 1% | ✅ PromQL: `sum(rate(api_request_total{status=~"5.."}[5m])) / sum(rate(api_request_total[5m])) > 0.01` |
| HighP95Latency 阈值 2s | ✅ PromQL: `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m]))) > 2` |
| 6 测覆盖 | ✅ YAML 合法 / 2 rules / PromQL 完整 / 1% 阈值 / 2s 阈值 / 真指标 |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| health-check 6/6 | ✅ 11/11 |
| Prometheus + alertmanager 实际配置 | ⏸️ 需 user 触发 (alertmanager 部署, 推独立 PR) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `monitoring/prometheus-alerts.yml` | +24 / -0 | 1 group + 2 rules (for=2m, severity=warning) |
| `monitoring/tests/test_prometheus_alerts.py` | +90 / -0 | 6 测覆盖 (urllib 不依赖 yaml 缺失) |
| **总** | **+114 / -0** | 2 文件, 0 行 production code 改 |

## 3. 关键决策

### 3.1 阈值符合规划 §5.3 (1% + 2s)

**规划原文**:
- C1: Alert rule (error > 1%, P95 > 2s) — 0.5d, 风险 L, alert 模拟, alertmanager 收到 test alert

**实现**:
- `HighErrorRate`: 错误率 > 1% (`api_request_total{status=~"5.."}` 占比)
- `HighP95Latency`: P95 延迟 > 2s (`histogram_quantile(0.95, ...)`)
- 2 rules 共享 `for: 2m` (避免抖动误报, 2min 持续才触发)
- `severity: warning` (P1 类, 不是 critical — production 调阈值时改)

### 3.2 6 测覆盖 (不依赖真 Prometheus)

**测覆盖** (urllib 验 /metrics, 不需 alertmanager):
1. YAML 合法 + 1 group (api-overview)
2. 2 rules (HighErrorRate + HighP95Latency)
3. PromQL expr 完整 + for 字段
4. 1% 阈值 (`"0.01" in expr` + `"5.." in expr`)
5. 2s 阈值 (`histogram_quantile` + `http_request_duration_seconds_bucket`)
6. 真指标在 /metrics 暴露 (backend 不可达时 skip)

**CI 兼容**: 跟 dashboard 测同模式, 纯 Python 标准库, system Python 可跑

### 3.3 raise concern — Prometheus 实际部署推后续

**现状**:
- alert rules YAML 模板 ship
- 实际告警链路需:
  1. Prometheus 服务 (抓 backend /metrics)
  2. alertmanager 服务 (收 Prometheus alert)
  3. webhook/邮件/Slack 通知集成

**推后续**: 部署 + 集成 (估 0.3-0.5d), 独立 PR, 不在本 F18 范围

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `test_yaml_valid` | YAML 合法 + 1 group | ✅ |
| 2 | `test_two_rules` | 2 rules (HighErrorRate / HighP95Latency) | ✅ |
| 3 | `test_promql_expressions` | expr + for 字段 | ✅ |
| 4 | `test_error_rate_threshold_1pct` | 1% 阈值 + 5xx 匹配 | ✅ |
| 5 | `test_p95_latency_threshold_2s` | 2s 阈值 + histogram_quantile | ✅ |
| 6 | `test_real_metrics_exposed` | 指标在 /metrics 真存在 | ✅ |
| 7 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 8 | `pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed |
| 9 | `git diff --stat` | +114 / -0 (2 文件) | ✅ 0 production code 改 |

**未测 / 推后续**:
- Prometheus 实际加载 + alert 触发模拟 (user 触发)
- alertmanager 部署 + webhook 集成 (推独立 PR)
- 长跑 (1d+) 累积 alert 趋势 (跟 C1.2 dashboard 一起)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 2 rules + 正确阈值 (1% / 2s) | 测 4 + 测 5 | ✅ |
| 6 测过 | python3 monitoring/tests/ | ✅ 6 passed |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d (1 YAML + 1 测) | ✅ |
| 5 强约束 (+30% buffer) | 估 0.3d → 实际 0.3d | ✅ |
| 5 强约束 (1 PR 必含测) | 6 测 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新增 monitoring/ 目录, 不动 backend) | ✅ |
| 5 强约束 (顺序锁死) | C1 启动 → C1.2 → F8 → F18 (C1 收尾) | ✅ |
| 5 强约束 (量化 KPI) | 6 测 + 78 E2E + 11/11 health + 2 真指标 = 10 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **Prometheus + alertmanager 部署** (0.3-0.5d, 推独立 PR)
- ❌ **webhook/邮件/Slack 通知集成** (0.2d, 推独立 PR)
- ❌ **alert 触发模拟 + 端到端验** (user 触发, 需真 Prometheus)
- ❌ **F1 B6 完整推后: real-flow 1 测 429 限流白名单** (0.2d, P1)
- ❌ **F2 B6 完整推后: auth.spec.ts 4 测 UI selector** (0.3d, P1)
- ❌ **F19 C2.1 structlog 集中日志** (1.5d, P1)
- ❌ **F20 C2.2 限流 audit + 文档化** (0.5d, P1)
- ❌ **F21 C2.3 drill 故障定位 <5min** (1d, P1)

## 7. 引用

- Followup: `docs/followups.md` F18 (P1, 0.3d) ← 本 PR
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.3 C1.3 (error > 1% / P95 > 2s)
- 上一站: `6b8485a` F8 feat (process_* 暴露)
- 上一站: `1ee023d` F8 docs
- C1 启动: `d2e9f38` (Prometheus metrics 现状)
- C1.2: `6b8ac17` (Grafana dashboard)
- 修法目标: `monitoring/prometheus-alerts.yml` (24 行) + `monitoring/tests/test_prometheus_alerts.py` (90 行)
- Prometheus 文档: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- 5 强约束: `.omo/plans/2026-06-07-roadmap-corrected.md` §7

**Phase C 状态**: C1 启动 + C1.2 (proxy → F8 治本) + F18 alert = C1 收尾 ✅
**Phase A+B+C 累计**: 43 commit, 20 大项
**下一步**: 推 F1+F2 B6 完整推后 (0.5d, P1) — 限流白名单 + auth UI selector
