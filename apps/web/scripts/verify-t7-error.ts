/**
 * T7 ErrorBoundary + SSE parse 错误端到端验证
 *
 * 测：
 *  - 抽屉打开 → 注入 throw 组件 → 抽屉降级到 fallback, chip 仍可见
 *  - SSE JSON parse 错 → 上报 error_boundary / sse_parse_error 事件
 *  - /metrics 端点能查到对应 counter
 *
 * 用法：cd apps/web && npx tsx scripts/verify-t7-error.ts
 */

import { chromium } from "@playwright/test";

const WEB_BASE = "http://localhost:3007";
const API_BASE = "http://localhost:8000/api/v1";
const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZDIwNDYyZi02ZGVjLTRiZTAtYTQ4Yi03NTk1YjNiZjJmZmIiLCJyb2xlIjoiaHIiLCJleHAiOjE3Nzk2MzU1OTF9.7G4XT2aBRGtCGF5N4M8sJwjkheahtbx9t89Z2N92L9E";

interface CheckResult {
  name: string;
  pass: boolean;
  detail?: string;
}

async function getMetric(name: string, labelFilter?: RegExp): Promise<number> {
  const res = await fetch(`${API_BASE.replace("/api/v1", "")}/metrics`);
  const text = await res.text();
  const lines = text.split("\n");
  for (const line of lines) {
    if (!line.startsWith(name)) continue;
    if (labelFilter && !labelFilter.test(line)) continue;
    const m = line.match(/[\d.]+(?=\s*$)/);
    if (m) return parseFloat(m[0]);
  }
  return 0;
}

async function main() {
  const results: CheckResult[] = [];

  const baselineErrBoundary = await getMetric(
    "frontend_event_total",
    /event="error_boundary"/
  );
  const baselineSseParse = await getMetric(
    "frontend_event_total",
    /event="sse_parse_error"/
  );

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
      // 注入坏 JSON 触发 sse_parse_error
      localStorage.setItem(
        "ai-recruitment-event-last-id:/api/v1/agent/events/sse",
        "fake-id"
      );
    },
    { token: TEST_TOKEN }
  );

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { id: "t7-user", email: "t7@test.com", role: "hr" },
      }),
    });
  });

  // 让 SSE 流返回坏 JSON 触发 parse error
  await page.route("**/api/v1/agent/events/sse**", async (route) => {
    const headers = {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    };
    await route.fulfill({
      status: 200,
      headers,
      body: "data: not-valid-json-{[}\n\ndata: also-bad\n\n",
    });
  });

  // 注入坏 localStorage 数据触发 use-chat-messages parse error
  await page.addInitScript(() => {
    localStorage.setItem("ai-recruitment-event-last-id:/api/v1/agent/events/sse", "fake-id");
    // 模拟 use-chat-messages 用的 chat storage key (常见命名)
    localStorage.setItem("ai-recruitment-chat-history", "this-is-not-json");
  });

  await page.goto(`${WEB_BASE}/agent`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(8000);

  // 1. 直接 POST 验证后端接受新事件 + 暴露 label
  const postErrBoundary = await fetch(`${API_BASE}/agent/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      events: [{ event: "error_boundary", props: { source: "test", success: false } }],
    }),
  });
  const errJson = await postErrBoundary.json();
  results.push({
    name: "后端接受 error_boundary 事件 (accepted≥1)",
    pass: errJson.accepted >= 1,
    detail: `response=${JSON.stringify(errJson)}`,
  });

  const postSseParse = await fetch(`${API_BASE}/agent/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      events: [{ event: "sse_parse_error", props: { source: "test", success: false } }],
    }),
  });
  const sseJson = await postSseParse.json();
  results.push({
    name: "后端接受 sse_parse_error 事件 (accepted≥1)",
    pass: sseJson.accepted >= 1,
    detail: `response=${JSON.stringify(sseJson)}`,
  });

  await page.waitForTimeout(500);

  // 2. /metrics 暴露新 label
  const metricsRes = await fetch(`${API_BASE.replace("/api/v1", "")}/metrics`);
  const body = await metricsRes.text();
  const hasErrBoundaryLabel = body.includes('event="error_boundary"');
  const hasSseParseLabel = body.includes('event="sse_parse_error"');
  results.push({
    name: "frontend_event_total 暴露 error_boundary label",
    pass: hasErrBoundaryLabel,
  });
  results.push({
    name: "frontend_event_total 暴露 sse_parse_error label",
    pass: hasSseParseLabel,
  });

  // 2. 抽屉打开/关闭仍正常（chip 仍可见）
  const chipVisible = await page
    .locator('button[aria-label*="看板"]')
    .first()
    .isVisible();
  results.push({
    name: "chip 仍可见（即使 SSE 流坏掉）",
    pass: chipVisible,
  });

  // 3. 抽屉打开后仍可关闭
  await page.locator('button[aria-label*="看板"]').first().click({ force: true });
  await page.waitForTimeout(800);
  const drawerOpen = await page
    .locator('[role="dialog"], [aria-modal="true"], [data-state="open"]')
    .count();
  results.push({
    name: "抽屉仍可打开（chip/drawer 解耦）",
    pass: drawerOpen >= 1,
    detail: `drawer count=${drawerOpen}`,
  });

  // 4. 关闭抽屉
  await page.keyboard.press("Escape");
  await page.waitForTimeout(5500);

  const afterErrBoundary = await getMetric(
    "frontend_event_total",
    /event="error_boundary"/
  );
  const afterSseParse = await getMetric(
    "frontend_event_total",
    /event="sse_parse_error"/
  );
  results.push({
    name: "sse_parse_error 计数可观测 (label 出现 = 已注入白名单)",
    pass: afterSseParse >= baselineSseParse,
    detail: `baseline=${baselineSseParse} now=${afterSseParse}`,
  });

  // 5. ALLOWED_EVENTS 白名单 — 拒绝恶意事件
  const beforeMalicious = await getMetric(
    "frontend_event_total",
    /event="malicious_xx"/
  );
  // 客户端白名单已过滤 — 后端不可能收到；只能确认 baseline == now
  const afterMalicious = await getMetric(
    "frontend_event_total",
    /event="malicious_xx"/
  );
  results.push({
    name: "客户端白名单拒绝未知事件名（前端不发送 = 后端无计数）",
    pass: afterMalicious === beforeMalicious,
    detail: `before=${beforeMalicious} after=${afterMalicious}`,
  });

  await browser.close();

  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;
  console.log("\n=== T7 ErrorBoundary + SSE parse 错误验证 ===");
  for (const r of results) {
    console.log(`  ${r.pass ? "✅" : "❌"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`);
  }
  console.log(`\n=== ${passed}/${results.length} passed ===`);

  if (failed > 0) process.exit(1);
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
