"""api-watchdog — uvicorn 自愈监控（Python 实现，确保脱离任何 shell）。

行为：
  - 每 10s 检查 8000 端口是否 LISTEN
  - 不在 → 拉起 uvicorn（双 fork + os.setsid，完全脱离当前进程组）
  - 启动失败 N 次 → 指数退避
  - 状态变化才写日志（健康时不刷屏）
  - 唯一性：flock 防多 watchdog 并发
  - 退出时清理锁文件

启动：
  nohup python -m app.scripts.api_watchdog > /tmp/wd-stdout.log 2>&1 &
  或 ./scripts/run-api-watchdog.sh（包装层）
"""

import errno
import fcntl
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UV_BIN = PROJECT_ROOT / "apps" / "api" / ".venv" / "bin" / "python"
UVICORN_LOG = Path("/tmp/uvicorn.log")
WATCHDOG_LOG = Path("/tmp/api-watchdog.log")
LOCK_FILE = Path("/tmp/api-watchdog.lock")
CHECK_INTERVAL = 10
MAX_RESTART_FAILS = 3
PORT = 8000

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=open(WATCHDOG_LOG, "a"),
)
log = logging.getLogger("api-watchdog")


def is_listening() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", PORT))
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def start_uvicorn() -> bool:
    """双 fork + setsid 拉起 uvicorn，**完全脱离**当前进程组。

    第一次 fork：让 shell 误以为命令完成。
    setsid：创建新 session，新进程组。
    第二次 fork：确保 daemon 不是 session leader（防重新获得 TTY）。
    """
    try:
        pid = os.fork()
        if pid > 0:
            os.waitpid(pid, 0)
            time.sleep(6)
            return is_listening()
        os.setsid()
        pid = os.fork()
        if pid > 0:
            os._exit(0)
        with open(UVICORN_LOG, "ab", 0) as logf:
            os.dup2(logf.fileno(), 1)
            os.dup2(logf.fileno(), 2)
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
        os.execv(
            str(UV_BIN),
            [str(UV_BIN), "-m", "uvicorn", "app.main:app",
             "--host", "0.0.0.0", "--port", str(PORT)],
        )
    except Exception as e:
        log.error("start_uvicorn fork failed: %s", e)
        return False


def acquire_lock() -> bool:
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_NB | fcntl.LOCK_EX)
    except OSError as e:
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return False
        raise
    os.write(fd, f"{os.getpid()}\n".encode())
    return True


def cleanup(*_):
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    log.info("watchdog stopped")
    sys.exit(0)


def main() -> int:
    import socket

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    if not acquire_lock():
        log.warning("another watchdog already running, exiting")
        return 1

    log.info("watchdog started, pid=%d, port=%d", os.getpid(), PORT)
    restart_fails = 0
    last_state = None

    while True:
        healthy = is_listening()
        state = "ok" if healthy else "dead"
        if state != last_state:
            if healthy:
                log.info("uvicorn healthy on :%d", PORT)
            else:
                log.warning("uvicorn NOT listening on :%d — restarting", PORT)
            last_state = state
            restart_fails = 0
        if not healthy:
            if start_uvicorn():
                log.info("restart successful")
                restart_fails = 0
            else:
                restart_fails += 1
                log.error("restart FAILED (%d/%d)", restart_fails, MAX_RESTART_FAILS)
                if restart_fails >= MAX_RESTART_FAILS:
                    backoff = 30 * (2 ** (restart_fails - MAX_RESTART_FAILS))
                    log.error("too many failures, backing off %ds", backoff)
                    time.sleep(backoff)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sys.exit(main() or 0)
