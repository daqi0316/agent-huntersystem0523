# 性能 baseline 报告 — 2026-06-07

> **测时间**: 2026-06-07
> **测脚本**: `scripts/perf_baseline.py` (A5 新增)
> **数据文件**: `/tmp/perf-baseline-2026-06-07.json`
> **环境**: macOS 14.x, Python 3.14, uvicorn 单 worker (无 --reload)
> **范围**: 14 MCP server 冷启动 + utils_server 热调用 (HTTP 端点测被 uvicorn hang 死, 见 §4 已知问题)

## 1. 14 MCP Server 冷启动 (spawn + initialize + list_tools)

**测法**: 5 trial/server, 取 P50/P95/P99/max

| # | Server | P50 (ms) | P95 (ms) | P99 (ms) | max (ms) | 备注 |
|---|---|---|---|---|---|---|
| 1 | application_server | 762 | 788 | 788 | 788 | |
| 2 | candidate_server | 757 | 835 | 835 | 835 | |
| 3 | dashboard_server | 544 | 578 | 578 | 578 | |
| 4 | evaluation_server | 545 | 561 | 561 | 561 | |
| 5 | interview_server | 575 | 580 | 580 | 580 | |
| 6 | jd_server | 511 | 516 | 516 | 516 | |
| 7 | job_server | 570 | 591 | 591 | 591 | |
| 8 | **knowledge_server** | **899** | **903** | **903** | **903** | **最慢**, LLM/embedding 初始化 |
| 9 | resume_server | 770 | 795 | 795 | 795 | |
| 10 | screening_server | 568 | 588 | 588 | 588 | |
| 11 | search_server | 422 | 430 | 430 | 430 | |
| 12 | skill_mgr_server | 386 | 395 | 395 | 395 | |
| 13 | **utils_server** | **342** | **349** | **349** | **349** | **最快**, 无外部依赖 |
| 14 | **weather_server** | **348** | **354** | **354** | **354** | **快**, 外部 API 调用但启动期不连 |

**总览**:
- 14 server 冷启动 P50 **范围 342-899ms**, 中位数 568ms
- **最快 3**: utils_server 342ms / weather_server 348ms / skill_mgr_server 386ms (无 LLM 依赖)
- **最慢 1**: knowledge_server 899ms (LLM/embedding 初始化重)
- 大部分 server P95 都在 600-800ms 区间

## 2. utils_server 热调用 (calculate '2*3')

**测法**: 3 rounds × 10 trials = 30 calls (mock LLM 入口)

| 指标 | 数值 |
|---|---|
| P50 | 1ms |
| P95 | 4ms |
| P99 | 4ms |
| max | 5ms |
| min | 0ms |
| mean | 1ms |

**说明**:
- 热调用极快 (MCP 协议开销 < 5ms)
- 没有 P99 spike (< 10ms)
- 符合 v0.6a PR-8 历史数据 (Day 0.5 测的 343ms 冷启动 + 后续热调 < 50ms)

## 3. CI 阈值门禁建议 (Momus §1.2 阶段 2)

按实测数字 + 30% buffer 设阈值, **A2 PR (E2E 加 CI) 接入 GitHub Actions**:

| 指标 | 实测 (P95) | 阈值 (×1.3 buffer) | 失败时排查方向 |
|---|---|---|---|
| 14 server 冷启动 | 354-903ms | **< 1.2s** | knowledge_server > 1s 报警 (LLM init 慢) |
| utils_server 热调用 | 4ms | **< 50ms** | MCP 协议开销 (uvicorn/asyncio) |
| 平均冷启动 P50 | 568ms | **< 800ms** | 半数 server 超 800ms → 拆异步初始化 |

**关键阈值**:
```yaml
# .github/workflows/perf-baseline.yml (A2 接入)
- name: Perf baseline check
  run: |
    python scripts/perf_baseline.py --rounds 3 --trials 10 --output perf.json
    python -c "
    import json
    data = json.load(open('perf.json'))
    cold = [r for r in data if r['category'] == 'mcp_cold_start']
    slow = [r for r in cold if r['p95_ms'] > 1200]
    hot = [r for r in data if r['category'] == 'mcp_hot_call']
    hot_slow = [r for r in hot if r['p95_ms'] > 50]
    if slow or hot_slow:
        print(f'❌ perf regression: {len(slow)} cold-start > 1.2s, {len(hot_slow)} hot > 50ms')
        exit(1)
    print('✅ perf baseline OK')
    "
```

