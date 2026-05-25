#!/usr/bin/env bash
set -euo pipefail

# Start all dev infrastructure, then the API, then the frontend

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Starting infrastructure (PostgreSQL, Qdrant, Redis) ==="
docker compose -f "$ROOT_DIR/docker-compose.dev.yml" up -d postgres qdrant redis 2>&1

echo "=== Starting API server ==="
cd "$ROOT_DIR/apps/api"
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -q && pip install "pydantic[email]" -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!
echo "API PID: $API_PID"

echo "=== Starting Frontend ==="
cd "$ROOT_DIR/apps/web"
pnpm dev &
WEB_PID=$!
echo "Web PID: $WEB_PID"

echo ""
echo "============================================"
echo "  API:      http://localhost:8000"
echo "  Docs:     http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $API_PID $WEB_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
