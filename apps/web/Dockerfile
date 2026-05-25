# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM node:20-alpine AS installer
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

# Copy workspace manifests first for layer caching
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/
COPY packages/ packages/

RUN pnpm install --frozen-lockfile

# ── Stage 2: Build Next.js standalone ─────────────────────────────────────
FROM node:20-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

COPY --from=installer /app .
COPY . .

ENV NEXT_OUTPUT=standalone
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_WS_URL=ws://localhost:8000

RUN pnpm --filter @ai-recruitment/web build

# ── Stage 3: Production runner ────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy standalone output (includes server.js + node_modules)
COPY --from=builder /app/apps/web/.next/standalone .

# Copy static assets that standalone doesn't bundle
COPY --from=builder /app/apps/web/.next/static apps/web/.next/static
COPY --from=builder /app/apps/web/public apps/web/public

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "apps/web/server.js"]
