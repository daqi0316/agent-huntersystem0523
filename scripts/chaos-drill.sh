#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# P5-7: chaos drill 脚本 — 演练告警是否能 5min 内响
# 用法: bash scripts/chaos-drill.sh [5xx|p99|db|llm]
# 默认演练所有 4 条
# ──────────────────────────────────────────────────────────────────────

set -uo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
ALERT_TYPE="${1:-all}"
LOG_FILE="/tmp/chaos-drill-$(date +%s).log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

trigger_5xx() {
    log "触发 5xx 演练: curl /health 1000 次, 强制 abort"
    for i in $(seq 1 1000); do
        curl -sS -o /dev/null --max-time 1 "$API_BASE/../health" 2>/dev/null || true
    done
}

trigger_p99() {
    log "触发 p99 演练: 发 50 个慢请求 (sleep 3s 模拟)"
    for i in $(seq 1 50); do
        curl -sS -o /dev/null --max-time 4 "$API_BASE/auth/me" 2>/dev/null &
    done
    wait
}

trigger_db_pool() {
    log "触发 DB 连接池演练: 100 个并发 long-running query"
    for i in $(seq 1 100); do
        curl -sS -o /dev/null --max-time 30 "$API_BASE/candidates?limit=1000" 2>/dev/null &
    done
    wait
}

trigger_llm() {
    log "触发 LLM 失败演练: 注: 需先停 omlx/vllm (本地用 LLM_BASE_URL=http://invalid:9999/v1)"
    log "提示: 在 .env 设 LLM_BASE_URL=http://127.0.0.1:9 后重启 api"
    for i in $(seq 1 10); do
        curl -sS -o /dev/null --max-time 5 -X POST "$API_BASE/agent/chat" \
            -H "Content-Type: application/json" \
            -d '{"message":"test","user_id":"u1","org_id":"o1"}' 2>/dev/null
    done
}

verify_alert() {
    local rule_name="$1"
    log "验证告警 '$rule_name' 是否触发 (查 /metrics):"
    sleep 10
    curl -sS "http://localhost:8000/metrics" 2>/dev/null | grep -E "(http_5xx_total|http_request_duration|db_pool|llm_failure)" | head -5 | tee -a "$LOG_FILE"
}

case "$ALERT_TYPE" in
    5xx)
        trigger_5xx
        verify_alert "http_5xx_rate_high"
        ;;
    p99)
        trigger_p99
        verify_alert "http_p99_latency_high"
        ;;
    db)
        trigger_db_pool
        verify_alert "db_pool_high"
        ;;
    llm)
        trigger_llm
        verify_alert "llm_failure_rate_high"
        ;;
    all|*)
        trigger_5xx
        verify_alert "http_5xx_rate_high"
        sleep 5
        trigger_p99
        verify_alert "http_p99_latency_high"
        sleep 5
        trigger_db_pool
        verify_alert "db_pool_high"
        sleep 5
        trigger_llm
        verify_alert "llm_failure_rate_high"
        ;;
esac

log "演练完成。检查:"
log "  1. 飞书群是否收到 webhook (P1 触发 5min 内)"
log "  2. /var/lib/ai-recruitment/alert_acks.json 是否记录"
log "  3. Sentry 是否捕获异常"
log "完整日志: $LOG_FILE"
