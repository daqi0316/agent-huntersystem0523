# AI Recruitment System

> 智能招聘管理系统 — AI 驱动的候选人初筛、评估与面试管理。

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│          Next.js (apps/web)                      │
│         tRPC / Recharts / Tailwind               │
└──────────────────────┬──────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────┐
│                   Backend API                    │
│       FastAPI (apps/api) — REST + SSE            │
│    Auth │ Agent │ Pipeline │ Orchestrator ...     │
└────┬─────────┬──────────┬──────────┬────────────┘
     │         │          │          │
┌────▼──┐ ┌───▼───┐ ┌───▼───┐ ┌───▼────────┐
│Postgres│ │ Redis │ │ Qdrant│ │ MinIO      │
│(main DB)│ │(cache)│ │(vector)│ │(file store)│
└────────┘ └───────┘ └───────┘ └────────────┘
```

### Layers

| Layer | Tech | Purpose |
|-------|------|---------|
| **Frontend** | Next.js 14, tRPC, Recharts | Dashboard, candidates, screening UI |
| **Backend API** | FastAPI, SQLAlchemy, Alembic | REST endpoints, auth, LLM agents |
| **AI Agents** | Pipeline, Orchestrator, Router | Resume screening, evaluation, report generation |
| **LLM** | OMLX / vLLM adapter | Chat completion, embeddings |
| **Storage** | PostgreSQL (primary), Redis (cache), Qdrant (vector), MinIO (files) | Data persistence |

## Quick Start

### Prerequisites

- Python 3.14+
- Node.js 20+
- pnpm 9+
- Docker (for PostgreSQL, Redis, Qdrant, MinIO)

### 1. Start infrastructure

```bash
docker compose up -d postgres redis qdrant minio
```

### 2. Backend

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start dev server (hot-reload)
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd apps/web
pnpm install
pnpm dev
```

Visit http://localhost:3000

## API Overview

| Prefix | Description |
|--------|-------------|
| `GET /health` | Health check |
| `GET /metrics` | Basic metrics |
| `/api/v1/auth` | Authentication (login / register) |
| `/api/v1/candidates` | Candidate CRUD |
| `/api/v1/jobs` | Job position CRUD |
| `/api/v1/applications` | Application CRUD |
| `/api/v1/pipeline` | AI resume screening pipeline |
| `/api/v1/evaluation` | Multi-dimension evaluation |
| `/api/v1/interview` | Interview scheduling |
| `/api/v1/knowledge` | RAG knowledge base |
| `/api/v1/dashboard` | Dashboard statistics |

Full docs at http://localhost:8000/docs (Swagger) or /redoc (ReDoc).

## Testing

```bash
# Backend unit tests with coverage
cd apps/api
python -m pytest tests/ --cov=app --cov-fail-under=50

# E2E (requires both API and web running)
cd apps/web
npx playwright test
```

## Key Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start API + web in parallel |
| `make test` | Run all backend tests |
| `make coverage` | Tests with coverage report |
| `make db-up` | Start Docker services |
| `make db-migrate` | Run Alembic migrations |

## Tech Stack

- **Runtime**: Python 3.14 / Node.js 20
- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- **Frontend**: Next.js 14, tRPC, Recharts, Tailwind CSS, Framer Motion
- **Agent Engine**: Custom Pipeline / Router / Orchestrator / Gen-Eval agents
- **LLM**: OMLX (local) / vLLM (remote) — graceful degradation on failure
- **Storage**: PostgreSQL, Redis, Qdrant (vector), MinIO (S3-compatible)
- **Tools**: Ruff, Pre-commit, Playwright, Docker Compose
