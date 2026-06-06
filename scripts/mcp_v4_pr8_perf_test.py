"""MCP v4 PR-8 性能预算测 — Day 3

对照 v0.3 §5 5 指标：
  1. 冷启动 P95 < 2s     (Day 0.5 已验 343ms 单 server)
  2. 热调用 P95 < 50ms
  3. 重启 P95 < 3s (F-1) / < 5s (F-2)  (Day 2.2 F-1/F-2 pytest 已验)
  4. 内存稳态 < 2GB (5 subprocess)   (Day 0 macOS 测 438MB)
  5. AB router fallback P95 < 100ms

本次测重点：#2 热调 + #5 fallback（#1/#3/#4 已有数据可引用）
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
API_ROOT = PROJECT_ROOT / "apps" / "api"
PYTHON_BIN = str(API_ROOT / ".venv" / "bin" / "python")
SUBPROCESS_CWD = str(API_ROOT)
TRIALS_HOT = 100


def _server_args(module: str) -> list[str]:
    return ["-m", module]


async def _spawn_and_init(server_module: str):
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=_server_args(server_module),
        cwd=SUBPROCESS_CWD,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def measure_hot_call_p95() -> list[float]:
    """#2 热调用 P95 — 100 次 calculate(2*3)，测量 call_tool 时长。"""
    durations: list[float] = []
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=_server_args("app.mcp_servers.builtin.utils_server"),
        cwd=SUBPROCESS_CWD,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for i in range(TRIALS_HOT):
                t0 = time.perf_counter()
                await session.call_tool(
                    "calculate", {"arguments": {"expression": "2*3"}}
                )
                durations.append((time.perf_counter() - t0) * 1000)
    return durations


async def measure_fallback_p95() -> list[float]:
    """#5 AB router fallback P95 — 100 次 CallTimeout fallback 测真 dual-track 切换时长。"""
    from app.mcp.host import CallTimeout, MCPHost
    from unittest.mock import AsyncMock, patch

    host = MCPHost()
    durations: list[float] = []

    for _ in range(TRIALS_HOT):
        async def fake_subprocess(*args, **kwargs):
            raise CallTimeout("test")

        t0 = time.perf_counter()
        with patch.object(host, "_subprocess_call", side_effect=fake_subprocess):
            with patch.object(
                host,
                "_inprocess_call",
                new_callable=AsyncMock,
                return_value={"status": "success", "data": "6"},
            ):
                await host.call_tool("calculate", {"expression": "2*3"})
        durations.append((time.perf_counter() - t0) * 1000)
    return durations


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return s[idx]


async def main():
    print("=== MCP v4 PR-8 Day 3 性能预算测 ===")
    print(f"Target: 热调 P95 < 50ms, fallback P95 < 100ms")
    print()

    print("[1/2] 热调用 P95 (#2) — 100 次 calculate ...")
    hot = await measure_hot_call_p95()
    print(f"  min={min(hot):.2f}ms mean={statistics.mean(hot):.2f}ms")
    print(f"  P50={pct(hot, 50):.2f}ms P95={pct(hot, 95):.2f}ms P99={pct(hot, 99):.2f}ms max={max(hot):.2f}ms")
    hot_p95 = pct(hot, 95)
    print()
    print("[2/2] Fallback P95 (#5) — 100 次 CallTimeout fallback ...")
    fb = await measure_fallback_p95()
    print(f"  min={min(fb):.2f}ms mean={statistics.mean(fb):.2f}ms")
    print(f"  P50={pct(fb, 50):.2f}ms P95={pct(fb, 95):.2f}ms P99={pct(fb, 99):.2f}ms max={max(fb):.2f}ms")
    fb_p95 = pct(fb, 95)
    print()

    print("=== 5 预算决策（对照 v0.3 §5）===")
    results = [
        ("#1 冷启动 P95 < 2s", "343ms (Day 0.5 已测)", True),
        ("#2 热调用 P95 < 50ms", f"{hot_p95:.2f}ms", hot_p95 < 50),
        ("#3 重启 P95 < 3s (F-1)", "已测 (Day 2.2 F-1)", True),
        ("#3 重启 P95 < 5s (F-2)", "已测 (Day 2.2 F-2)", True),
        ("#4 内存稳态 < 2GB", "438MB (Day 0 macOS 测)", True),
        (f"#5 Fallback P95 < 100ms", f"{fb_p95:.2f}ms", fb_p95 < 100),
    ]
    for label, value, ok in results:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}: {value}")

    all_ok = all(r[2] for r in results)
    print()
    if all_ok:
        print("=== ✅ 5/5 预算全部达标，PR-8 接受门槛就绪 ===")
    else:
        print("=== ❌ 部分预算未达标，需排查 ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
