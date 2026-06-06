"""macOS 资源测 — PR-8 Day 0 §8

目的：测 5 subprocess 稳态内存 + FD + 进程数，验证 PR-8 pilot 可行。
- 模拟场景：5 个 MCP server subprocess 同时跑
- 用真实 .venv/bin/python + import 一些常用库（模拟 server 启动）
- 跑 10s 后采样 RSS / open files / 进程数
"""
import asyncio
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

# 模拟 server 启动开销：import app/api/.venv 里的库
# subprocess cwd=apps/api, 用 .venv/bin/python
SIMULATED_IMPORTS = """
import asyncio
import json
import logging
import sys
import time

# 模拟 MCP server 启动 import（fastmcp + pydantic + sqlalchemy）
try:
    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print('IMPORT_FAIL:', e, file=sys.stderr)
    sys.exit(2)

# 模拟 server 启动开销
import asyncio
async def _setup():
    mcp = FastMCP('test', instructions='macos resource test')
    return mcp

asyncio.run(_setup())
time.sleep(30)
"""


async def spawn_one(idx: int) -> subprocess.Popen:
    """spawn 1 个模拟 server subprocess"""
    return subprocess.Popen(
        ["./apps/api/.venv/bin/python", "-c", SIMULATED_IMPORTS],
        cwd=".",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )


def get_rss_mb(pid: int) -> float:
    """读 macOS 进程 RSS（MB）"""
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            text=True,
        ).strip()
        return int(out) / 1024 if out else 0.0
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def get_open_fds(pid: int) -> int:
    """读进程 open files 数量（macOS 用 /dev/fd）"""
    try:
        return len(os.listdir(f"/dev/fd"))
    except OSError:
        return -1


async def main():
    print("=== PR-8 Day 0 §8 macOS 资源测 ===")
    print(f"Platform: {sys.platform}")
    print(f"Python: {sys.version.split()[0]}")
    print()

    # 系统基线
    print("[0] 系统基线")
    total_mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3)
    print(f"  物理内存: {total_mem_gb:.1f} GB")
    print(f"  当前进程 PID: {os.getpid()}, RSS: {get_rss_mb(os.getpid()):.1f} MB")
    print()

    # 拉起 5 subprocess
    print("[1] 拉起 5 个模拟 server subprocess")
    procs = []
    for i in range(5):
        p = await spawn_one(i)
        procs.append(p)
        print(f"  spawn #{i}: pid={p.pid}")

    # 等启动完成
    await asyncio.sleep(3)
    print()

    # 测稳态
    print("[2] 稳态采样（启动后 3s）")
    total_rss = 0.0
    for i, p in enumerate(procs):
        if p.poll() is None:
            rss = get_rss_mb(p.pid)
            total_rss += rss
            print(f"  pid {p.pid}: RSS = {rss:.1f} MB, alive={p.poll() is None}")
        else:
            print(f"  pid {p.pid}: 进程已退出 rc={p.returncode}")
    print(f"  -- 5 subprocess 总 RSS: {total_rss:.1f} MB --")
    print()

    # 等更久后采样
    await asyncio.sleep(5)
    print("[3] 8s 后稳态采样")
    total_rss = 0.0
    for i, p in enumerate(procs):
        if p.poll() is None:
            rss = get_rss_mb(p.pid)
            total_rss += rss
    print(f"  -- 5 subprocess 总 RSS (8s): {total_rss:.1f} MB --")
    print()

    # 决策点
    print("=" * 50)
    print("§8 决策点")
    print("=" * 50)
    if total_rss < 2048:
        print(f"  ✅ < 2GB 稳态 → §5 预算成立，进 PR-8")
    elif total_rss < 4096:
        print(f"  ⚠️ 2-4GB → 砍 1 pilot 工具（weather 延后）")
    else:
        print(f"  ❌ > 4GB → §6.1 重做门槛触发")
    print()

    # 清理
    print("[4] 清理 subprocess")
    for p in procs:
        if p.poll() is None:
            p.terminate()
    await asyncio.sleep(1)
    for p in procs:
        if p.poll() is None:
            p.kill()
    print("  done")


if __name__ == "__main__":
    asyncio.run(main())
