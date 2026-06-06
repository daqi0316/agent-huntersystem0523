#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# PostgreSQL backup script for AI Recruitment (Phase 4 P5-6)
# - Daily full backup via pg_dump
# - 7 daily / 4 weekly / 12 monthly retention
# - Optional upload to S3-compatible storage (Aliyun OSS)
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backup/postgres}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)
BACKUP_FILE="${BACKUP_DIR}/ai_recruitment_${TIMESTAMP}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-ai_recruitment}"
export PGPASSWORD="${PGPASSWORD:?PGPASSWORD required}"

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $*" | tee -a "$LOG_FILE"
}

log "Starting backup: $BACKUP_FILE"

# 1. pg_dump (compressed)
START_TIME=$(date +%s)
pg_dump \
    --host="$PGHOST" \
    --port="$PGPORT" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --format=custom \
    --no-owner \
    --no-acl \
    --verbose \
    --file="$BACKUP_FILE" 2>>"$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

log "Backup complete: $BACKUP_FILE ($BACKUP_SIZE, ${DURATION}s)"

# 2. Verify backup integrity
log "Verifying backup integrity..."
if pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    log "Backup integrity verified"
else
    log "ERROR: Backup integrity check failed"
    exit 1
fi

# 3. Upload to S3-compatible storage (Aliyun OSS)
if [ -n "${OSS_ACCESS_KEY_ID:-}" ] && [ -n "${OSS_ACCESS_KEY_SECRET:-}" ] && [ -n "${OSS_BUCKET:-}" ]; then
    log "Uploading to OSS: oss://${OSS_BUCKET}/postgres/${TIMESTAMP}.sql.gz"
    # Use ossutil (install via: wget http://gosspublic.alicdn.com/ossutil/1.7.0/ossutil64 && chmod +x)
    if command -v ossutil &> /dev/null; then
        ossutil cp "$BACKUP_FILE" "oss://${OSS_BUCKET}/postgres/$(date +%Y/%m/%d)/" \
            --access-key-id "$OSS_ACCESS_KEY_ID" \
            --access-key-secret "$OSS_ACCESS_KEY_SECRET" \
            --endpoint "${OSS_ENDPOINT:-oss-cn-hangzhou.aliyuncs.com}" 2>>"$LOG_FILE" \
            && log "Uploaded to OSS" \
            || log "WARNING: OSS upload failed (backup still safe locally)"
    else
        log "WARNING: ossutil not installed, skipping OSS upload"
    fi
fi

# 4. Retention policy
log "Applying retention policy..."

# Daily: keep 7 days
find "$BACKUP_DIR" -name "ai_recruitment_*.sql.gz" -mtime +7 -delete 2>/dev/null || true

# Weekly: keep 4 weeks (every Sunday)
if [ "$DAY_OF_WEEK" = "7" ]; then
    WEEKLY_DIR="${BACKUP_DIR}/weekly"
    mkdir -p "$WEEKLY_DIR"
    cp "$BACKUP_FILE" "${WEEKLY_DIR}/ai_recruitment_week_${TIMESTAMP}.sql.gz"
    find "$WEEKLY_DIR" -name "ai_recruitment_week_*.sql.gz" -mtime +28 -delete 2>/dev/null || true
    log "Weekly snapshot created"
fi

# Monthly: keep 12 months (first day of month)
if [ "$DAY_OF_MONTH" = "01" ]; then
    MONTHLY_DIR="${BACKUP_DIR}/monthly"
    mkdir -p "$MONTHLY_DIR"
    cp "$BACKUP_FILE" "${MONTHLY_DIR}/ai_recruitment_month_${TIMESTAMP}.sql.gz"
    find "$MONTHLY_DIR" -name "ai_recruitment_month_*.sql.gz" -mtime +365 -delete 2>/dev/null || true
    log "Monthly snapshot created"
fi

# 5. Report
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "ai_recruitment_*.sql.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup pool: ${TOTAL_BACKUPS} files, ${TOTAL_SIZE} total"
log "Backup completed successfully"

# 6. Alert on failure (in real deployment, send to Feishu webhook)
# curl -X POST "$FEISHU_WEBHOOK" -d "{\"msgtype\":\"text\",\"content\":{\"text\":\"PostgreSQL backup succeeded: $BACKUP_FILE\"}}"

exit 0
