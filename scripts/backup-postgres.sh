#!/bin/bash
# ═══════════════════════════════════════════════════
#  PostgreSQL Automated Backup Script
#  Run via: docker compose exec postgres /backup.sh
#  Or schedule via cron in the backup service.
# ═══════════════════════════════════════════════════

set -euo pipefail

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/aegis_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting backup..."

# Dump with custom format (compressed)
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -U "${POSTGRES_USER:-aegis}" \
    -d "${POSTGRES_DB:-aegis}" \
    --no-owner \
    --no-privileges \
    --format=custom \
    --compress=9 \
    -f "${BACKUP_FILE%.gz}.dump"

# Also create a plain SQL gz for portability
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -U "${POSTGRES_USER:-aegis}" \
    -d "${POSTGRES_DB:-aegis}" \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

DUMP_SIZE=$(du -h "${BACKUP_FILE%.gz}.dump" | cut -f1)
SQL_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${SQL_SIZE}), ${BACKUP_FILE%.gz}.dump (${DUMP_SIZE})"

# ── Cleanup old backups ──
DELETED=$(find "$BACKUP_DIR" -name "aegis_*.sql.gz" -o -name "aegis_*.dump" | \
    xargs -r ls -t | tail -n +$((RETENTION_DAYS * 2 + 1)) | wc -l)

find "$BACKUP_DIR" -name "aegis_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
find "$BACKUP_DIR" -name "aegis_*.dump" -mtime +${RETENTION_DAYS} -delete

echo "[$(date -Iseconds)] Cleaned up ${DELETED} old backups (retention: ${RETENTION_DAYS} days)"

# ── List current backups ──
echo ""
echo "Current backups:"
ls -lh "$BACKUP_DIR"/aegis_* 2>/dev/null || echo "  (none)"
