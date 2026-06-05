/**
 * T6 埋点端到端验证 — apps/web/scripts/verify-t6-telemetry.ts
 *
 * 测：
 *  - 打开抽屉 → drawer_open 事件上报
 *  - 关闭抽屉 → drawer_close 事件上报
 *  - 搜索 → search_use 事件上报
 *  - 导出 → card_export 事件上报
 *  - /metrics 端点能查到对应 counter
 *
 * 用法：cd apps/web && npx tsx scripts/verify-t6-telemetry.ts
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

  // 记录 baseline counters
  const baselineDrawerOpen = await getMetric(
    "frontend_event_total",
    /event="drawer_open"/
  );
  const baselineDrawerClose = await getMetric(
    "frontend_event_total",
    /event="drawer_close"/
  );
  const baselineSearch = await getMetric(
    "frontend_event_total",
    /event="search_use"/
  );
  const baselineExport = await getMetric(
    "frontend_event_total",
    /event="card_export"/
  );

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
      const now = new Date().toISOString();
      const seed = {
        state: {
          dataCards: [
            {
              id: "t6-card-aaa",
              type: "candidate_list",
              title: "T6 候选人 A",
              summary: "",
              payload: null,
              messageId: "msg_t6-aaa",
              createdAt: now,
              isRead: false,
            },
            {
              id: "t6-card-bbb",
              type: "dashboard_stats",
              title: "T6 看板",
              summary: "",
              payload: null,
              messageId: "msg_t6-bbb",
              createdAt: now,
              isRead: false,
            },
          ],
          currentContext: {
            currentCandidateIds: [],
            currentJobIds: [],
            recentTopic: "T6 telemetry test",
            lastToolUsed: undefined,
          },
        },
        version: 1,
      };
      localStorage.setItem("ai-recruitment-agent-store", JSON.stringify(seed));
      const origSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key === "ai-recruitment-agent-store") return;
        return origSetItem.call(this, key, value);
      };
    },
    { token: TEST_TOKEN }
  );

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { id: "t6-user", email: "t6@test.com", role: "hr" },
      }),
    });
  });

  await page.goto(`${WEB_BASE}/agent`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);

  // 打开抽屉 → drawer_open
  await page
    .locator('button[aria-label*="看板"]')
    .first()
    .click({ force: true });
  await page.waitForTimeout(500);
  // 等 5s 队列 flush
  await page.waitForTimeout(5500);

  const afterDrawerOpen = await getMetric(
    "frontend_event_total",
    /event="drawer_open"/
  );
  results.push({
    name: "drawer_open 计数 +1",
    pass: afterDrawerOpen - baselineDrawerOpen >= 1,
    detail: `baseline=${baselineDrawerOpen} now=${afterDrawerOpen}`,
  });

  // 搜索 → search_use
  const searchInput = page.locator('input[placeholder*="搜索"], input[placeholder*="filter" i]').first();
  if ((await searchInput.count()) > 0) {
    await searchInput.fill("T6");
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(5500);

  const afterSearch = await getMetric(
    "frontend_event_total",
    /event="search_use"/
  );
  results.push({
    name: "search_use 计数 +1",
    pass: afterSearch - baselineSearch >= 1,
    detail: `baseline=${baselineSearch} now=${afterSearch}`,
  });

  // 导出 → card_export
  const downloadPromise = page
    .waitForEvent("download", { timeout: 3000 })
    .catch(() => null);
  await page.locator('button[aria-label="导出 JSON"]').first().click();
  await downloadPromise;
  await page.waitForTimeout(5500);

  const afterExport = await getMetric(
    "frontend_event_total",
    /event="card_export"/
  );
  results.push({
    name: "card_export 计数 +1",
    pass: afterExport - baselineExport >= 1,
    detail: `baseline=${baselineExport} now=${afterExport}`,
  });

  // 关闭抽屉 → drawer_close
  await page.keyboard.press("Escape");
  await page.waitForTimeout(5500);

  const afterDrawerClose = await getMetric(
    "frontend_event_total",
    /event="drawer_close"/
  );
  results.push({
    name: "drawer_close 计数 +1",
    pass: afterDrawerClose - baselineDrawerClose >= 1,
    detail: `baseline=${baselineDrawerClose} now=${afterDrawerClose}`,
  });

  // 验证 /metrics 返 prom 文本格式
  const metricsRes = await fetch(`${API_BASE.replace("/api/v1", "")}/metrics`);
  const contentType = metricsRes.headers.get("content-type") ?? "";
  const body = await metricsRes.text();
  const isProm =
    contentType.includes("text/plain") &&
    body.includes("# HELP frontend_event_total") &&
    body.includes("# TYPE frontend_event_total counter");
  results.push({
    name: "/metrics 返 Prometheus 文本格式",
    pass: isProm,
    detail: `content-type=${contentType.split(";")[0]}`,
  });

  // 验证 api_request_total 包含 /api/v1/agent/telemetry
  const apiReqHasTelemetry = body.includes(
    'api_request_total{method="POST",path="/api/v1/agent/telemetry"'
  );
  results.push({
    name: "api_request_total 包含 telemetry 端点",
    pass: apiReqHasTelemetry,
  });

  await browser.close();

  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;
  console.log("\n=== T6 埋点 + /metrics 验证 ===");
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
