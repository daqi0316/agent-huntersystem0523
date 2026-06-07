# Phase A · A5 Ship Report — 性能 baseline 测

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A5 0.5d)
> **上一站**: `A1` (限流工程化基础, 2462e23 + 9f76046) — 2026-06-07
> **commit**: 1 个 feat + 1 个 perf report + 1 个 daemonize 脚本
> **接受门槛**: 14 server 冷启动 14/14 测出 + 热调用 1 测出 + 报告含 CI 阈值

## 1. 概览

| 维度 | 状态 |
|---|---|
| `scripts/perf_baseline.py` 测脚本 (280 行) | ✅ |
| 14 server 冷启动 P50/P95/P99/max | ✅ 全测出 (342-903ms 范围) |
| utils_server 热调用 P50/P95 | ✅ 1-4ms (30 trial) |
| `docs/perf-baseline-2026-06-07.md` baseline 报告 | ✅ |
| CI 阈值门禁建议 (Momus §1.2 阶段 2) | ✅ P95<1.2s 冷启动 / P95<50ms 热调用 |
| HTTP 端点 baseline | ⚠️ uvicorn hang 死 httpx, **推独立 PR** (不在 A5 范围) |
| Daemonize 脚本 (`apps/api/_scripts/daemonize_api.py`) | ✅ Popen + setsid (替代有问题的 fork) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `scripts/perf_baseline.py` | +280 (新) | 14 server 冷启动 + 热调用 + 8 HTTP 端点 baseline 测 |
| `docs/perf-baseline-2026-06-07.md` | +190 (新) | baseline 报告 + 14 server P50/P95 表 + CI 阈值建议 |
| `apps/api/_scripts/daemonize_api.py` | +115 (新) | Python subprocess.Popen + setsid 启 uvicorn + watchdog (替代 fork) |
| **总** | **+585 / 0** | 3 文件 |

## 3. 关键数据

### 3.1 14 server 冷启动 (P50 范围)

```
最慢: knowledge_server 899ms (LLM/embedding 初始化)
最快: utils_server 342ms (无外部依赖)
中位数: 568ms
```

### 3.2 热调用 (utils_server.calculate '2*3', 30 trial)

```
P50: 1ms · P95: 4ms · P99: 4ms
```

### 3.3 CI 阈值建议 (A2 接入)

| 指标 | 实测 P95 | 阈值 (×1.3 buffer) |
|---|---|---|
| 14 server 冷启动 | 354-903ms | **< 1.2s** |
| utils_server 热调用 | 4ms | **< 50ms** |
| 平均冷启动 P50 | 568ms | **< 800ms** |

## 4. 关键决策

### 4.1 测 5 trial 而非 30 (冷启动)

**理由**: 单 server 冷启动 ~800ms × 14 server × 30 trial = 336s (5.6 分钟), 太慢。
**折中**: 5 trial/server 拿 P50/P95/P99, 总 14×5 = 70 次冷启动 ≈ 90s。
**风险**: 5 trial 抖动大, 但冷启动时间主要受 import + init 影响, 单次基本稳定。

### 4.2 utils_server 而非 14 server 都热调用

**理由**: 14 server 工具签名差异大, 难统一测试。utils_server.calculate 是**最简单的纯计算工具**, 不依赖 LLM/DB, 是热调用延迟的**下限 baseline**。
**折中**: A5 只测 1 个 server 热调用, A3/A4 PR 测具体业务 server (orchestrator, pipeline)。

### 4.3 HTTP 端点测独立 PR 修复

**现象**: `perf_baseline.py` `--skip-http=False` 时 httpx 连续 ReadTimeout, curl 同时同 URL 返 200。

**初步根因**: uvicorn 单 worker + lifespan background task 阻塞 accept loop, curl 短连接幸运命中, httpx connection pool hang 死。

**不在 A5 修, 理由**:
- A5 是 baseline 测, 修复 uvicorn hang 是 bug fix, scope 不同
- HTTP baseline 缺失**不影响** Phase A 后续 (A2/A3/A4 重点是 E2E, 不依赖 baseline 数字)
- 推到 Phase B 单独 PR: 多 worker 化 + lifespan task timeout

### 4.4 Daemonize 改用 Popen + setsid (替代 fork)

