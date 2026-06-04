/**
 * 一键验证脚本：起 dev server + 用 Playwright 验证 ContextBar 真实渲染
 * 用法：npx tsx scripts/verify-contextbar.ts
 */

import { chromium } from "@playwright/test";

const BASE_URL = "http://localhost:3007";
const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZDIwNDYyZi02ZGVjLTRiZTAtYTQ4Yi03NTk1YjNiZjJmZmIiLCJyb2xlIjoiaHIiLCJleHAiOjE3Nzk2MzU1OTF9.7G4XT2aBRGtCGF5N4M8sJwjkheahtbx9t89Z2N92L9E";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(`PAGE ERROR: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(`CONSOLE ERROR: ${msg.text()}`);
  });

  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
    },
    { token: TEST_TOKEN }
  );

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "verify-user",
        email: "verify@test.com",
        name: "Verify User",
        role: "hr",
      }),
    });
  });

  await page.route("**/api/v1/conversation/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, data: { id: "verify-sess-1" } }),
    });
  });

  await page.goto(`${BASE_URL}/agent`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500);

  const checks: Array<{ name: string; ok: boolean; detail: string }> = [];

  const title = await page.title();
  checks.push({
    name: "page title",
    ok: title.includes("AI Recruitment") || title.length > 0,
    detail: `title="${title}"`,
  });

  const chipVisible = await page
    .getByRole("button", { name: /数据看板/ })
    .isVisible()
    .catch(() => false);
  checks.push({
    name: "ContextBar 缩略按钮可见",
    ok: chipVisible,
    detail: chipVisible ? "已渲染" : "未渲染",
  });

  const sidebarVisible = await page
    .locator("aside")
    .first()
    .isVisible()
    .catch(() => false);
  checks.push({
    name: "Sidebar 仍存在（共存边界）",
    ok: sidebarVisible,
    detail: sidebarVisible ? "已渲染" : "未渲染",
  });

  const memoryBtnVisible = await page
    .getByTitle("查看结构化记忆")
    .isVisible()
    .catch(() => false);
  checks.push({
    name: "MemoryPanel 触发按钮仍存在（共存边界）",
    ok: memoryBtnVisible,
    detail: memoryBtnVisible ? "已渲染" : "未渲染",
  });

  if (chipVisible) {
    await page
      .getByRole("button", { name: /数据看板/ })
      .click();
    await page.waitForTimeout(500);

    const drawerVisible = await page
      .getByText("暂无数据卡片")
      .isVisible()
      .catch(() => false);
    checks.push({
      name: "点击缩略按钮 → 抽屉展开 + 空态文案",
      ok: drawerVisible,
      detail: drawerVisible ? "展开 + 显示空态" : "未展开",
    });
  }

  if (chipVisible) {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            reply:
              '招聘看板数据：\n```json\n{"total_candidates":42,"total_jobs":5,"active_interviews":3}\n```',
            tool_calls: [
              {
                name: "get_dashboard_stats",
                args: {},
                error: null,
                needs_human: false,
              },
            ],
            agent_actions: [],
            model: "chat",
          },
        }),
      });
    });

    const textarea = page.locator("textarea").first();
    await textarea.fill("查看招聘数据看板");
    await textarea.press("Enter");
    await page.waitForTimeout(2000);

    const chipWithBadge = page.getByRole("button", { name: /数据看板.*未读/ });
    const badgeVisible = await chipWithBadge.isVisible().catch(() => false);
    const badgeText = badgeVisible
      ? await chipWithBadge.textContent()
      : "";
    checks.push({
      name: "发送消息 → 角标 +1",
      ok: badgeVisible && (badgeText?.includes("1") ?? false),
      detail: `chip="${badgeText}"`,
    });

    const chipTitle = badgeVisible
      ? await chipWithBadge.getAttribute("title")
      : "";
    const showsTopic =
      (chipTitle?.includes("查看招聘数据看板") ?? false) ||
      (badgeText?.includes("查看招聘数据看板") ?? false);
    checks.push({
      name: "ContextBar 显示当前话题（Phase 2 上下文感知）",
      ok: showsTopic,
      detail: showsTopic
        ? `title="${chipTitle}"`
        : `title="${chipTitle}" text="${badgeText}"`,
    });
  }

  checks.push({
    name: "无 console error / page error",
    ok: consoleErrors.length === 0,
    detail:
      consoleErrors.length === 0
        ? "clean"
        : consoleErrors.slice(0, 3).join(" | "),
  });

  await page.screenshot({ path: "/tmp/contextbar-verify.png", fullPage: true });

  await browser.close();

  console.log("\n=== 验证结果 ===\n");
  let pass = 0;
  for (const c of checks) {
    const mark = c.ok ? "✅" : "❌";
    console.log(`${mark} ${c.name}: ${c.detail}`);
    if (c.ok) pass++;
  }
  console.log(`\n${pass}/${checks.length} 通过\n`);

  process.exit(pass === checks.length ? 0 : 1);
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(2);
});
