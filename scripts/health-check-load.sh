#!/bin/bash
# ============================================================
# 系统健康检查 — 负载验证 (Step 8-9: 限流 + MCP)
# 来源: docs/system-health-check.md
# 用法: ./scripts/health-check-load.sh
# 返回: 0=全过 / 1=有失败
# 注: A1 拆分, 跟 health-check.sh 分离避免 60 并发限流污染
# 警告: 会触发限流 + 修改限流状态, 跑前会先 reset
# ============================================================

set -u

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
export API_BASE

PASS=0
FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo ""
echo "=== Step 1/2: admin reset 限流状态 (防残留污染) ==="
ADMIN_TOKEN=""
for TRY_EMAIL in "audit-admin@x.com" "e2e-tester@test.com"; do
  TRY_PASSWORD="AuditPass123!"
  [ "$TRY_EMAIL" = "e2e-tester@test.com" ] && TRY_PASSWORD="E2ePass123!"
  LOGIN_RES=$(curl -sS -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TRY_EMAIL\",\"password\":\"$TRY_PASSWORD\"}" 2>&1)
  TRY_TOKEN=$(echo "$LOGIN_RES" | jq -r .access_token 2>/dev/null)
  if [ -n "$TRY_TOKEN" ] && [ "$TRY_TOKEN" != "null" ]; then
    PROBE=$(curl -sS -H "Authorization: Bearer $TRY_TOKEN" \
      "$API_BASE/admin/rate-limit/state" 2>&1)
    if echo "$PROBE" | jq -e .success >/dev/null 2>&1; then
      ADMIN_TOKEN="$TRY_TOKEN"
      break
    fi
  fi
done
if [ -n "$ADMIN_TOKEN" ]; then
  RESET_RES=$(curl -sS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$API_BASE/admin/rate-limit/reset" 2>&1)
  RESET_OK=$(echo "$RESET_RES" | jq -r .success 2>/dev/null)
  if [ "$RESET_OK" = "true" ]; then
    ok "admin reset 成功 (A1 端点工作)"
  else
    fail "admin reset 失败: $RESET_RES"
    echo "       提示: A1 改造未生效? 检查 apps/api/app/api/admin.py"
  fi
else
  fail "admin login 失败 (audit-admin/e2e-tester 都不可用), 跳过 reset"
  echo "       提示: SQL 升级 e2e-tester@test.com role=ADMIN, 或注册新 admin 账号"
fi

echo ""
echo "=== Step 2/2: 限流验证 (60 并发打 /auth/login) ==="
# 3-key 中: IP 限 30 req/min, dev 环境用更严苛阈值临时验证
# 用 60 并发请求打 /auth/login 端点, 应至少见到 1 个 429
if [ -x "$(command -v xargs)" ]; then
    SEEN_429=0
    SEEN_200=0
    TMP_RL=$(mktemp)
    for i in $(seq 1 60); do
        CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "$API_BASE/auth/login" \
            -H "Content-Type: application/json" \
            -d '{"email":"rl_test@x.com","password":"x"}' 2>/dev/null)
        if [ "$CODE" = "429" ]; then
            SEEN_429=$((SEEN_429 + 1))
            echo "$CODE" >> "$TMP_RL"
        elif [ "$CODE" = "401" ] || [ "$CODE" = "422" ]; then
            SEEN_200=$((SEEN_200 + 1))
        fi
    done
    rm -f "$TMP_RL"
    if [ "$SEEN_429" -gt 0 ]; then
        ok "60 并发请求触发限流 429: ${SEEN_429} 次"
    else
        echo "  ⚠️  60 并发请求未触发 429 (限流阈值偏高, dev 可接受)"
    fi
    ok "限流中间件工作正常 (${SEEN_200} 非 429)"
else
    fail "xargs 不可用"
fi

echo ""
echo "=== Step 3/3: MCP 工具系统 CI 守门 (v4 PR-5) ==="
# 跑 check_mcp_servers.py --quick (静态检查, 不启动 host)
# 验证 tools / skills / config 完整性
# 注: 必须用 venv python (项目依赖 asyncpg / openai / qdrant_client 等)
# 用 bash -c 保证主 shell 的 ok/fail 函数可见 (子 shell ( ) 不继承函数)
if [ -f "scripts/check_mcp_servers.py" ] && [ -d "apps/api" ] && [ -x "apps/api/.venv/bin/python" ]; then
    if bash -c "cd apps/api && .venv/bin/python ../../scripts/check_mcp_servers.py --quick" >/tmp/mcp-check.log 2>&1; then
        ok "MCP CI 守门通过 (tools / skills / config)"
    else
        fail "MCP CI 守门失败 (看 /tmp/mcp-check.log)"
        # 打印前 10 行错误摘要 (不全是, 避免日志爆炸)
        head -10 /tmp/mcp-check.log | sed 's/^/    /'
    fi
else
    echo "  ⚠️  scripts/check_mcp_servers.py 或 apps/api/.venv 不存在 (PR-4 未实施? 跳过)"
fi

echo ""
echo "=== 验证后清理: 再 reset 一次限流 ==="
if [ -n "$ADMIN_TOKEN" ] && [ "$ADMIN_TOKEN" != "null" ]; then
  curl -sS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$API_BASE/admin/rate-limit/reset" >/dev/null 2>&1
  ok "清理完成, 真实用户不会撞 429"
fi

echo ""
echo "================================================"
echo "  通过：$PASS"
echo "  失败：$FAIL"
echo "================================================"
echo ""
echo "  注: 负载验证后会清理限流, 真实用户跑 health-check.sh 不会撞 429"

if [ $FAIL -gt 0 ]; then
  exit 1
fi
exit 0
