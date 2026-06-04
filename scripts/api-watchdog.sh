#!/bin/bash
# api-watchdog.sh - uvicorn 自愈监控
#
# 行为：
#   - 每 10s 检查 8000 端口是否 LISTEN
#   - 不在 → kill 僵尸 + setsid 拉起（完全脱离父 shell）
#   - 启动失败 3 次 → 退避（30s/60s/120s）
#   - 状态变化才写日志（健康时不刷屏）
#   - 唯一性：用 flock 防多 watchdog 并发
#
# 用法：
#   ./scripts/api-watchdog.sh           # 前台跑（看实时日志）
#   nohup ./scripts/api-watchdog.sh &  # 后台跑（推荐）
#   停止：kill $(cat /tmp/api-watchdog.pid)

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UV_BIN="$PROJECT_ROOT/apps/api/.venv/bin/python"
UVICORN_LOG="/tmp/uvicorn.log"
WATCHDOG_LOG="/tmp/api-watchdog.log"
WATCHDOG_PID="/tmp/api-watchdog.pid"
LOCK_FILE="/tmp/api-watchdog.lock"
CHECK_INTERVAL=10
MAX_RESTART_FAILS=3

echo $$ > "$WATCHDOG_PID"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$WATCHDOG_LOG"
}

is_listening() {
    lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN
}

start_uvicorn() {
    pkill -9 -f "uvicorn app.main:app" 2>/dev/null
    sleep 1
    cd "$PROJECT_ROOT"
    # setsid → 新 session，与父 shell 完全脱离；nohup → 忽略 SIGHUP
    setsid nohup "$UV_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        > "$UVICORN_LOG" 2>&1 < /dev/null &
    sleep 6
    is_listening
}

main_loop() {
    log "watchdog started, pid=$$"
    local restart_fails=0
    local last_state=""

    while true; do
        if is_listening; then
            if [ "$last_state" != "ok" ]; then
                log "uvicorn healthy on :8000"
                last_state="ok"
                restart_fails=0
            fi
        else
            if [ "$last_state" != "dead" ]; then
                log "uvicorn NOT listening on :8000 — restarting"
                last_state="dead"
            fi
            if start_uvicorn; then
                log "restart successful"
                restart_fails=0
            else
                restart_fails=$((restart_fails + 1))
                log "restart FAILED ($restart_fails/$MAX_RESTART_FAILS)"
                if [ $restart_fails -ge $MAX_RESTART_FAILS ]; then
                    local backoff=$((30 * (2 ** (restart_fails - MAX_RESTART_FAILS))))
                    log "too many failures, backing off ${backoff}s"
                    sleep $backoff
                fi
            fi
        fi
        sleep $CHECK_INTERVAL
    done
}

cleanup() {
    rm -f "$LOCK_FILE"
    log "watchdog stopped"
}
trap cleanup EXIT INT TERM

# 单一实例：flock 阻塞式
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "another watchdog already running, exiting"
    exit 1
fi

main_loop
