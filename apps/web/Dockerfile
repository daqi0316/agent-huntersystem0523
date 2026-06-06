# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM node:20-alpine AS installer
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

# Copy workspace manifests first for layer caching
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json .npmrc* ./
COPY apps/web/package.json apps/web/
COPY packages/ packages/

RUN pnpm install --frozen-lockfile

# ── Stage 2: Build Next.js standalone ─────────────────────────────────────
FROM node:20-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

COPY --from=installer /app .
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_OUTPUT=standalone \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN pnpm --filter @ai-recruitment/web build

# ── Stage 3: Production runner ────────────────────────────────────────────
FROM node:20-alpine AS runner

# wget for healthcheck, tini for signal handling
RUN apk add --no-cache wget tini

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    APP_USER=appuser \
    APP_UID=1001

RUN addgroup --system --gid ${APP_UID} ${APP_USER} && \
    adduser --system --uid ${APP_UID} --ingroup ${APP_USER} --no-create-home ${APP_USER}

WORKDIR /app

# Copy standalone output (includes server.js + node_modules)
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/apps/web/.next/standalone .
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/apps/web/.next/static apps/web/.next/static
COPY --from=builder --chown=${APP_USER}:${APP_USER} /app/apps/web/public apps/web/public

USER ${APP_USER}

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "apps/web/server.js"]
