"""按 CLAUDE.md 模式 1 daemonize 启 uvicorn + watchdog。

用 subprocess.Popen + start_new_session=True (POSIX setsid 等价) 完全脱离父 shell
进程组, bash 工具退出也不影响。
启动 uvicorn 8000 + api-watchdog 监控。

用法: python3 apps/api/_scripts/daemonize_api.py
       python3 apps/api/_scripts/daemonize_api.py --health-check-url http://127.0.0.1:8000/health
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/Users/qixia/agent-huntersystem0523")
API_ROOT = PROJECT_ROOT / "apps" / "api"
PYTHON_BIN = API_ROOT / ".venv" / "bin" / "python"
UVICORN_LOG = "/tmp/uvicorn.log"
WATCHDOG_LOG = "/tmp/api-watchdog.log"
WATCHDOG_PID = "/tmp/api-watchdog.pid"


def start_uvicorn() -> None:
    """subprocess.Popen + start_new_session=True 启 uvicorn (无 --reload, watchdog 兜底)。"""
    with open(UVICORN_LOG, "a+") as logf:
        subprocess.Popen(
            [
                str(PYTHON_BIN), "-m", "uvicorn",
                "app.main:app", "--host", "0.0.0.0", "--port", "8000",
            ],
            cwd=str(API_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
        )


def start_watchdog() -> None:
    """subprocess.Popen + start_new_session=True 启 api-watchdog.sh。"""
    with open(WATCHDOG_LOG, "a+") as logf:
        subprocess.Popen(
            ["/bin/bash", str(PROJECT_ROOT / "scripts" / "api-watchdog.sh")],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
        )


def wait_for_listening(port: int, timeout: float = 30.0) -> bool:
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def kill_existing(port: int) -> None:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5.0
        )
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), 9)
                except ProcessLookupError:
                    pass
    except Exception as e:
        print(f"kill_existing warn: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daemonize API server (double-fork + setsid)")
    parser.add_argument(
        "--health-check-url",
        default="http://127.0.0.1:8000/health",
        help="Worker ready check URL (default: %(default)s). Phase A 推后 5: A2 增强.",
    )
    args = parser.parse_args()

    print("=== daemonize api (subprocess + setsid) ===")

    print("[1/4] kill existing :8000")
    kill_existing(8000)
    time.sleep(1.0)

    print("[2/4] start uvicorn (setsid)")
    start_uvicorn()

    print("[3/4] wait for uvicorn :8000 LISTEN")
    if not wait_for_listening(8000, timeout=30.0):
        print(f"❌ uvicorn 未起, 看 {UVICORN_LOG}")
        return 1
    print("✅ uvicorn :8000 LISTEN")

    print("[3.5/4] wait for uvicorn worker ready (curl health-check-url)")
    import urllib.request
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(args.health_check_url, timeout=2.0) as resp:
                if resp.status == 200:
                    print(f"✅ uvicorn worker ready ({args.health_check_url} 200)")
                    break
        except Exception:
            time.sleep(0.5)
    else:
        print(f"⚠️  {args.health_check_url} 未 200, 看 {UVICORN_LOG} (但 LISTEN OK, 继续)")

    print("[4/4] start api-watchdog (setsid)")
    start_watchdog()
    time.sleep(2.0)

    print("\n=== 后台进程 ===")
    for label, cmd in [
        ("uvicorn :8000", ["lsof", "-ti:8000"]),
        ("watchdog pid", ["cat", WATCHDOG_PID]),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            print(f"  {label}: {r.stdout.strip() or 'N/A'}")
        except Exception as e:
            print(f"  {label}: {e}")

    print("\n=== 完成 ===")
    print(f"  uvicorn log: tail -f {UVICORN_LOG}")
    print(f"  watchdog log: tail -f {WATCHDOG_LOG}")
    print(f"  停: kill -9 $(lsof -ti:8000) $(cat {WATCHDOG_PID} 2>/dev/null) 2>/dev/null")
    return 0


if __name__ == "__main__":
    sys.exit(main())
