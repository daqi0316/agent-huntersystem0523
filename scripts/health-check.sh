#!/bin/bash
# ============================================================
# 系统健康检查 — 日常快查 (Step 1-7)
# 来源: docs/system-health-check.md
# 用法: ./scripts/health-check.sh
# 返回: 0=全过 / 1=有失败
# 注: A1 拆分, 限流验证 + MCP 守门见 health-check-load.sh
# ============================================================

set -u

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
# WEB_BASE 默认 3000 — 用户 pnpm dev 实际跑在 3000。 之前 3007 daemonize 启的 next dev 不稳 (CLAUDE.md 模式 4)
WEB_BASE="${WEB_BASE:-http://localhost:3000}"
export WEB_BASE API_BASE
TEST_EMAIL="${TEST_EMAIL:-e2e-tester@test.com}"
TEST_PASSWORD="${TEST_PASSWORD:-E2ePass123!}"

PASS=0
FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo ""
echo "=== Step 1/7: 基础设施（postgres/redis/qdrant/minio）==="
MISSING=()
for port in 5432 6379 6333 9000; do
  if ! lsof -i:$port >/dev/null 2>&1; then
    MISSING+=("$port")
  fi
done
if [ ${#MISSING[@]} -eq 0 ]; then
  ok "5432/6379/6333/9000 全部 LISTEN"
else
  fail "缺失端口：${MISSING[*]}"
  echo "       修复：docker compose -f docker-compose.dev.yml up -d postgres redis qdrant minio"
fi

echo ""
echo "=== Step 2/7: 后端进程（uvicorn 8000）==="
if lsof -i:8000 >/dev/null 2>&1; then
  ok "uvicorn 8000 在跑"
else
  fail "uvicorn 未运行"
  echo "       修复：cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
fi

echo ""
echo "=== Step 3/7: 后端可登录（POST /auth/login）==="
LOGIN_RES=$(curl -sS -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" 2>&1)
TOKEN=$(echo "$LOGIN_RES" | jq -r .access_token 2>/dev/null)
if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
  ok "登录成功 token=${TOKEN:0:20}..."
else
  fail "登录失败：$LOGIN_RES"
  echo "       提示：先 POST /auth/register 注册用户"
fi

echo ""
echo "=== Step 4/7: 后端可验证（GET /auth/me）==="
if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
  ME_RES=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/auth/me" 2>&1)
  EMAIL=$(echo "$ME_RES" | jq -r .email 2>/dev/null)
  if [ -n "$EMAIL" ] && [ "$EMAIL" != "null" ]; then
    ok "/auth/me 返回 user email=$EMAIL"
  else
    fail "/auth/me 失败：$ME_RES"
  fi
else
  fail "跳过（无 token）"
fi

echo ""
echo "=== Step 5/7: 前端可达（HTML + _next 资源都必须 200）==="
# /login 应直接 200（公开页）；/agent 未登录应 307 重定向到 /login（这是预期行为，不是 fail）
for path in /login /agent; do
  CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$WEB_BASE$path" 2>&1)
  if [ "$CODE" = "200" ]; then
    ok "GET $path → 200"
  elif [ "$CODE" = "307" ] && [ "$path" = "/agent" ]; then
    # /agent 重定向是预期（dev 行为：未登录跳 /login）；CI 上是 dev 模式
    ok "GET $path → 307（未登录重定向，预期）"
  else
    fail "GET $path → $CODE"
  fi
  CHUNK=$(curl -sS "$WEB_BASE$path" 2>/dev/null | grep -oE '/_next/static/chunks/[^"?]*\.js' | head -1)
  if [ -n "$CHUNK" ]; then
    CCODE=$(curl -sS -o /dev/null -w "%{http_code}" "$WEB_BASE$CHUNK" 2>&1)
    if [ "$CCODE" = "200" ]; then
      ok "  _next chunk 200"
    else
      fail "  _next chunk $CCODE（$CHUNK）— 浏览器会 'Failed to fetch'！"
    fi
  fi
done

echo ""
echo "=== Step 6/7: 端到端登录（Playwright 真实后端）==="
if [ -x "$(command -v npx)" ]; then
  if [ -f "apps/web/scripts/verify-login-e2e.ts" ]; then
    if (cd apps/web && npx tsx "scripts/verify-login-e2e.ts") >/tmp/login-e2e.log 2>&1; then
      ok "verify-login-e2e.ts 通过"
    else
      fail "verify-login-e2e.ts 失败（看 /tmp/login-e2e.log）"
    fi
  else
    fail "verify-login-e2e.ts 还未写（待办）"
  fi
else
  fail "npx 不可用"
fi

echo ""
echo "=== Step 7/7: 微信扫码登录 (P5-2 mock 模式) ==="
QR_RES=$(curl -sS "$API_BASE/auth/wechat/qrcode" 2>&1)
QR_STATE=$(echo "$QR_RES" | jq -r .data.state 2>/dev/null)
QR_MOCK=$(echo "$QR_RES" | jq -r .data.mock 2>/dev/null)
if [ -n "$QR_STATE" ] && [ "$QR_STATE" != "null" ]; then
  ok "GET /auth/wechat/qrcode → state=${QR_STATE:0:16}... mock=$QR_MOCK"
else
  fail "GET /auth/wechat/qrcode 失败: $QR_RES"
fi

if [ "$QR_MOCK" = "true" ]; then
  LOGIN_RES=$(curl -sS -X POST "$API_BASE/auth/wechat/mock-login?code=mock_healthcheck" 2>&1)
  WX_TOKEN=$(echo "$LOGIN_RES" | jq -r .data.access_token 2>/dev/null)
  WX_ORG=$(echo "$LOGIN_RES" | jq -r .data.org_id 2>/dev/null)
  if [ -n "$WX_TOKEN" ] && [ "$WX_TOKEN" != "null" ]; then
    ok "POST /auth/wechat/mock-login → token=${WX_TOKEN:0:20}... org=$WX_ORG"
    ME_RES=$(curl -sS -H "Authorization: Bearer $WX_TOKEN" "$API_BASE/auth/me" 2>&1)
    ME_EMAIL=$(echo "$ME_RES" | jq -r .email 2>/dev/null)
    if [ -n "$ME_EMAIL" ] && [ "$ME_EMAIL" != "null" ]; then
      ok "  /auth/me 微信 user 验证通过: $ME_EMAIL"
    else
      fail "  /auth/me 微信登录后失败: $ME_RES"
    fi
  else
    fail "POST /auth/wechat/mock-login 失败: $LOGIN_RES"
  fi
else
  echo "  ⚠️  微信真模式 (WECHAT_MOCK_MODE=false), 跳过 mock-login 检查"
fi

echo ""
echo "================================================"
echo "  通过：$PASS"
echo "  失败：$FAIL"
echo "================================================"
echo ""
echo "  提示: 限流验证 + MCP 守门在 health-check-load.sh 单独跑"
echo "        避免 60 并发打 /auth/login 留下限流污染"

if [ $FAIL -gt 0 ]; then
  exit 1
fi
exit 0