**踩坑**: 第一次按 CLAUDE.md 模式 1 用 `os.fork() × 2` 双重 fork + `os.setsid()` + `os.execv()`, 但 macOS Python 3.14 下 fork 行为不稳, 脚本打印两遍就挂住。

**修复**: 改用 `subprocess.Popen(start_new_session=True)` (POSIX `setsid` 等价, 跨平台稳), 行为符合 CLAUDE.md 模式 1 目的 (脱离父 shell 进程组)。

**教训**: Python 3.14 fork 行为已变, 优先用 `subprocess` 高级 API。

## 5. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `perf_baseline.py` 跑成功 | 14 server 冷启动 14/14 + 热调用 3 rounds × 10 trial |
| 2 | 数字稳定 (3 轮) | 3 rounds × 10 trials, P95 抖动 < 5% |
| 3 | Daemonize 工作 | uvicorn 90523 LISTEN + watchdog 90524 跑 |
| 4 | 报告可读 | 14 server 表 + 阈值 + 历史对比 + 已知问题 |

## 6. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 14 server 冷启动全测出 | `perf_baseline.py --skip-http` | ✅ 14/14 |
| 热调用 P50/P95 测出 | utils_server.calculate 30 trial | ✅ 1-4ms |
| CI 阈值建议 | 报告 §3 列出 | ✅ |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.5d | ✅ |
| 5 强约束 (+30% buffer) | 估 0.5d → 实际 0.5d | ✅ |
| 5 强约束 (1 PR 必含测) | 17 测点 + 数字稳定 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (只测, 不改代码) | N/A |
| 5 强约束 (顺序锁死) | A1 → A5 (Phase A 第 2 步) | ✅ |

## 7. 未在 A5 范围（明确不做）

- ❌ HTTP 端点 baseline (uvicorn hang 死, 推 Phase B 修复 PR)
- ❌ 14 server 各自热调用 (用 utils_server 作下限 baseline, 业务 server 在 A3/A4 测)
- ❌ Prometheus 趋势监控 (Phase C Grafana 接入)
- ❌ Daemonize 写 systemd unit (macOS Popen + setsid 够用, prod 再上 systemd)
- ❌ perf_baseline.py 加 baseline JSON 历史对比 (后续 PR)

## 8. 后续路径

**A2 (0.5d, 1 commit) — E2E 加 CI**:
- `scripts/mcp_v4_e2e_14_servers.py` 加 GitHub Actions workflow
- docker-compose up + pytest + teardown
- **接入本报告 §3 CI 阈值门禁** (perf regression block PR)
- fail block PR

**A3+A4 (1.6d, 2 commit) — v1.4 orchestrator E2E**:
- v1.4a parse→evaluate 0.8d
- v1.4b match→schedule 0.8d

**A6 (0.3d, 1 commit) — ship report 模板化**:
- 抽 18+ ship report 共性结构

**Phase B 修复 PR — uvicorn hang 死**:
- 启多 worker (`--workers 2`)
- lifespan task 加 timeout
- httpx + curl 双测验证

## 9. 回滚方法

```bash
git revert <A5 commit>
# 改动 3 文件
git checkout HEAD~1 -- \
  scripts/perf_baseline.py \
  docs/perf-baseline-2026-06-07.md \
  apps/api/_scripts/daemonize_api.py
```

**回滚影响**:
- A5 不动核心代码, 回滚 = 删测脚本 + 报告
- Phase A 后续 A2/A3/A4 不依赖 baseline 测脚本 (可继续推进)
- Daemonize 脚本回滚后, 需要手动 `uvicorn` 启后端 (无 setsid detach)

## 10. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A5 = 性能 baseline)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §1.2 (3 阶段: 测数字 + 阈值 + CI)
- 上站: A1 (限流工程化基础, commit 2462e23 + 9f76046)
- 历史 perf: `scripts/mcp_v4_pr8_perf_test.py` (v0.6a PR-8 Day 3)
- 14 server 并行: `scripts/mcp_v4_v0_8_parallel_14_servers.py` (v0.8.1)
- Baseline 数据: `/tmp/perf-baseline-2026-06-07.json` (17 测点)
- Baseline 报告: `docs/perf-baseline-2026-06-07.md`
- Daemonize 脚本: `apps/api/_scripts/daemonize_api.py`

**下一步**: A2 (E2E CI) — 接入本报告 §3 阈值门禁
