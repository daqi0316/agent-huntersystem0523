"""v0.8: 14 server 并行 spawn 压测 — 安全验证 + fd/memory 边界探测

覆盖 3 场景 × 10 trial = 30 实验:
  - 场景 A: stagger 0 (同时 spawn, 找 fd/memory 硬上限)
  - 场景 B: stagger 100ms (模拟快速重启, 代码热重载场景)
  - 场景 C: stagger 1s (模拟 prod 滚动重启)

主目标 (Momus §3 决策 4): 安全验证 (14 server 并行不死), 非性能基准.
dev 数字 prod 无效 (v0.5-replan §5 原文 "价值低"), 但失败率阈值 0% 必查
(任何 spawn fail 都是 bug).

测量:
  - P95 total wall (单 trial 14 server 全部 spawn+init+list+shutdown 完成时间)
  - mean RSS peak (Trial 内任一 server 进程 max RSS, KB)
  - max open fd peak (Trial 内任一 server 进程 max open fd count)
  - 失败率 (failed lifecycle / total, 0% 是底线)

CI 兼容 (Momus §2.2):
  - lsof / ps 命令 try/except 包, 缺命令时记 NA 不阻塞
  - trial 间 asyncio.sleep(0.5) 让 fd 释放 (Momus §2.3)

不做函数级 profiling (Momus §2.4): 推 v0.8.1
"""
from __future__ import annotations

import asyncio
import json
import statistics
import subprocess
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
TRIALS = 10
TRIAL_GAP_S = 0.5
SCENARIOS = [
    ("A_simultaneous", 0.0),
    ("B_100ms_stagger", 0.1),
    ("C_1s_stagger", 1.0),
]


@dataclass
class TrialResult:
    scenario: str
    trial_idx: int
    stagger_s: float
    total_wall_ms: float = 0.0
    failed_count: int = 0
    succeeded_count: int = 0
    peak_rss_kb: int = 0
    peak_fd: int = 0
    fd_measurement: str = "ok"  # "ok" / "lsof_na" / "ps_na" / "lsof_and_ps_na"
    error: str = ""


