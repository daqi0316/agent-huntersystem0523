# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM python:3.14-slim-bookworm AS installer

WORKDIR /build

# System deps for bcrypt + asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "pydantic[email]"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────
FROM python:3.14-slim-bookworm AS runner

WORKDIR /app

# Runtime deps only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_USER=appuser \
    APP_UID=1001

# Create non-root user
RUN groupadd --system --gid ${APP_UID} ${APP_USER} && \
    useradd --system --uid ${APP_UID} --gid ${APP_USER} --no-create-home ${APP_USER}

# Copy site-packages only — not build tools
COPY --from=installer /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=installer /usr/local/bin /usr/local/bin

COPY --chown=${APP_USER}:${APP_USER} . .

USER ${APP_USER}

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=20s \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
