#!/bin/bash
set -e

echo "🔄 Running migrations..."
alembic upgrade head 2>/dev/null || echo "⚠️ Migrations skipped (may already be applied)"

echo "🚀 Starting AEGIS v4..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers ${WORKERS:-4} \
  --log-level ${LOG_LEVEL:-info} \
  --limit-concurrency ${MAX_CONCURRENT:-200} \
  --limit-max-requests ${MAX_REQUESTS:-10000} \
  --timeout-keep-alive 30