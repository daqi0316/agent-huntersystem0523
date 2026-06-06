#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Rollback script for AI Recruitment production deployment
# Phase 4 P5-13: 5-minute rollback SOP
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ai-recruitment}"
PREVIOUS_TAG_FILE="${DEPLOY_DIR}/.previous_tag"
CURRENT_TAG_FILE="${DEPLOY_DIR}/.current_tag"
LOG_FILE="${DEPLOY_DIR}/rollback.log"

log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $*" | tee -a "$LOG_FILE"
}

cd "$DEPLOY_DIR"

if [ ! -f "$PREVIOUS_TAG_FILE" ]; then
    log "ERROR: No previous tag found at $PREVIOUS_TAG_FILE"
    log "Manual intervention required. Steps:"
    log "  1. cd $DEPLOY_DIR"
    log "  2. docker compose -f docker-compose.prod.yml ps"
    log "  3. Identify last working image tag from GHCR"
    log "  4. API_IMAGE_TAG=<sha> WEB_IMAGE_TAG=<sha> docker compose -f docker-compose.prod.yml up -d api web"
    exit 1
fi

PREVIOUS_TAG=$(cat "$PREVIOUS_TAG_FILE")
CURRENT_TAG=$(cat "$CURRENT_TAG_FILE" 2>/dev/null || echo "unknown")

log "Initiating rollback..."
log "  Current:  $CURRENT_TAG"
log "  Rolling back to: $PREVIOUS_TAG"

# 1. Pull previous image
log "Pulling previous image: api:$PREVIOUS_TAG"
docker pull "ghcr.io/${GITHUB_REPOSITORY:-your-org/your-repo}/api:$PREVIOUS_TAG"
docker pull "ghcr.io/${GITHUB_REPOSITORY:-your-org/your-repo}/web:$PREVIOUS_TAG"

# 2. Downgrade database if needed
# Note: only run if the failing version added a migration
if [ "${ROLLBACK_DB:-yes}" = "yes" ]; then
    log "Downgrading database..."
    API_IMAGE_TAG="$PREVIOUS_TAG" \
    docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1
fi

# 3. Restart with previous image
log "Restarting services with previous image..."
API_IMAGE_TAG="$PREVIOUS_TAG" \
WEB_IMAGE_TAG="$PREVIOUS_TAG" \
docker compose -f docker-compose.prod.yml up -d --no-deps --remove-orphans api web nginx

# 4. Health check
log "Waiting for health check..."
sleep 15

if curl -fsS https://app.airecruit.com/health > /dev/null; then
    log "✓ Rollback successful: $PREVIOUS_TAG is now live"
    echo "$PREVIOUS_TAG" > "$CURRENT_TAG_FILE"

    # Notify
    if [ -n "${FEISHU_WEBHOOK:-}" ]; then
        curl -X POST "$FEISHU_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"msgtype\":\"text\",\"content\":{\"text\":\"✓ Production rollback complete: $PREVIOUS_TAG\"}}"
    fi
else
    log "✗ Rollback FAILED - health check still failing"
    log "Manual intervention required!"
    if [ -n "${FEISHU_WEBHOOK:-}" ]; then
        curl -X POST "$FEISHU_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"msgtype\":\"text\",\"content\":{\"text\":\"✗ PRODUCTION ROLLBACK FAILED - $PREVIOUS_TAG - manual intervention required\"}}"
    fi
    exit 1
fi
