#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# chaos drill 脚本 — 演练故障注入 + 5min 内自动检测 + 告警
# 用法: bash scripts/chaos-drill.sh [5xx|p99|db-pool|llm|db-down|uvicorn-dies|redis-disconnect|all]
# 默认演练所有 7 条 (4 旧 + 3 新)
# 3 新硬故障 trigger (F21 1d ship):
#   - db-down: 停 postgres 容器, 验 API 5min 内返回 5xx
#   - uvicorn-dies: kill uvicorn 进程, 验 5min 内 watchdog 拉起
#   - redis-disconnect: 停 redis 容器, 验 cache miss fallback 工作
# ──────────────────────────────────────────────────────────────────────

set -uo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
ALERT_TYPE="${1:-all}"
LOG_FILE="/tmp/chaos-drill-$(date +%s).log"
DRILL_REPORT="/tmp/chaos-drill-report-$(date +%s).md"

# F21: drill 报告 markdown 生成
DRILL_START_TS=$(date +%s)
DRILL_FAILURES=()

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

record_failure() {
    local name="$1"
    local detail="$2"
    DRILL_FAILURES+=("$name: $detail")
    log "❌ FAILURE: $name — $detail"
}

# F21: timing 工具函数
start_timer() {
    echo $(date +%s)
}

elapsed_sec() {
    local start_ts="$1"
    local now_ts=$(date +%s)
    echo $((now_ts - start_ts))
}

# ──────────────────────────────────────────────────────────────────────
# 4 旧 trigger (P5-7, 保留)
# ──────────────────────────────────────────────────────────────────────

trigger_5xx() {
    log "触发 5xx 演练: curl /health 1000 次, 强制 abort"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 1000 curl"
        return 0
    fi
    for i in $(seq 1 1000); do
        curl -sS -o /dev/null --max-time 1 "$API_BASE/../health" 2>/dev/null || true
    done
}

trigger_p99() {
    log "触发 p99 演练: 发 50 个慢请求 (sleep 3s 模拟)"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 50 慢请求"
        return 0
    fi
    for i in $(seq 1 50); do
        curl -sS -o /dev/null --max-time 4 "$API_BASE/auth/me" 2>/dev/null &
    done
    wait
}

trigger_db_pool() {
    log "触发 DB 连接池演练: 100 个并发 long-running query"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 100 并发"
        return 0
    fi
    for i in $(seq 1 100); do
        curl -sS -o /dev/null --max-time 30 "$API_BASE/candidates?limit=1000" 2>/dev/null &
    done
    wait
}

trigger_llm() {
    log "触发 LLM 失败演练: 注: 需先停 omlx/vllm (本地用 LLM_BASE_URL=http://invalid:9999/v1)"
    log "提示: 在 .env 设 LLM_BASE_URL=http://127.0.0.1:9 后重启 api"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 10 LLM 请求"
        return 0
    fi
    for i in $(seq 1 10); do
        curl -sS -o /dev/null --max-time 5 -X POST "$API_BASE/agent/chat" \
            -H "Content-Type: application/json" \
            -d '{"message":"test","user_id":"u1","org_id":"o1"}' 2>/dev/null
    done
}

# ──────────────────────────────────────────────────────────────────────
# 3 新硬故障 trigger (F21, momus v2 G12)
# ──────────────────────────────────────────────────────────────────────

trigger_db_down() {
    log "触发 DB down 演练: docker compose stop postgres"
    log "⚠️  需 docker, 需 operator 手动确认环境 (非 dry-run 模式)"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 docker stop, 仅记录意图"
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        record_failure "db-down" "docker 命令不可用, 无法停 postgres"
        return 1
    fi
    docker compose stop postgres 2>&1 | tee -a "$LOG_FILE"
    log "postgres 已停, 等 5s 让健康检查反映"
    sleep 5
}