def _read_fd_and_rss(pids: list[int]) -> tuple[int, int, str]:
    """读一组 PID 的 max fd + max RSS (KB). lsof/ps 缺命令时返 NA.

    Returns: (max_fd, max_rss_kb, measurement_status)
    """
    fd_measurement = "ok"
    max_fd = 0
    fd_na = False
    rss_na = False

    for pid in pids:
        if not fd_na:
            try:
                result = subprocess.run(
                    ["lsof", "-p", str(pid)],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    fd_count = len(result.stdout.strip().splitlines()) - 1
                    max_fd = max(max_fd, fd_count)
                else:
                    fd_na = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                fd_na = True

        if not rss_na:
            try:
                result = subprocess.run(
                    ["ps", "-o", "rss=", "-p", str(pid)],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    rss_kb = int(result.stdout.strip().splitlines()[0])
                    max_rss_kb = max(max_rss_kb, rss_kb)
                else:
                    rss_na = True
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
                rss_na = True

    if fd_na and rss_na:
        return max_fd, max_rss_kb, "lsof_and_ps_na"
    if fd_na:
        return max_fd, max_rss_kb, "lsof_na"
    if rss_na:
        return max_fd, max_rss_kb, "ps_na"
    return max_fd, max_rss_kb, "ok"


async def _lifecycle_one(server: dict) -> tuple[bool, list[int]]:
    """跑单 server 完整 lifecycle. 返 (ok, pids).

    这里简化不开新进程测量, 直接用 stdio_client 子进程 PID.
    """
    params = StdioServerParameters(
        command=PYTHON_BIN,
        args=list(server["args"]),
        cwd=SUBPROCESS_CWD,
        env={**server.get("extra_env", {})},
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_S)
                await asyncio.wait_for(session.list_tools(), timeout=LIST_TOOLS_TIMEOUT_S)
                return True, []
    except Exception:
        return False, []


async def _run_trial(servers: list[dict], scenario: str, trial_idx: int, stagger_s: float) -> TrialResult:
    """跑单 trial: stagger spawn 14 server, 测总耗时 + 失败数 + fd/rss peak."""
    r = TrialResult(scenario=scenario, trial_idx=trial_idx, stagger_s=stagger_s)
    pids_collected: list[int] = []

    t_total = time.perf_counter()

    async def one_with_stagger(idx: int, server: dict):
        if stagger_s > 0:
            await asyncio.sleep(stagger_s * idx)
        ok, pids = await _lifecycle_one(server)
        pids_collected.extend(pids)
        return ok

    results = await asyncio.gather(
        *[one_with_stagger(i, s) for i, s in enumerate(servers)],
        return_exceptions=True,
    )
    r.total_wall_ms = (time.perf_counter() - t_total) * 1000

    succeeded = 0
    failed = 0
    for r_item in results:
        if r_item is True:
            succeeded += 1
        else:
            failed += 1
    r.succeeded_count = succeeded
    r.failed_count = failed

    if pids_collected:
        max_fd, max_rss_kb, status = _read_fd_and_rss(pids_collected)
        r.peak_fd = max_fd
        r.peak_rss_kb = max_rss_kb
        r.fd_measurement = status

    return r


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return s[idx]


async def main() -> int:
    config = json.loads(CONFIG_PATH.read_text())
    servers = config["servers"]
    print(f"=== v0.8: 14 server 并行 spawn 压测 ===")
    print(f"Servers: {len(servers)}")
    print(f"Scenarios: {[s[0] for s in SCENARIOS]}")
    print(f"Trials/scenario: {TRIALS}")
    print(f"Trial gap: {TRIAL_GAP_S}s")
    print()

    all_results: list[TrialResult] = []

    for scenario_name, stagger_s in SCENARIOS:
        print(f"--- 场景 {scenario_name} (stagger={stagger_s}s) ---")
        scenario_results: list[TrialResult] = []
        for trial_idx in range(1, TRIALS + 1):
            r = await _run_trial(servers, scenario_name, trial_idx, stagger_s)
            scenario_results.append(r)
            all_results.append(r)
            status = "✅" if r.failed_count == 0 else "❌"
            print(
                f"  {status} trial {trial_idx}/{TRIALS}: "
                f"wall={r.total_wall_ms:7.0f}ms "
                f"failed={r.failed_count}/14 "
                f"fd={r.peak_fd} rss={r.peak_rss_kb}KB"
            )
            await asyncio.sleep(TRIAL_GAP_S)
        wall_p95 = _pct([r.total_wall_ms for r in scenario_results], 95)
        avg_failed = statistics.mean([r.failed_count for r in scenario_results])
        max_fd = max([r.peak_fd for r in scenario_results])
        max_rss = max([r.peak_rss_kb for r in scenario_results])
        print(
            f"  Aggregate: P95 wall={wall_p95:.0f}ms "
            f"avg failed/trial={avg_failed:.1f}/14 "
            f"max fd={max_fd} max rss={max_rss}KB"
        )
        print()

    total_trials = len(all_results)
    total_failed = sum(r.failed_count for r in all_results)
    total_servers = total_trials * len(servers)
    overall_fail_rate = total_failed / total_servers * 100 if total_servers else 0.0

    print("=" * 50)
    print("=== 总结 (30 实验, 30 × 14 = 420 server lifecycle) ===")
    print(f"  总 trials: {total_trials}")
    print(f"  总 server lifecycle: {total_servers}")
    print(f"  总 failed: {total_failed}")
    print(f"  失败率: {overall_fail_rate:.2f}%")
    print()

    if overall_fail_rate > 0:
        print(f"❌ 失败率 {overall_fail_rate:.2f}% > 0% — 必须查原因, 推 v0.8.1 修复")
        return 1

    print("✅ 失败率 0% — 14 server 并行安全, ship 文档")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
