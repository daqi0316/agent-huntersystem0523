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
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start dev server (hot-reload) — 必须用 make api:dev，不要直接 uvicorn
make api:dev
#  或：cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> **重要**：dev server 必须带 `--reload`。否则改 model/枚举后，旧进程仍用旧字节码，会出现
> "代码已修但生产仍 500" 的假象（2026-06-03 事故根因之一）。

### 2.5. Pre-commit（强烈推荐）

防 model enum 模式 bug 复发（`SAEnum` 漏 `values_callable`、`UUID(as_uuid=False)` schema 漂移）。

```bash
pip install pre-commit
pre-commit install
# 之后每次 commit 会自动跑 scripts/check_model_patterns.py
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
| `make dev` | Start API + web in parallel (docker) |
| `make api:dev` | Start API with hot-reload (**推荐本地开发**) |
| `make test` | Run all backend tests |
| `make coverage` | Tests with coverage report |
| `make db-up` | Start Docker services |
| `make db-migrate` | Run Alembic migrations |

## Development Guards（多层防护）

防 2026-06-03 enum 500 / schema 漂移 500 类事故复发：

- **L1 编译期**：`scripts/check_model_patterns.py`（pre-commit hook）扫危险 model 模式
- **L2 启动期**：`app.core.schema_audit` 在 `lifespan` 启动时比对 model 与 DB enum label，**不一致阻止启动**
- **L3 测试期**：`tests/test_models_enum_integration.py` 真 DB round-trip 测试

详见 `.omo/plans/decision-records/2026-06-03-enum-and-uuid-pattern.md`。

## Tech Stack

- **Runtime**: Python 3.14 / Node.js 20
- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- **Frontend**: Next.js 14, tRPC, Recharts, Tailwind CSS, Framer Motion
- **Agent Engine**: Custom Pipeline / Router / Orchestrator / Gen-Eval agents
- **LLM**: OMLX (local) / vLLM (remote) — graceful degradation on failure
- **Storage**: PostgreSQL, Redis, Qdrant (vector), MinIO (S3-compatible)
- **Tools**: Ruff, Pre-commit, Playwright, Docker Compose
