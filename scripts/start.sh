#!/bin/bash
# =============================================================================
# AI Recruitment System — 一键启动脚本
# 用法: ./scripts/start.sh [api|web|all|restart|status|stop]
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_DEV="$PROJECT_ROOT/docker-compose.dev.yml"
COMPOSE_FILE="$COMPOSE_DEV"
LOG_FILE="/tmp/ai-recruitment-startup.log"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

# ── 检查依赖 ────────────────────────────────────────────────────────────────
check_docker() {
  if ! docker info > /dev/null 2>&1; then
    err "Docker 未运行，请先启动 Docker Desktop"
    exit 1
  fi
}

check_venv() {
  VENV="$PROJECT_ROOT/apps/api/.venv/bin/python"
  if [[ ! -x "$VENV" ]]; then
    err "Python venv 未找到: $VENV"
    exit 1
  fi
}

# ── 启动基础设施 ───────────────────────────────────────────────────────────
start_infra() {
  log "启动基础设施（postgres / redis / qdrant）..."
  check_docker

  # 检查是否已有运行中的容器
  RUNNING=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | grep -E "postgres|redis|qdrant" || true)
  if [[ -n "$RUNNING" ]]; then
    warn "基础设施已在运行，跳过启动"
    docker compose -f "$COMPOSE_FILE" ps
    return
  fi

  docker compose -f "$COMPOSE_FILE" up -d postgres redis qdrant
  log "等待健康检查..."
  sleep 8

  # 验证
  for svc in postgres redis qdrant; do
    local status=$(docker inspect --format='{{.State.Health.Status}}' "ai-recruitment-$svc" 2>/dev/null || echo "none")
    if [[ "$status" == "healthy" ]] || docker exec "ai-recruitment-$svc" echo "ok" > /dev/null 2>&1; then
      log "  ✓ $svc OK"
    else
      warn "  ⚠ $svc 状态: $status"
    fi
  done
}

# ── 启动 API（PM2 守护）────────────────────────────────────────────────────
start_api() {
  log "启动 API（PM2 守护）..."
  check_venv

  # 确保 infra 启动
  start_infra

  # 重启已有实例或启动新的
  if pm2 describe ai-recruitment-api > /dev/null 2>&1; then
    pm2 restart ai-recruitment-api --update-env
    log "  ✓ PM2 重启完成"
  else
    pm2 start "$PROJECT_ROOT/apps/api/ecosystem.config.js"
    log "  ✓ PM2 启动完成"
  fi

  # 保存启动列表，开机自动恢复
  pm2 save
  log "  ✓ PM2 进程列表已保存"

  # 等待 API 就绪
  for i in $(seq 1 15); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
      log "  ✓ API 健康检查通过 (8000)"
      return
    fi
    sleep 1
  done
  err "API 启动超时，请检查: pm2 logs ai-recruitment-api"
}

# ── 启动 Web ──────────────────────────────────────────────────────────────
start_web() {
  log "启动 Web 前端..."
  if ! command -v pnpm > /dev/null; then
    err "pnpm 未安装"
    exit 1
  fi
  cd "$PROJECT_ROOT/apps/web" && pnpm dev &
  log "  ✓ Web 启动中 → http://localhost:3000"
}

# ── 查看状态 ──────────────────────────────────────────────────────────────
status() {
  echo ""
  echo "=== Docker 容器 ==="
  docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || echo "(Docker 未运行)"
  echo ""
  echo "=== PM2 进程 ==="
  pm2 list ai-recruitment-api 2>/dev/null || echo "(PM2 无进程)"
  echo ""
  echo "=== API 健康 ==="
  curl -sf http://localhost:8000/health 2>/dev/null || echo "(API 无响应)"
  echo ""
  echo "=== Web 健康 ==="
  curl -sf -o /dev/null -w "HTTP %{http_code}" http://localhost:3000 2>/dev/null || echo "(Web 无响应)"
  echo ""
}

# ── 停止 ────────────────────────────────────────────────────────────────────
stop() {
  log "停止所有服务..."
  pm2 stop ai-recruitment-api 2>/dev/null || true
  docker compose -f "$COMPOSE_FILE" stop 2>/dev/null || true
  log "✓ 已停止"
}

# ── 重启 ─────────────────────────────────────────────────────────────────
restart() {
  stop
  sleep 2
  start_api
}

# ── 主入口 ───────────────────────────────────────────────────────────────
CMD="${1:-all}"

case "$CMD" in
  infra)
    check_docker
    start_infra
    ;;
  api)
    start_api
    ;;
  web)
    start_web
    ;;
  all)
    start_api
    start_web
    echo ""
    log "=== 启动完成 ==="
    echo "  API  → http://localhost:8000/docs"
    echo "  Web  → http://localhost:3000"
    echo "  状态 → ./scripts/start.sh status"
    ;;
  restart)
    restart
    ;;
  status)
    status
    ;;
  stop)
    stop
    ;;
  *)
    echo "用法: $0 {api|web|all|restart|status|stop}"
    echo "  api    - 仅启动 API（含 infra）"
    echo "  infra  - 仅启动基础设施"
    echo "  web    - 仅启动 Web"
    echo "  all    - 启动全部（默认）"
    echo "  status - 查看所有状态"
    echo "  stop   - 停止所有服务"
    ;;
esac