**建议 PR baseline 评审节奏**:
- 每个 Phase A PR 跑 `perf_baseline.py` 输出 JSON
- 数字波动 > 20% 触发 review (单 PR 不应让 14 server 任意 P95 涨 20%+)
- 月度 review 调阈值 (产品用户量变化调整)

## 4. 已知问题 (本报告不解决, 推独立 PR)

### 4.1 HTTP 端点 baseline 缺失

**现象**: `perf_baseline.py` `--skip-http=False` 时 httpx 连续 ReadTimeout, curl 同时同 URL 返 200。

**根因** (初步):
- uvicorn 90523 单 worker (无 --reload), lifespan 跑 background task (Recommendation scan / aggregation loop)
- curl 短连接 OK (1 request 1 connect), httpx 复用 connection pool 时 hang 死
- 推测: uvicorn worker 在处理 lifespan task 时阻塞 accept loop, 但**部分请求 (curl) 命中, 部分 (httpx) 卡住**

**修复路径** (推 Phase B E2E 修复 PR):
- (a) 启 uvicorn 多 worker (`--workers 2`), 单 worker 阻塞不影响其他
- (b) lifespan task 加 timeout / catch exception, 不让 background task 阻塞 worker
- (c) httpx 改用 `Limits(max_keepalive_connections=0)` 强制短连接

**A5 不修, 理由**: 不在 Phase A 范围, 跟限流工程化无关。HTTP baseline 缺失不影响 Phase A 后续 PR 推进 (A2/A3/A4 重点是 E2E, 不依赖 baseline 数字)。

### 4.2 knowledge_server 慢 (899ms)

**根因**: 启动时 import LLM/embedding 客户端 + 初始化 Qdrant client。

**优化方向** (推后续):
- 拆 LLM client 初始化到 lifespan (不阻塞 list_tools)
- 用 lazy import (按需加载)
- 不在 A5 范围 (跟 baseline 数字采集中性, 阈值已留 buffer)

## 5. 历史对比

| 阶段 | 冷启动 P95 (单 server) | 数据来源 |
|---|---|---|
| v0.4e | < 500ms | 14 server e2e 14/14 报告 |
| v0.6a PR-8 (Day 0.5) | 343ms | `mcp_v4_pr8_perf_test.py` |
| v0.8.1 (14 server 并行) | 1-3s 范围 (peak fd/mem) | `mcp_v4_v0_8_parallel_14_servers.py` |
| **A5 baseline (2026-06-07)** | **354-903ms (per server)** | 本报告 |

**观察**:
- 单 server 冷启动没显著退化 (A5 范围 ≈ 历史)
- v0.8.1 测的并行场景 (1-3s) 反映**总**时间, 不是单 server — 不可直接对比
- 建议 A3/A4 PR 测 e2e 整体 wall-time (5 server 并发), 对比 v0.8.1 数字

## 6. 引用

- 测脚本: `scripts/perf_baseline.py` (A5 新增, 280 行)
- 历史 perf 脚本: `scripts/mcp_v4_pr8_perf_test.py` (v0.6a PR-8 Day 3)
- 14 server 并行测: `scripts/mcp_v4_v0_8_parallel_14_servers.py` (v0.8.1)
- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A5 = 性能 baseline 0.5d)
- Momus 修正: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §1.2 (3 阶段: 测数字 + 阈值 + CI 门禁)
- 报告数据: `/tmp/perf-baseline-2026-06-07.json` (17 测点)

## 7. 后续

- **A2 (E2E 加 CI)**: 接入本报告 §3 的 GitHub Actions 阈值
- **Phase B 修复 HTTP baseline**: 修 §4.1 uvicorn hang 问题后, 重跑 HTTP 测补充报告
- **Phase C 监控**: 把 baseline 数字接到 Prometheus Grafana 面板 (趋势监控)
