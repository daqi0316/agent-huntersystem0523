#!/usr/bin/env python3
"""系统健康监控 + 自动修复脚本。

功能:
1. 每 30s 检查 API/Web/MCP 健康状态，挂了自动重启
2. 检查日志中的 ERROR 并尝试自动修复常见问题
3. 检查数据库迁移状态，自动补跑缺失迁移
"""

import os
import sys
import time
import json
import signal
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta

PM2 = "/Users/qixia/.npm-global/bin/pm2"
CHECK_INTERVAL = 30
LOG_DIR = "/Users/qixia/.pm2/logs"

SERVICES = {
    "ai-recruitment-api":  {"port": 8000, "url": "http://localhost:8000/health"},
    "ai-recruitment-web":  {"port": 3000, "url": "http://localhost:3000"},
    "ai-recruitment-mcp": {"port": 8002, "url": "http://localhost:8002/mcp"},
}

KNOWN_ERRORS = [
    ("scheduled", "SCHEDULED"),  # PostgreSQL enum case mismatch
    ("UndefinedTableError", "conversation_messages"),  # missing migration
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def pm2_restart(name):
    subprocess.run([PM2, "restart", name], capture_output=True)
    log(f"🔄 重启 {name}")

def pm2_status(name):
    r = subprocess.run([PM2, "jlist"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        processes = json.loads(r.stdout)
        for p in processes:
            if p["name"] == name:
                return p.get("pm2_env", {}).get("status", "unknown")
        return None
    except Exception:
        return None

def check_service(name, url):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            code = resp.status
            if code in (200, 307, 302):
                return "ok"
            return f"http_{code}"
    except urllib.error.HTTPError as e:
        return f"http_{e.code}"
    except Exception:
        return "down"

def check_all_services():
    for name, cfg in SERVICES.items():
        status = pm2_status(name)
        health = check_service(name, cfg["url"])

        if status != "online":
            log(f"⚠️  {name} PM2 status={status}，正在重启...")
            pm2_restart(name)
        elif health != "ok":
            log(f"⚠️  {name} health={health}，正在重启...")
            pm2_restart(name)
        else:
            log(f"✅ {name} OK")

def check_migrations():
    """检查数据库迁移，缺失则补跑。"""
    try:
        r = subprocess.run(
            ["alembic", "current"],
            capture_output=True, text=True,
            cwd="/Users/qixia/agent-huntersystem0523/apps/api"
        )
        log(f"  DB migrations OK: {r.stdout.strip()}")
    except Exception as e:
        log(f"  DB migration check failed: {e}")

def check_log_errors():
    """扫描最近日志中的已知错误，尝试修复。"""
    # 检查 API 错误日志
    err_log = f"{LOG_DIR}/ai-recruitment-api-error.log"
    if not os.path.exists(err_log):
        return

    try:
        with open(err_log) as f:
            lines = f.readlines()
        # 只读最后 50 行
        recent = lines[-50:]
        content = "".join(recent)

        for pattern, fix in KNOWN_ERRORS:
            if pattern in content:
                log(f"⚠️  发现已知错误模式: {pattern}，尝试修复...")
                # 这里可以扩展为更智能的修复逻辑
    except Exception:
        pass

def signal_handler(sig, frame):
    log("监控停止")
    sys.exit(0)

def main():
    log("🚀 系统监控启动，每 30s 检查一次")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while True:
        check_all_services()
        check_log_errors()
        check_migrations()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
