# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM python:3.14-slim-bookworm AS installer

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "pydantic[email]"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────
FROM python:3.14-slim-bookworm AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy site-packages only — not build tools
COPY --from=installer /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=installer /usr/local/bin /usr/local/bin

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--timeout", "120"]