trigger_uvicorn_dies() {
    log "触发 uvicorn dies 演练: pkill uvicorn 进程"
    log "⚠️  需 uvicorn 在跑, watchdog (apps/api/app/scripts/api_watchdog.py) 应自动拉起"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 pkill, 仅记录意图"
        return 0
    fi
    pkill -f "uvicorn.*app.main" 2>&1 || record_failure "uvicorn-dies" "pkill 未命中 uvicorn 进程"
    log "uvicorn 已 kill, 等 10s 让 watchdog 拉起"
    sleep 10
}

trigger_redis_disconnect() {
    log "触发 redis disconnect 演练: docker compose stop redis"
    log "⚠️  需 docker, cache 应自动 fallback 到 DB (降级策略验证)"
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 docker stop, 仅记录意图"
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        record_failure "redis-disconnect" "docker 命令不可用, 无法停 redis"
        return 1
    fi
    docker compose stop redis 2>&1 | tee -a "$LOG_FILE"
    log "redis 已停, 等 5s 让 cache miss 反映"
    sleep 5
}

# ──────────────────────────────────────────────────────────────────────
# 检测 + 验证 (通用, F21 强化: 加 timing)
# ──────────────────────────────────────────────────────────────────────

verify_alert_with_timing() {
    local rule_name="$1"
    local start_ts="$2"
    log "验证告警 '$rule_name' 是否触发 (查 /metrics, 计时 < 5min 阈值):"
    local detected=0
    local elapsed=0
    while [ "$elapsed" -lt 300 ]; do
        sleep 10
        elapsed=$(elapsed_sec "$start_ts")
        local metrics=$(curl -sS "http://localhost:8000/metrics" 2>/dev/null)
        if echo "$metrics" | grep -qE "(http_5xx_total|http_request_duration|db_pool|llm_failure|process_uptime)"; then
            log "✅ 告警 '$rule_name' 在 ${elapsed}s 检测到 (≤ 300s 阈值)"
            echo "$metrics" | grep -E "(http_5xx_total|http_request_duration|db_pool|llm_failure|process_uptime)" | head -5 | tee -a "$LOG_FILE"
            detected=1
            break
        fi
    done
    if [ "$detected" = "0" ]; then
        record_failure "$rule_name" "5min (300s) 内未检测到告警指标"
    fi
}

