#!/bin/bash
set -e

echo "=== AI Recruitment System - Development Startup ==="
echo ""

# Check prerequisites
check_prereq() {
  if ! command -v "$1" &> /dev/null; then
    echo "[ERROR] $1 is not installed. Please install it first."
    exit 1
  fi
}

check_prereq "pnpm"
check_prereq "docker"
check_prereq "python3"

# Start infrastructure
echo "[1/4] Starting infrastructure (PostgreSQL, Qdrant, Redis, MinIO, RabbitMQ)..."
docker compose -f docker-compose.dev.yml up -d
echo "  -> Infrastructure started. Waiting for services to be ready..."
sleep 3

# Install dependencies
echo ""
echo "[2/4] Installing monorepo dependencies..."
pnpm install

# Create .env if not exists
if [ ! -f .env ]; then
  echo ""
  echo "[INFO] Creating .env from .env.example..."
  cp .env.example .env
  echo "  -> Edit .env to configure your local setup."
fi

# Start backend
echo ""
echo "[3/4] Starting FastAPI backend..."
cd apps/api
if [ ! -d "venv" ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
  pip install -q "pydantic[email]"
else
  source venv/bin/activate
fi
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ../..
echo "  -> Backend starting (PID: $BACKEND_PID)..."

# Start frontend
echo ""
echo "[4/4] Starting Next.js frontend..."
pnpm --filter @ai-recruitment/web dev &
FRONTEND_PID=$!
echo "  -> Frontend starting (PID: $FRONTEND_PID)..."

echo ""
echo "=== All services started ==="
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  MinIO:    http://localhost:9001 (minioadmin:minioadmin)"
echo "  RabbitMQ: http://localhost:15672 (guest:guest)"
echo ""
echo "Press Ctrl+C to stop all services."

# Trap Ctrl+C to clean up
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; docker compose -f docker-compose.dev.yml down; exit 0" SIGINT SIGTERM

wait
