.PHONY: dev up down ps logs api web test help

# ── Development ────────────────────────────────────────────────────────────

dev:		## Start all services for development (infra + api + web)
	docker compose -f docker-compose.dev.yml --profile full up --build -d
	@echo "API → http://localhost:8000/docs"
	@echo "Web → http://localhost:3000"

dev:infra:	## Start only infrastructure (postgres, redis, qdrant, minio, rabbitmq)
	docker compose -f docker-compose.dev.yml up -d

up:		## Start production stack (infra + api + web, no GPU)
	docker compose --profile production up --build -d

up:gpu:		## Start production stack with vLLM GPU inference
	docker compose --profile gpu up --build -d

down:		## Stop all containers and remove volumes
	docker compose -f docker-compose.dev.yml down -v 2>/dev/null; \
	docker compose down -v 2>/dev/null

ps:		## List running containers
	docker compose -f docker-compose.dev.yml ps 2>/dev/null; \
	echo "---"; \
	docker compose ps 2>/dev/null

logs:		## Tail logs for all services
	docker compose -f docker-compose.dev.yml logs -f 2>/dev/null || \
	docker compose logs -f 2>/dev/null

# ── API ────────────────────────────────────────────────────────────────────

api:dev:	## Start API with hot-reload (requires infra)
	nohup $(MAKE) _api:run-detached >/dev/null 2>&1 &

api:watch:	## Run API watchdog (auto-restart on death)
	cd apps/api && nohup ../../apps/api/.venv/bin/python -m app.scripts.api_watchdog > /tmp/wd-stdout.log 2>&1 &

_api:run-detached:	## Internal: double-fork daemonize uvicorn
	cd apps/api && .venv/bin/python -c "import os,sys;pid=os.fork();\
sys.exit(0) if pid>0 else None;os.setsid();pid=os.fork();\
sys.exit(0) if pid>0 else None;\
log=os.open('/tmp/uvicorn.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o644);\
devnull=os.open(os.devnull,os.O_RDONLY);\
os.dup2(devnull,0);os.dup2(log,1);os.dup2(log,2);\
os.execv('.venv/bin/python',['../apps/api/.venv/bin/python','-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000'])"
	cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

api:migrate:	## Run Alembic migrations
	cd apps/api && alembic upgrade head

api:check-schema:	## Compare SQLAlchemy models with current DB schema (alembic check)
	cd apps/api && alembic check

api:test:	## Run API tests
	cd apps/api && python -m pytest tests/ -v --tb=short

# ── Web ────────────────────────────────────────────────────────────────────

web:dev:	## Start Next.js dev server
	cd apps/web && pnpm dev

web:build:	## Build Next.js
	cd apps/web && pnpm build

web:e2e:	## Run Playwright E2E tests (start API first)
	cd apps/web && npx playwright test

# ── CI ─────────────────────────────────────────────────────────────────────

test:		## Run all backend tests
	cd apps/api && python -m pytest tests/ -v --tb=short --no-header 2>&1 | tail -20

coverage:	## Run tests with coverage
	cd apps/api && python -m pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=50

# ── Help ───────────────────────────────────────────────────────────────────

help:		## Show this help
	@grep -E '^[a-zA-Z:_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
