"""P5-8 + A1 限流 Audit 脚本。

测每个 HTTP 路由是否被限流覆盖, 输出覆盖率报告。
不依赖 pytest/Django, 纯 stdlib + httpx。

用法:
    python scripts/audit_rate_limit.py [--base http://localhost:8000]

输出:
    JSON 报告 + stdout 摘要
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any
from urllib.parse import urljoin

import httpx


# 已知端点 (从 apps/api/app/api/router.py 自动提取, 但部分需要鉴权)
# 简化为: 用 admin token 测 /admin/rate-limit/state, 用匿名测 /auth/login
TEST_ENDPOINTS = [
    {
        "path": "/api/v1/auth/login",
        "method": "POST",
        "auth": "none",
        "expected": "429 after 30 req/min (IP key)",
    },
    {
        "path": "/api/v1/auth/register",
        "method": "POST",
        "auth": "none",
        "expected": "429 after 30 req/min (IP key)",
    },
    {
        "path": "/api/v1/admin/rate-limit/state",
        "method": "GET",
        "auth": "admin",
        "expected": "200 with snapshot",
    },
    {
        "path": "/api/v1/agent/agents",
        "method": "GET",
        "auth": "user",
        "expected": "401 (need auth) or 200 (with token)",
    },
    {
        "path": "/api/v1/pipeline/runs",
        "method": "GET",
        "auth": "user",
        "expected": "401 or 200",
    },
    {
        "path": "/health",
        "method": "GET",
        "auth": "none",
        "expected": "200 (excluded from rate limit)",
    },
    {
        "path": "/metrics",
        "method": "GET",
        "auth": "none",
        "expected": "200 (excluded from rate limit, contains rate_limit_check_total)",
    },
]


async def get_admin_token(client: httpx.AsyncClient, base_url: str) -> str | None:
    """尝试登录拿 admin token. 失败返 None (audit 仍能跑, 跳过 admin 端点)."""
    admin_email = "audit-admin@x.com"
    admin_password = "AuditPass123!"
    try:
        # 先尝试注册
        await client.post(
            urljoin(base_url, "/api/v1/auth/register"),
            json={"email": admin_email, "password": admin_password, "name": "Audit Admin"},
            timeout=5.0,
        )
    except Exception:
        pass
    try:
        resp = await client.post(
            urljoin(base_url, "/api/v1/auth/login"),
            json={"email": admin_email, "password": admin_password},
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token")
    except Exception as e:
        print(f"  ⚠️  admin login failed: {e}", file=sys.stderr)
    return None


async def test_endpoint(
    client: httpx.AsyncClient,
    base_url: str,
    endpoint: dict[str, Any],
    admin_token: str | None,
) -> dict[str, Any]:
    """测单个端点, 记录响应码分布 + 限流触发情况."""
    path = endpoint["path"]
    method = endpoint["method"]
    url = urljoin(base_url, path)
    auth_type = endpoint["auth"]

    headers = {}
    if auth_type == "admin" and admin_token:
        headers["Authorization"] = f"Bearer {admin_token}"

    codes: dict[str, int] = {}
    rate_limited = False
    start = time.monotonic()
    try:
        for _ in range(5):  # 5 次探测, 不用多, audit 不是压测
            resp = await client.request(
                method, url, headers=headers, timeout=5.0,
                json={} if method == "POST" else None,
            )
            code = str(resp.status_code)
            codes[code] = codes.get(code, 0) + 1
            if resp.status_code == 429:
                rate_limited = True
    except Exception as e:
        return {
            "path": path,
            "method": method,
            "error": str(e),
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    return {
        "path": path,
        "method": method,
        "auth": auth_type,
        "codes": codes,
        "rate_limited_triggered": rate_limited,
        "excluded": path in ("/health", "/metrics"),
        "duration_ms": int((time.monotonic() - start) * 1000),
    }


async def check_metrics_rate_limit(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    """检查 /metrics 端点是否暴露 rate_limit_check_total 指标."""
    try:
        resp = await client.get(urljoin(base_url, "/metrics"), timeout=5.0)
        if resp.status_code != 200:
            return {"metrics_endpoint_ok": False, "status": resp.status_code}
        body = resp.text
        has_rate_limit = "rate_limit_check_total" in body
        return {
            "metrics_endpoint_ok": True,
            "has_rate_limit_metric": has_rate_limit,
            "sample_rate_limit_line": next(
                (line for line in body.split("\n") if "rate_limit_check_total" in line),
                None,
            ),
        }
    except Exception as e:
        return {"metrics_endpoint_ok": False, "error": str(e)}


async def main() -> int:
    parser = argparse.ArgumentParser(description="P5-8 限流 audit 脚本")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", help="输出 JSON 报告到文件")
    args = parser.parse_args()

    print(f"=== 限流 Audit — {args.base} ===\n")
    async with httpx.AsyncClient() as client:
        print("1. 拿 admin token...")
        admin_token = await get_admin_token(client, args.base)
        if admin_token:
            print("   ✓ admin token 拿到\n")
        else:
            print("   ⚠️  admin token 拿不到 (admin 端点会跳过)\n")

        print("2. 测各端点限流覆盖...")
        results = []
        for ep in TEST_ENDPOINTS:
            r = await test_endpoint(client, args.base, ep, admin_token)
            results.append(r)
            status = "✓ 限流" if r.get("rate_limited_triggered") else "  "
            excluded = " [排除]" if r.get("excluded") else ""
            codes_str = ",".join(f"{c}={n}" for c, n in (r.get("codes") or {}).items())
            print(f"   {status} {r['method']:6} {r['path']:50} codes=[{codes_str}]{excluded}")

        print("\n3. 检查 /metrics 端点 rate_limit 指标...")
        metrics_check = await check_metrics_rate_limit(client, args.base)
        if metrics_check.get("metrics_endpoint_ok"):
            if metrics_check.get("has_rate_limit_metric"):
                print(f"   ✓ /metrics 含 rate_limit_check_total")
                if metrics_check.get("sample_rate_limit_line"):
                    print(f"     示例: {metrics_check['sample_rate_limit_line']}")
            else:
                print("   ⚠️  /metrics 不含 rate_limit_check_total (需 P5-8 + A1 改造)")
        else:
            print(f"   ✗ /metrics 端点异常: {metrics_check}")
        print()

        summary = {
            "base_url": args.base,
            "timestamp": time.time(),
            "endpoints_tested": len(results),
            "endpoints_rate_limited": sum(1 for r in results if r.get("rate_limited_triggered")),
            "endpoints_excluded": sum(1 for r in results if r.get("excluded")),
            "admin_token_obtained": admin_token is not None,
            "metrics_check": metrics_check,
            "results": results,
        }

        print("=== 摘要 ===")
        print(f"  测 {summary['endpoints_tested']} 端点")
        print(f"  触发限流: {summary['endpoints_rate_limited']}")
        print(f"  排除限流: {summary['endpoints_excluded']} (health/metrics)")
        print(f"  /metrics 含 rate_limit: {metrics_check.get('has_rate_limit_metric', False)}")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            print(f"\n报告写入: {args.output}")

        rate_limited = summary["endpoints_rate_limited"] > 0
        metrics_ok = metrics_check.get("has_rate_limit_metric", False)
        return 0 if (rate_limited and metrics_ok) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
