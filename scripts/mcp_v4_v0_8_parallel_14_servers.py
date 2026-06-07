"""v0.8.1: 14 server 并行 spawn 压测 — subprocess.Popen + psutil 真实 fd/memory 测量

覆盖 3 场景 × 10 trial = 30 实验 (Momus §3 决策 4 选安全验证):
  - 场景 A: stagger 0 (同时 spawn, 找 fd/memory 硬上限)
  - 场景 B: stagger 100ms (模拟快速重启, 代码热重载场景)
  - 场景 C: stagger 1s (模拟 prod 滚动重启)

v0.8 局限修复 (Momus §3.2): v0.8 用 stdio_client, anyio 包装子进程 PID 不暴露, max fd/rss 测 0.
v0.8.1 改用 subprocess.Popen + psutil.Process:
  - Popen 拿 real PID
  - psutil.Process(pid).memory_info().rss 读 RSS (KB)
  - psutil.Process(pid).open_files() 拿 FD 占用 (regular + socket)
  - 不测 MCP 协议 (v0.4e 14 server e2e 14/14 已覆盖, 避免双测)

主目标 (Momus §3.1): 失败率 0% (任何 fail = bug, 必查).
次目标: 真实 fd/memory 数字 (per-server + total).

CI 兼容 (Momus §3.3): psutil 跨平台 (macOS/Linux/Docker), 不依赖 lsof/ps 命令.
trial 间 sleep 1.5s 让 fd 释放 (Momus §3.4: Popen 退出后 fd 释放延迟比 stdio_client 长).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import psutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
PYTHON_BIN = str(API_ROOT / ".venv" / "bin" / "python")
SUBPROCESS_CWD = str(API_ROOT)
CONFIG_PATH = API_ROOT / "app" / "mcp_servers" / "config.json"
TRIALS = 10  # 标准场景跑 10 trials
TRIAL_GAP_S = 1.5
D_TRIALS = 3  # long-running 场景只跑 3 trials (5s × 14 server × 3 trials = 210s, 控时间)
D_TRIAL_GAP_S = 3.0
SERVER_INIT_SLEEP_S = 0.5  # spawn-kill 模式: 0.5s 让 server 起来 (import + stdio init)
SERVER_LIVE_SLEEP_S = 5.0  # long-running 模式: 5s 让 server 真正稳定 (listen socket + DB conn)
SCENARIOS = [
    ("A_simultaneous", 0.0),
    ("B_100ms_stagger", 0.1),
    ("C_1s_stagger", 1.0),
    ("D_long_running_5s", 0.0),  # v0.8.2 新场景: stdin=PIPE 让 server 不退, 5s 后测稳定态
]


@dataclass
class TrialResult:
    scenario: str
    trial_idx: int
    stagger_s: float
    total_wall_ms: float = 0.0
    failed_count: int = 0
    succeeded_count: int = 0
    peak_rss_kb: int = 0  # 任一 server 进程 max RSS (KB)
    peak_fd: int = 0  # 任一 server 进程 max FD 占用 (open_files + connections)
    mean_rss_kb: int = 0  # 平均 RSS (成功 server)
    mean_fd: int = 0
    max_open_files: int = 0
    max_connections: int = 0
    measurement: str = "ok"  # "ok" / "no_such_process" / "access_denied"


def _spawn_one_popen(server: dict, init_sleep: float = SERVER_INIT_SLEEP_S, keep_alive: bool = False) -> tuple[bool, int, int, int, int, int, str]:
    """Popen 起 server, 等初始化, 读 RSS/fd, terminate.

    keep_alive=True (v0.8.2 long-running): stdin=PIPE 让 server 不退, 测稳定态 fd.
    keep_alive=False (默认 spawn-kill): stdin=DEVNULL, 0.5s 后测启动期资源.

    Returns: (ok, pid, rss_kb, fd_open_files, fd_connections, total_fd, measurement_status)
    """
    env = {**os.environ, **server.get("extra_env", {})}
    stdin_cfg = subprocess.PIPE if keep_alive else subprocess.DEVNULL
    proc = subprocess.Popen(
        [PYTHON_BIN] + list(server["args"]),
        cwd=SUBPROCESS_CWD,
        env=env,
        stdin=stdin_cfg,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(init_sleep)
        try:
            ps = psutil.Process(proc.pid)
            rss_kb = ps.memory_info().rss // 1024
            open_files = ps.open_files()
            connections = ps.connections()
            fd_count = len(open_files) + len(connections)
            return True, proc.pid, rss_kb, len(open_files), len(connections), fd_count, "ok"
        except psutil.NoSuchProcess:
            return True, proc.pid, 0, 0, 0, 0, "no_such_process"
        except psutil.AccessDenied:
            return True, proc.pid, 0, 0, 0, 0, "access_denied"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def _run_trial(servers: list[dict], scenario: str, trial_idx: int, stagger_s: float, init_sleep: float = SERVER_INIT_SLEEP_S, keep_alive: bool = False) -> TrialResult:
    """跑单 trial: ThreadPoolExecutor 并行起 14 server (MCP 协议不测).

    init_sleep + keep_alive: v0.8.2 long-running 场景用 5.0s + keep_alive=True.
    """
    r = TrialResult(scenario=scenario, trial_idx=trial_idx, stagger_s=stagger_s)
    rss_values: list[int] = []
    fd_values: list[int] = []
    open_files_values: list[int] = []
    connections_values: list[int] = []

    def one_with_stagger(idx: int, server: dict) -> None:
        if stagger_s > 0:
            time.sleep(stagger_s * idx)
        ok, _pid, rss_kb, open_files, conns, fd_count, status = _spawn_one_popen(server, init_sleep=init_sleep, keep_alive=keep_alive)
        r.measurement = status
        if ok:
            r.succeeded_count += 1
            rss_values.append(rss_kb)
            fd_values.append(fd_count)
            open_files_values.append(open_files)
            connections_values.append(conns)
        else:
            r.failed_count += 1

    t_total = time.perf_counter()
    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = [executor.submit(one_with_stagger, i, s) for i, s in enumerate(servers)]
        for f in as_completed(futures):
            f.result()
    r.total_wall_ms = (time.perf_counter() - t_total) * 1000

    if rss_values:
        r.peak_rss_kb = max(rss_values)
        r.mean_rss_kb = sum(rss_values) // len(rss_values)
    if fd_values:
        r.peak_fd = max(fd_values)
        r.mean_fd = sum(fd_values) // len(fd_values)
    if open_files_values:
        r.max_open_files = max(open_files_values)
    if connections_values:
        r.max_connections = max(connections_values)

    return r


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return s[idx]


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text())
    servers = config["servers"]
    print(f"=== v0.8.2: 14 server 并行 spawn 压测 (Popen + psutil + long-running) ===")
    print(f"Servers: {len(servers)}")
    print(f"Scenarios: {[s[0] for s in SCENARIOS]}")
    print(f"Trials A/B/C: {TRIALS}, Trial D (long-running): {D_TRIALS}")
    print(f"Trial gap A/B/C: {TRIAL_GAP_S}s, D: {D_TRIAL_GAP_S}s")
    print(f"Init sleep spawn-kill: {SERVER_INIT_SLEEP_S}s, long-running: {SERVER_LIVE_SLEEP_S}s")
    print()

    all_results: list[TrialResult] = []

    for scenario_name, stagger_s in SCENARIOS:
        is_long = scenario_name.startswith("D_")
        n_trials = D_TRIALS if is_long else TRIALS
        gap_s = D_TRIAL_GAP_S if is_long else TRIAL_GAP_S
        init_s = SERVER_LIVE_SLEEP_S if is_long else SERVER_INIT_SLEEP_S
        keep_alive = is_long
        print(f"--- 场景 {scenario_name} (stagger={stagger_s}s, init={init_s}s, keep_alive={keep_alive}) ---")
        scenario_results: list[TrialResult] = []
        for trial_idx in range(1, n_trials + 1):
            r = _run_trial(servers, scenario_name, trial_idx, stagger_s, init_sleep=init_s, keep_alive=keep_alive)
            scenario_results.append(r)
            all_results.append(r)
            status = "✅" if r.failed_count == 0 else "❌"
            print(
                f"  {status} trial {trial_idx}/{n_trials}: "
                f"wall={r.total_wall_ms:7.0f}ms "
                f"failed={r.failed_count}/14 "
                f"peak rss={r.peak_rss_kb}KB "
                f"peak fd={r.peak_fd} (files={r.max_open_files} conns={r.max_connections})"
            )
            time.sleep(gap_s)
        wall_p95 = _pct([r.total_wall_ms for r in scenario_results], 95)
        avg_failed = sum(r.failed_count for r in scenario_results) / len(scenario_results)
        max_rss = max(r.peak_rss_kb for r in scenario_results)
        max_fd = max(r.peak_fd for r in scenario_results)
        print(
            f"  Aggregate: P95 wall={wall_p95:.0f}ms "
            f"avg failed/trial={avg_failed:.1f}/14 "
            f"max rss={max_rss}KB max fd={max_fd}"
        )
        print()

    total_trials = len(all_results)
    total_failed = sum(r.failed_count for r in all_results)
    total_servers = total_trials * len(servers)
    overall_fail_rate = total_failed / total_servers * 100 if total_servers else 0.0

    print("=" * 50)
    print("=== 总结 (33 实验: A/B/C × 10 + D × 3, 33 × 14 = 462 server lifecycle) ===")
    print(f"  总 trials: {total_trials}")
    print(f"  总 server lifecycle: {total_servers}")
    print(f"  总 failed: {total_failed}")
    print(f"  失败率: {overall_fail_rate:.2f}%")
    print()
    print("  --- fd/memory 真实数字 (v0.8.2 spawn-kill + long-running 对比) ---")
    rss_peak_per_scenario = {}
    fd_peak_per_scenario = {}
    for scenario_name, _ in SCENARIOS:
        scenario_rss = max(r.peak_rss_kb for r in all_results if r.scenario == scenario_name)
        scenario_fd = max(r.peak_fd for r in all_results if r.scenario == scenario_name)
        rss_peak_per_scenario[scenario_name] = scenario_rss
        fd_peak_per_scenario[scenario_name] = scenario_fd
    for scenario_name, _ in SCENARIOS:
        print(
            f"  {scenario_name}: max rss={rss_peak_per_scenario[scenario_name]}KB "
            f"max fd={fd_peak_per_scenario[scenario_name]}"
        )
    print()
    print(f"  跨场景: max rss={max(rss_peak_per_scenario.values())}KB "
          f"max fd={max(fd_peak_per_scenario.values())}")
    print()

    if overall_fail_rate > 0:
        print(f"❌ 失败率 {overall_fail_rate:.2f}% > 0% — 必须查原因")
        return 1

    print("✅ 失败率 0% — 14 server 并行安全 + spawn-kill vs long-running 资源对比")
    return 0


if __name__ == "__main__":
    import json
    sys.exit(main())
