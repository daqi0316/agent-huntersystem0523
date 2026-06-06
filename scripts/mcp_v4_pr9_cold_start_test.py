"""MCP v4 PR-9 cold start 测 — v0.4c phase 重排后

对照 v0.3 §5 预算（< 2s）：
  - v0.4c 之前：14 server 全 core → ≈ 4.8s（超预算 2.4x）
  - v0.4c 之后：5 server core（utils/weather/search/screening/knowledge）
    + 9 server secondary（30s 后拉）→ 冷启动预算内

测法：
  并行 spawn 5 core server，测量从 spawn 到全部 ready 的总时长，
  取 P95 over 10 trials。
"""
import asyncio
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
TRIALS = 10

CORE_SERVERS = [
    "app.mcp_servers.builtin.utils_server",
    "app.mcp_servers.builtin.weather_server",
    "app.mcp_servers.builtin.search_server",
    "app.mcp_servers.builtin.screening_server",
    "app.mcp_servers.builtin.knowledge_server",
]


async def _spawn_and_init(server_module: str) -> None:
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=["-m", server_module],
        cwd=SUBPROCESS_CWD,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()


async def measure_parallel_cold_start() -> float:
    """并行 spawn 5 core server 测总 cold start 时长。"""
    t0 = time.perf_counter()
    await asyncio.gather(*[_spawn_and_init(m) for m in CORE_SERVERS])
    return (time.perf_counter() - t0) * 1000


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return s[idx]


async def main():
    print("=== MCP v4 PR-9 v0.4c cold start 测 ===")
    print(f"Target:  P95 < 2000ms (v0.3 §5)")
    print(f"Core:    {len(CORE_SERVERS)} server (utils/weather/search/screening/knowledge)")
    print(f"Trials:  {TRIALS} (并行 spawn)")
    print()

    durations: list[float] = []
    for i in range(TRIALS):
        d = await measure_parallel_cold_start()
        durations.append(d)
        print(f"  trial #{i:2d}: {d:7.1f} ms")

    print()
    print("=== 结果 ===")
    print(f"  min:   {min(durations):7.1f} ms")
    print(f"  mean:  {statistics.mean(durations):7.1f} ms")
    print(f"  P50:   {pct(durations, 50):7.1f} ms")
    print(f"  P90:   {pct(durations, 90):7.1f} ms")
    print(f"  P95:   {pct(durations, 95):7.1f} ms")
    print(f"  P99:   {pct(durations, 99):7.1f} ms")
    print(f"  max:   {max(durations):7.1f} ms")
    print()

    p95 = pct(durations, 95)
    print("=== 决策（v0.3 §5 P95 < 2s）===")
    if p95 < 2000:
        print(f"  ✅ P95 {p95:.0f}ms < 2000ms → §5 预算成立")
    else:
        print(f"  ❌ P95 {p95:.0f}ms ≥ 2000ms → §5 预算未过，需再砍 core server")

    return 0 if p95 < 2000 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