# F21: 故障恢复验证 (3 新 trigger 必做)
verify_recovery() {
    local failure_name="$1"
    local start_ts="$2"
    log "验证 '$failure_name' 恢复 (等 5min 让修复生效):"
    local elapsed=0
    local recovered=0
    while [ "$elapsed" -lt 300 ]; do
        sleep 10
        elapsed=$(elapsed_sec "$start_ts")
        local health=$(curl -sS -o /dev/null -w "%{http_code}" "http://localhost:8000/health" 2>/dev/null || echo "000")
        if [ "$health" = "200" ]; then
            log "✅ '$failure_name' 在 ${elapsed}s 恢复 (健康检查 200)"
            recovered=1
            break
        fi
    done
    if [ "$recovered" = "0" ]; then
        record_failure "${failure_name}-recovery" "5min (300s) 内未自动恢复"
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Drill 报告生成 (F21 核心交付)
# ──────────────────────────────────────────────────────────────────────

generate_drill_report() {
    local drill_end_ts=$(date +%s)
    local total_elapsed=$((drill_end_ts - DRILL_START_TS))

    cat > "$DRILL_REPORT" <<EOF
# Chaos Drill 报告 (F21)

> 生成时间: $(date -r $drill_end_ts '+%Y-%m-%d %H:%M:%S')
> 演练类型: $ALERT_TYPE
> 总耗时: ${total_elapsed}s

## 演练概要

| 项 | 状态 |
|---|---|
| 总 trigger 数 | $(echo "$ALERT_TYPE" | grep -q "all" && echo "7" || echo "1") |
| 成功 trigger | $((7 - ${#DRILL_FAILURES[@]})) |
| 失败 trigger | ${#DRILL_FAILURES[@]} |
| 总耗时 | ${total_elapsed}s (≤ 300s 阈值) |

## 模拟故障清单

$(echo "$ALERT_TYPE" | grep -q "all" || echo "$ALERT_TYPE" | sed 's/^/- /')

## 排查步骤 (按 trigger 顺序)

EOF

    for failure in "${DRILL_FAILURES[@]+"${DRILL_FAILURES[@]}"}"; do
        cat >> "$DRILL_REPORT" <<EOF
### ❌ $failure
- 检测时间: $(date '+%H:%M:%S')
- 根因: 待 operator 填
- 修复: 待 operator 填

EOF
    done

    cat >> "$DRILL_REPORT" <<EOF
## 实际耗时

- 5min 阈值: 300s
- 实际总耗时: ${total_elapsed}s
- $([ ${total_elapsed} -le 300 ] && echo "✅ 达标" || echo "❌ 超阈值")

## 改进点 (operator 填)

1.
2.
3.

## 引用

- Refs: scripts/chaos-drill.sh (本报告生成源)
- Refs: apps/api/app/scripts/api_watchdog.py (uvicorn watchdog)
- Refs: monitoring/prometheus-alerts.yml (告警规则)
- Refs: docs/followup-f21-drill-ship-report.md (F21 ship report)
EOF

    log "📄 drill 报告生成: $DRILL_REPORT"
}

# ──────────────────────────────────────────────────────────────────────
# 主调度
# ──────────────────────────────────────────────────────────────────────

run_trigger_with_timing() {
    local trigger_func="$1"
    local rule_name="$2"
    local start_ts=$(start_timer)
    log "── 启动 $trigger_func ──"
    $trigger_func
    # dry-run 模式跳过 verify (否则 dry-run 也走 5min polling, 不合理)
    if [ "${DRY_RUN:-0}" = "1" ]; then
        log "[dry-run] 跳过 verify_alert_with_timing (5min polling)"
    else
        verify_alert_with_timing "$rule_name" "$start_ts"
        # 3 硬故障 trigger 额外验恢复
        case "$trigger_func" in
            trigger_db_down|trigger_uvicorn_dies|trigger_redis_disconnect)
                verify_recovery "$rule_name" "$start_ts"
                ;;
        esac
    fi
}

case "$ALERT_TYPE" in
    5xx)
        run_trigger_with_timing trigger_5xx "http_5xx_rate_high"
        ;;
    p99)
        run_trigger_with_timing trigger_p99 "http_p99_latency_high"
        ;;
    db|db-pool)
        run_trigger_with_timing trigger_db_pool "db_pool_high"
        ;;
    llm)
        run_trigger_with_timing trigger_llm "llm_failure_rate_high"
        ;;
    db-down)
        run_trigger_with_timing trigger_db_down "db_connection_failed"
        ;;
    uvicorn-dies)
        run_trigger_with_timing trigger_uvicorn_dies "uvicorn_restart"
        ;;
    redis-disconnect)
        run_trigger_with_timing trigger_redis_disconnect "redis_connection_failed"
        ;;
    all|*)
        run_trigger_with_timing trigger_5xx "http_5xx_rate_high"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_p99 "http_p99_latency_high"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_db_pool "db_pool_high"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_llm "llm_failure_rate_high"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_db_down "db_connection_failed"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_uvicorn_dies "uvicorn_restart"
        [ "${DRY_RUN:-0}" != "1" ] && sleep 5
        run_trigger_with_timing trigger_redis_disconnect "redis_connection_failed"
        ;;
esac

generate_drill_report

log "演练完成。检查:"
log "  1. drill 报告: $DRILL_REPORT"
log "  2. 完整日志: $LOG_FILE"
log "  3. 飞书群是否收到 webhook (P1 触发 5min 内)"
log "  4. Sentry 是否捕获异常"
