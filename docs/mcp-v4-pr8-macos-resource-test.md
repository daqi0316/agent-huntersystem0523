# MCP v4 PR-8 macOS 资源测报告

> **测时**: 2026-06-06
> **场景**: 5 个模拟 MCP server subprocess 稳态内存
> **结论**: ✅ < 2GB 稳态 → §5 预算成立，**进 PR-8**

## 1. 测试目的

§8 决策点：
- < 2GB → §5 预算成立，进 PR-8
- 2-4GB → 砍 1 pilot 工具
- > 4GB → §6.1 重做门槛触发

## 2. 测试环境

| 项 | 值 |
|---|---|
| Platform | darwin (macOS) |
| Python | 3.14.3 |
| 物理内存 | 32.0 GB |
| venv | `apps/api/.venv`（含 pydantic + sqlalchemy + mcp[cli]）|
| 测试脚本 | `scripts/mcp_v4_pr8_macos_resource_test.py` |

## 3. 测试方法

每个 subprocess 启动后做：
1. import pydantic / sqlalchemy / mcp.server.fastmcp（真实 MCP server 启动开销）
2. 实例化 FastMCP server
3. sleep 30s（模拟空闲等待）

**关键**：用的是 `apps/api/.venv/bin/python`（真 venv，fastmcp 等已装），不是系统 python。模拟的是真实 server 启动的开销，不是空 Python。

## 4. 实测结果

| 采样点 | 状态 |
|---|---|
| T+0s | spawn 5 个 subprocess |
| T+3s（启动后） | 5 个全 alive，平均 RSS = 87.7 MB/个 |
| T+8s（稳态） | 5 个仍 alive，**总 RSS = 438.1 MB**（稳态，无明显增长）|

**单进程均值**: 87.7 MB
**总稳态**: 438.1 MB
**占物理内存比**: 1.4%（32GB 机器）

## 5. 对比 §5 预算

| 指标 | 预算 | 实测 | 状态 |
|---|---|---|---|
| 内存稳态（5 subprocess）| < 2GB | **438 MB** | ✅ 4.5x 余量 |

## 6. 关键观察

1. **实际远低于理论值**：supervisor.py 设的 `RLIMIT_AS=512MB` 是 hard cap，不是实际占用。实测 ~88MB 是因为：
   - Python 解释器基线 ~30MB
   - 库 import（pydantic + sqlalchemy + fastmcp）~50MB
   - 业务代码未加载（工具函数未 import）
2. **稳态无增长**：T+3s 和 T+8s 都是 438MB，无内存泄漏迹象（短观察期，需更长时间验证）
3. **冷启动开销未计入**：5 个并发 spawn ~1s 完成（脚本测的延迟 0.1s/subprocess）

## 7. PR-9 scale 推算

PR-8 是 2 工具（calc + weather）= 2 subprocess。

PR-9 计划 scale 到 13+ subprocess（v3 plan §4.2 拆分粒度）。基于本测 88MB/subprocess：
- 13 × 88MB = 1.14GB（仍在 2GB 预算内）
- 保守估 20 × 88MB = 1.76GB（贴近 2GB 上限）
- 25 × 88MB = 2.2GB（超 2GB，需 Type B 拆 wrapper 时合并 server）

**推论**：PR-9 scale 上限约 20 subprocess。超过则考虑：
- Type A/B 合并到同一 server（按业务域）
- supervisor 启动 phase 控流（lazy 阶段只 call 时拉起）

## 8. 风险 + 待验证

| 风险 | 状态 | 后续 |
|---|---|---|
| 短测 8s 内存稳定，更长时间是否泄漏？ | 未验证 | PR-8 跑 24h 看 trend |
| 实际 MCP call 时内存峰值（带 result / 临时对象）| 未测 | §9 observability 加 `mcp_server_peak_memory_mb` gauge |
| 真实业务工具（DB + LLM client）import 完是不是仍 ~88MB？| 未测 | PR-8 启动 calc + weather 真 server 测 |
| macOS RLIMIT_AS 实际生效？| 未验 | 测一个超 512MB 进程看 OOM 是否触发 |

## 9. 决策

✅ **进 PR-8 Day 1**（host.py 改造）

**保留 Day 0.5 任务**（PR-8 pilot 时同步做）：
- 跑 calc + weather 真 server 看实际 memory（不是模拟 subprocess）
- 验证 supervisor RLIMIT_AS 实际行为（构造一个超限工具测）
- 长跑 24h 内存 trend（PR-8 ship 前夜跑）

## 10. 测试脚本归档

脚本: `scripts/mcp_v4_pr8_macos_resource_test.py`
可重跑：`.venv/bin/python scripts/mcp_v4_pr8_macos_resource_test.py`（在 apps/api/）
输出: stdout（人类可读）+ 可加 `--json` 输出 Prometheus 格式
