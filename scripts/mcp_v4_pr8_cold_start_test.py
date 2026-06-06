"""MCP v4 PR-8 冷启动基线测 — Day 0.5 M-2

目的：v0.3 §8.5 — 测"spawn subprocess → session.initialize() 返回"时长
对照预算：v0.3 §5 — 冷启动 P95 < 2s

测法：
  1. spawn 1 subprocess (utils_server.py) × 10 次
  2. 每次测完整 cold start 时长
  3. 输出 P50 / P90 / P95 / P99 / max / mean
  4. 对照 §5 预算给决策
"""
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_MODULE = "app.mcp_servers.builtin.utils_server"
PYTHON_BIN = str(PROJECT_ROOT / "apps/api/.venv/bin/python")
SUBPROCESS_CWD = str(PROJECT_ROOT / "apps/api")
TRIALS = 10
PER_TRIAL_TIMEOUT_S = 10


async def measure_one_cold_start(idx: int) -> float:
    """单次 cold start：spawn + initialize，返回毫秒数

    注意：ClientSession 必须 `async with` 启动 receive_loop（v4 impl report §2.2 坑）。
    """
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=["-m", SERVER_MODULE],
        cwd=SUBPROCESS_CWD,
    )

    t0 = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            t_ready = time.perf_counter()

    elapsed_ms = (t_ready - t0) * 1000
    return elapsed_ms


async def run_with_timeout(coro, timeout_s: float, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError:
        raise TimeoutError(f"{label} 超时 ({timeout_s}s)")


async def main():
    print("=== MCP v4 PR-8 Day 0.5 冷启动基线测 ===")
    print(f"Target:  P95 < 2000ms (v0.3 §5)")
    print(f"Server:  {SERVER_MODULE}")
    print(f"Python:  {PYTHON_BIN}")
    print(f"Cwd:     {SUBPROCESS_CWD}")
    print(f"Trials:  {TRIALS}, per-trial timeout: {PER_TRIAL_TIMEOUT_S}s")
    print()

    durations_ms: list[float] = []
    failures: list[tuple[int, str]] = []

    for i in range(TRIALS):
        try:
            d = await run_with_timeout(
                measure_one_cold_start(i),
                PER_TRIAL_TIMEOUT_S,
                f"trial #{i}",
            )
            durations_ms.append(d)
            print(f"  trial #{i:2d}: {d:7.1f} ms")
        except Exception as e:
            failures.append((i, str(e)[:200]))
            print(f"  trial #{i:2d}: FAILED — {str(e)[:100]}")

    if not durations_ms:
        print("\n❌ 所有 trial 失败，无法给基线")
        sys.exit(1)

    print()
    durations_sorted = sorted(durations_ms)
    n = len(durations_sorted)

    def pct(p: float) -> float:
        if n == 1:
            return durations_sorted[0]
        idx = max(0, min(n - 1, int(p / 100 * n)))
        return durations_sorted[idx]

    p50 = pct(50)
    p90 = pct(90)
    p95 = pct(95)
    p99 = pct(99) if n >= 20 else durations_sorted[-1]
    mean = statistics.mean(durations_ms)
    mx = max(durations_ms)
    mn = min(durations_ms)
    stdev = statistics.stdev(durations_ms) if n > 1 else 0.0

    print("=== 结果 ===")
    print(f"  min:    {mn:7.1f} ms")
    print(f"  mean:   {mean:7.1f} ms")
    print(f"  stdev:  {stdev:7.1f} ms")
    print(f"  P50:    {p50:7.1f} ms")
    print(f"  P90:    {p90:7.1f} ms")
    print(f"  P95:    {p95:7.1f} ms")
    print(f"  P99:    {p99:7.1f} ms")
    print(f"  max:    {mx:7.1f} ms")
    print()

    print("=== 决策（对照 v0.3 §5 预算 P95 < 2s）===")
    if p95 < 2000:
        print(f"  ✅ P95 {p95:.0f}ms < 2000ms → §5 预算成立")
        print(f"     PR-8 Day 2 pilot 可继续")
    elif p95 < 3000:
        print(f"  ⚠️ P95 {p95:.0f}ms 在 2-3s 之间")
        print(f"     → §5 预算松到 P95 < 3s，ADR 0007 D3 加注 'core 批接受较长冷启动'")
    else:
        print(f"  ❌ P95 {p95:.0f}ms > 3000ms")
        print(f"     → §5 预算不成立，需找 perf 根因（import 慢？FastMCP 重？subprocess spawn 慢？）")

    if failures:
        print()
        print(f"=== 失败 ({len(failures)}/{TRIALS}) ===")
        for idx, err in failures:
            print(f"  trial #{idx}: {err}")

    print()
    print("=== 输出（粘到 docs/mcp-v4-pr8-cold-start-test.md）===")
    print(f"Trials: {TRIALS}, Success: {len(durations_ms)}")
    print(f"min={mn:.1f} mean={mean:.1f} stdev={stdev:.1f}")
    print(f"p50={p50:.1f} p90={p90:.1f} p95={p95:.1f} p99={p99:.1f} max={mx:.1f} (ms)")


if __name__ == "__main__":
    asyncio.run(main())
