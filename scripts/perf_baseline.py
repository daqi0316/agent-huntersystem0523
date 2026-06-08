"""A5: 性能 baseline 测 — 14 MCP server + 关键 HTTP 端点 P50/P95/P99

Momus §1.2 修正版 3 阶段:
  1. 测当前数字 (本脚本)
  2. 设定阈值 (报告 docs/perf-baseline-2026-06-07.md)
  3. CI 阈值门禁 (A2 PR 接入 GitHub Actions)

3 轮 × 30 trials 取 P50/P95/P99, 避免单次抖动。
mock LLM (跟 v1.1+v1.2 模式) 不污染 LLM token 配额。

输出:
  - JSON 完整数据
  - Markdown 报告 (给 docs/ 用)
  - stdout 摘要 (脚本模式)

用法:
  python scripts/perf_baseline.py --rounds 3
  python scripts/perf_baseline.py --output /tmp/perf-baseline.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
PYTHON_BIN = str(API_ROOT / ".venv" / "bin" / "python")
SUBPROCESS_CWD = str(API_ROOT)

ROUNDS = 3
TRIALS_PER_ROUND = 30
COLD_START_TRIALS = 5  # 冷启动只测 5 次 (每次 spawn 1.5s × 14 server, 总 105s)

# 14 server 列表 (从 config.json 提取)
SERVERS = [
    "application_server",
    "candidate_server",
    "dashboard_server",
    "evaluation_server",
    "interview_server",
    "jd_server",
    "job_server",
    "knowledge_server",
    "resume_server",
    "screening_server",
    "search_server",
    "skill_mgr_server",
    "utils_server",
    "weather_server",
]

# 关键 HTTP 端点 (高频 + 业务关键)
HTTP_ENDPOINTS = [
    {"method": "POST", "path": "/api/v1/auth/login", "auth": "none"},
    {"method": "GET", "path": "/api/v1/auth/me", "auth": "user"},
    {"method": "GET", "path": "/api/v1/agent/agents", "auth": "user"},
    {"method": "GET", "path": "/api/v1/dashboard/stats", "auth": "user"},
    {"method": "GET", "path": "/api/v1/jobs", "auth": "user"},
    {"method": "GET", "path": "/api/v1/candidates", "auth": "user"},
    {"method": "GET", "path": "/metrics", "auth": "none"},
    {"method": "GET", "path": "/health", "auth": "none"},
]


@dataclass
class BaselineResult:
    category: str  # mcp_cold_start / mcp_hot_call / http_endpoint
    target: str  # server name / endpoint path
    rounds: int = 0
    trials: int = 0
    min_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    raw_ms: list[float] = field(default_factory=list)


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return s[idx]


def _summarize(name: str, category: str, target: str, durations: list[float]) -> BaselineResult:
    return BaselineResult(
        category=category,
        target=target,
        rounds=ROUNDS,
        trials=len(durations),
        min_ms=min(durations) if durations else 0,
        mean_ms=statistics.mean(durations) if durations else 0,
        median_ms=statistics.median(durations) if durations else 0,
        p50_ms=pct(durations, 50),
        p95_ms=pct(durations, 95),
        p99_ms=pct(durations, 99),
        max_ms=max(durations) if durations else 0,
        raw_ms=durations,
    )


def compare_with_baseline(
    current: list[BaselineResult], baseline: list[BaselineResult]
) -> list[dict]:
    """对比 current vs baseline, 返回每端点的 diff (含 P50/P95/P99 ±%).

    Phase A 推后 (3): 性能 baseline 历史对比. 阈值 ±20% 标黄 (警告), ±50% 标红.
    返回 list[dict], 每项含 target, p50/p95/p99 当前+基线+diff_pct, 标记 warning/critical.
    """
    base_by_target: dict[str, BaselineResult] = {r.target: r for r in baseline}
    diffs: list[dict] = []
    for r in current:
        b = base_by_target.get(r.target)
        if b is None:
            diffs.append({
                "target": r.target,
                "category": r.category,
                "status": "new",
                "p50_current_ms": r.p50_ms,
                "p95_current_ms": r.p95_ms,
                "p99_current_ms": r.p99_ms,
            })
            continue
        def _pct_delta(cur: float, base: float) -> float:
            if base == 0:
                return 0.0 if cur == 0 else 100.0
            return (cur - base) / base * 100.0
        d_p50 = _pct_delta(r.p50_ms, b.p50_ms)
        d_p95 = _pct_delta(r.p95_ms, b.p95_ms)
        d_p99 = _pct_delta(r.p99_ms, b.p99_ms)
        worst = max(d_p50, d_p95, d_p99)
        if abs(worst) >= 50:
            status = "critical"
        elif abs(worst) >= 20:
            status = "warning"
        else:
            status = "ok"
        diffs.append({
            "target": r.target,
            "category": r.category,
            "status": status,
            "p50_current_ms": r.p50_ms, "p50_baseline_ms": b.p50_ms, "p50_delta_pct": d_p50,
            "p95_current_ms": r.p95_ms, "p95_baseline_ms": b.p95_ms, "p95_delta_pct": d_p95,
            "p99_current_ms": r.p99_ms, "p99_baseline_ms": b.p99_ms, "p99_delta_pct": d_p99,
        })
    return diffs


def _print_diff_table(diffs: list[dict]) -> None:
    """打印 diff 表格 (status emoji + target + P95 差)."""
    if not diffs:
        print("  (无 baseline 对比数据)")
        return
    print(f"  {'STATUS':10} {'TARGET':30} {'P50 Δ%':>10} {'P95 Δ%':>10} {'P99 Δ%':>10}")
    for d in diffs:
        emoji = {"ok": "✅", "warning": "⚠️ ", "critical": "❌", "new": "🆕"}.get(d["status"], "?")
        p50 = d.get("p50_delta_pct", 0.0)
        p95 = d.get("p95_delta_pct", 0.0)
        p99 = d.get("p99_delta_pct", 0.0)
        print(
            f"  {emoji:10} {d['target']:30} {p50:+10.1f} {p95:+10.1f} {p99:+10.1f}"
        )
    n_warn = sum(1 for d in diffs if d["status"] == "warning")
    n_crit = sum(1 for d in diffs if d["status"] == "critical")
    n_new = sum(1 for d in diffs if d["status"] == "new")
    if n_crit:
        print(f"\n  ❌ {n_crit} 端点 P95 退化 ≥50%")
    if n_warn:
        print(f"  ⚠️  {n_warn} 端点 P95 退化 20-50%")
    if n_new:
        print(f"  🆕 {n_new} 新端点 (无基线)")


async def _measure_mcp_cold_start(server: str, trials: int) -> list[float]:
    """测 MCP server 冷启动: spawn subprocess + initialize + list_tools, terminate。"""
    durations: list[float] = []
    for _ in range(trials):
        params = StdioServerParameters(
            command=PYTHON_BIN,
            args=["-m", f"app.mcp_servers.builtin.{server}"],
            cwd=SUBPROCESS_CWD,
        )
        t0 = time.perf_counter()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
        except Exception as e:
            print(f"  ⚠️  {server} cold start failed: {e}", file=sys.stderr)
            continue
        durations.append((time.perf_counter() - t0) * 1000)
    return durations


async def _measure_mcp_hot_call(server: str, tool_name: str, args: dict, trials: int) -> list[float]:
    """测 MCP server 热调用: spawn 一次, N 次 call_tool。"""
    durations: list[float] = []
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=["-m", f"app.mcp_servers.builtin.{server}"],
        cwd=SUBPROCESS_CWD,
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for _ in range(trials):
                    t0 = time.perf_counter()
                    try:
                        await session.call_tool(tool_name, args)
                    except Exception as e:
                        print(f"  ⚠️  {server}.{tool_name} call failed: {e}", file=sys.stderr)
                        continue
                    durations.append((time.perf_counter() - t0) * 1000)
    except Exception as e:
        print(f"  ❌  {server} init failed: {e}", file=sys.stderr)
    return durations


async def _measure_http_endpoint(
    client, base_url: str, endpoint: dict, token: str | None, trials: int
) -> list[float]:
    """测 HTTP 端点 P50/P95: client 复用, N 次连续 request。"""
    import httpx

    durations: list[float] = []
    headers = {}
    if token and endpoint["auth"] != "none":
        headers["Authorization"] = f"Bearer {token}"

    url = base_url.rstrip("/") + endpoint["path"]
    method = endpoint["method"]

    for _ in range(trials):
        t0 = time.perf_counter()
        try:
            resp = await client.request(method, url, headers=headers, timeout=10.0)
            if resp.status_code >= 500:
                continue
        except Exception:
            continue
        durations.append((time.perf_counter() - t0) * 1000)
    return durations


async def get_test_token(client, base_url: str) -> str | None:
    """拿 e2e-tester token (test fixture, 长期存在)."""
    import httpx
    try:
        resp = await client.post(
            base_url.rstrip("/") + "/api/v1/auth/login",
            json={"email": "e2e-tester@test.com", "password": "E2ePass123!"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        print(f"  ⚠️  login non-200: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  login exception: {e}", file=sys.stderr)
    return None


async def main() -> int:
    global ROUNDS, TRIALS_PER_ROUND
    parser = argparse.ArgumentParser(description="A5 性能 baseline 测")
    parser.add_argument("--rounds", type=int, default=ROUNDS, help="跑几轮取平均 (默认 3)")
    parser.add_argument("--trials", type=int, default=TRIALS_PER_ROUND, help="每轮 trial 数 (默认 30)")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", help="输出 JSON 报告")
    parser.add_argument("--compare-with", help="对比历史 baseline JSON (Phase A 推后 3)")
    parser.add_argument("--skip-mcp", action="store_true", help="跳过 MCP 测 (只测 HTTP)")
    parser.add_argument("--skip-http", action="store_true", help="跳过 HTTP 测 (只测 MCP)")
    args = parser.parse_args()

    ROUNDS = args.rounds
    TRIALS_PER_ROUND = args.trials

    print(f"=== A5 性能 baseline — {ROUNDS} 轮 × {TRIALS_PER_ROUND} trials ===\n")

    results: list[BaselineResult] = []

    if not args.skip_mcp:
        print(f"[1/2] MCP 14 server 测...\n")
        # 冷启动 (只跑 1 轮, 5 trials, 因每次 1.5s)
        print("  冷启动 (spawn + initialize + list_tools):")
        for srv in SERVERS:
            durations = await _measure_mcp_cold_start(srv, COLD_START_TRIALS)
            if durations:
                r = _summarize(srv, "mcp_cold_start", srv, durations)
                results.append(r)
                print(f"    {srv:25} P50={r.p50_ms:6.0f}ms P95={r.p95_ms:6.0f}ms P99={r.p99_ms:6.0f}ms (n={r.trials})")

        # 热调用 (用 utils_server 的 calculate 工具作 smoke test)
        print("\n  热调用 (utils_server.calculate '2*3'):")
        for _ in range(ROUNDS):
            durations = await _measure_mcp_hot_call(
                "utils_server", "calculate", {"arguments": {"expression": "2*3"}}, TRIALS_PER_ROUND
            )
            if durations:
                r = _summarize("utils_server", "mcp_hot_call", "utils_server.calculate", durations)
                results.append(r)
        # 报告最后一次 (3 轮累计 90 trials)
        if results and results[-1].category == "mcp_hot_call":
            r = results[-1]
            print(f"    calculate '2*3'    P50={r.p50_ms:6.0f}ms P95={r.p95_ms:6.0f}ms P99={r.p99_ms:6.0f}ms (n={r.trials})")

    if not args.skip_http:
        print(f"\n[2/2] HTTP 端点测 ({args.base})...")
        import httpx
        async with httpx.AsyncClient() as client:
            token = await get_test_token(client, args.base)
            if not token:
                print("  ⚠️  拿不到 test token, 跳过需鉴权端点")
            for ep in HTTP_ENDPOINTS:
                if ep["auth"] != "none" and not token:
                    continue
                durations = await _measure_http_endpoint(client, args.base, ep, token, TRIALS_PER_ROUND)
                if durations:
                    r = _summarize(ep["path"], "http_endpoint", f"{ep['method']} {ep['path']}", durations)
                    results.append(r)
                    print(f"    {ep['method']:6} {ep['path']:40} P50={r.p50_ms:6.0f}ms P95={r.p95_ms:6.0f}ms (n={r.trials})")

    print(f"\n=== 摘要 ===")
    print(f"  总测点数: {len(results)}")
    print(f"  14 server 冷启动: {sum(1 for r in results if r.category == 'mcp_cold_start')}/14")
    print(f"  MCP 热调用: {sum(1 for r in results if r.category == 'mcp_hot_call')}")
    print(f"  HTTP 端点: {sum(1 for r in results if r.category == 'http_endpoint')}/{len(HTTP_ENDPOINTS)}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)
        print(f"\n完整报告: {args.output}")

    if args.compare_with:
        with open(args.compare_with) as f:
            baseline_raw = json.load(f)
        baseline = [BaselineResult(**r) for r in baseline_raw]
        diffs = compare_with_baseline(results, baseline)
        print(f"\n=== Diff vs baseline ({args.compare_with}) ===")
        _print_diff_table(diffs)
        n_crit = sum(1 for d in diffs if d["status"] == "critical")
        return 1 if n_crit else 0

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
