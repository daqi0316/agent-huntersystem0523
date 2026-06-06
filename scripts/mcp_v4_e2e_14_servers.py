"""MCP v4 e2e 测 — v0.4e 14 server 全生命周期

覆盖 v0.4c phase 重排后的 14 server（5 core + 9 secondary）：
  对每个 server 顺序跑完整 lifecycle：spawn → initialize → list_tools → shutdown
  验证：lifecycle OK = spawn 不超时 + initialize 成功 + list_tools 返回 ≥1 工具
  测得：per-server 各阶段耗时 + total wall time + P95

与 mcp_v4_pr9_cold_start_test.py（仅 5 core 并行 spawn）的区别：
  本脚本是 lifecycle e2e（验证每个 server 端到端可用），
  那个脚本是 cold start 性能基准（仅 5 core 并行 spawn 测时）。
"""
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
PYTHON_BIN = str(API_ROOT / ".venv" / "bin" / "python")
SUBPROCESS_CWD = str(API_ROOT)
CONFIG_PATH = API_ROOT / "app" / "mcp_servers" / "config.json"
INIT_TIMEOUT_S = 10.0
LIST_TOOLS_TIMEOUT_S = 5.0


@dataclass
class ServerResult:
    server_id: str
    phase: str
    module: str
    ok: bool
    spawn_ms: float = 0.0
    init_ms: float = 0.0
    list_tools_ms: float = 0.0
    tool_count: int = 0
    total_ms: float = 0.0
    error: str = ""


async def lifecycle_one(server: dict) -> ServerResult:
    r = ServerResult(
        server_id=server["id"],
        phase=server["startup_phase"],
        module=server["args"][-1],
        ok=False,
    )
    t_total = time.perf_counter()
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=list(server["args"]),
        cwd=SUBPROCESS_CWD,
        env={**server.get("extra_env", {})},
    )
    t_spawn = time.perf_counter()
    try:
        async with stdio_client(params) as (read, write):
            t_spawn_done = time.perf_counter()
            r.spawn_ms = (t_spawn_done - t_spawn) * 1000
            async with ClientSession(read, write) as session:
                t_init = time.perf_counter()
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_S)
                r.init_ms = (time.perf_counter() - t_init) * 1000
                t_list = time.perf_counter()
                tools = await asyncio.wait_for(
                    session.list_tools(), timeout=LIST_TOOLS_TIMEOUT_S
                )
                r.list_tools_ms = (time.perf_counter() - t_list) * 1000
                r.tool_count = len(tools.tools)
                r.ok = r.tool_count >= 1
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"[:120]
    r.total_ms = (time.perf_counter() - t_total) * 1000
    return r


async def main() -> int:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    servers = cfg["servers"]
    print(f"=== MCP v4 e2e lifecycle 测 — v0.4e 14 server ===")
    print(f"Servers: {len(servers)} ({sum(1 for s in servers if s['startup_phase'] == 'core')} core + "
          f"{sum(1 for s in servers if s['startup_phase'] == 'secondary')} secondary)")
    print(f"Mode:    sequential lifecycle (spawn → init → list_tools → shutdown)")
    print()

    results: list[ServerResult] = []
    for s in servers:
        r = await lifecycle_one(s)
        results.append(r)
        status = "✅" if r.ok else "❌"
        print(
            f"  {status} {r.server_id:18} phase={r.phase:10} "
            f"spawn={r.spawn_ms:6.0f}ms init={r.init_ms:6.0f}ms "
            f"list={r.list_tools_ms:5.0f}ms tools={r.tool_count:2d} "
            f"total={r.total_ms:6.0f}ms"
            + (f"  err={r.error}" if r.error else "")
        )

    print()
    print("=== Aggregate ===")
    n_ok = sum(1 for r in results if r.ok)
    n_fail = len(results) - n_ok
    totals = [r.total_ms for r in results]
    print(f"  pass:  {n_ok}/{len(results)}")
    print(f"  fail:  {n_fail}")
    print(f"  total wall:  {sum(totals):.0f}ms")
    print(f"  mean/server: {statistics.mean(totals):.0f}ms")
    print(f"  P95/server:  {sorted(totals)[int(0.95 * len(totals)) - 1]:.0f}ms")
    print(f"  max/server:  {max(totals):.0f}ms")

    if n_fail:
        print()
        print("=== Failures ===")
        for r in results:
            if not r.ok:
                print(f"  ❌ {r.server_id}: {r.error or f'tool_count={r.tool_count}'}")

    print()
    print("=== 决策 ===")
    if n_ok == len(results):
        print(f"  ✅ 14/14 server lifecycle OK → 14 server 端到端可用")
        return 0
    print(f"  ❌ {n_fail} server 失败 → e2e 未通过")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
