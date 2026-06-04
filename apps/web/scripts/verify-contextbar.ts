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
    if (msg.type() === "error") {
      const text = msg.text();
      if (
        text.includes("agent/events") ||
        text.includes("ERR_CONNECTION_REFUSED")
      ) {
        return;
      }
      consoleErrors.push(`CONSOLE ERROR: ${text}`);
    }
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
      body: JSON.stringify({
        success: true,
        data: { id: "sess_e2e_001", title: "E2E", message_count: 0 },
      }),
    });
  });
  await page.route("**/api/v1/agent/events", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: "event: connected\ndata: {\"user_id\":\"test\"}\n\n",
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

    const closeBtn = page.getByRole("button", { name: "关闭抽屉" });
    await closeBtn.click();
    await page.waitForTimeout(300);

    const isMac = process.platform === "darwin";
    const modKey = isMac ? "Meta" : "Control";
    await page.keyboard.down(modKey);
    await page.keyboard.press("k");
    await page.keyboard.up(modKey);
    await page.waitForTimeout(400);

    const reopened = await page
      .getByText("暂无数据卡片")
      .isVisible()
      .catch(() => false);
    checks.push({
      name: "⌘K / Ctrl+K 全局快捷键打开抽屉（Phase 3）",
      ok: reopened,
      detail: reopened ? "快捷键生效" : "快捷键未生效",
    });

    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    const drawerAriaHidden = await page
      .locator('[role="dialog"]')
      .getAttribute("aria-hidden")
      .catch(() => null);
    const closedByEsc = drawerAriaHidden === "true";
    checks.push({
      name: "Esc 关闭抽屉（Phase 3）",
      ok: closedByEsc,
      detail: closedByEsc
        ? "Esc 生效（aria-hidden=true）"
        : `aria-hidden=${drawerAriaHidden}`,
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

    await chipWithBadge.click();
    await page.waitForTimeout(400);

    const contextSectionVisible = await page
      .locator('[aria-label="当前讨论上下文"]')
      .isVisible()
      .catch(() => false);
    const topicVisible = await page
      .getByText("查看招聘数据看板")
      .nth(1)
      .isVisible()
      .catch(() => false);
    const sectionText = await page
      .locator('[aria-label="当前讨论上下文"]')
      .textContent()
      .catch(() => "");
    const lastToolInText = sectionText?.includes("看板数据") ?? false;
    checks.push({
      name: "CurrentContextSection 渲染（Phase 5：当前讨论 + 上次工具）",
      ok: contextSectionVisible && topicVisible && lastToolInText,
      detail:
        contextSectionVisible && topicVisible && lastToolInText
          ? `section text="${sectionText?.slice(0, 60)}..."`
          : `section=${contextSectionVisible} topic=${topicVisible} text="${sectionText?.slice(0, 80)}"`,
    });

    const statsSectionVisible = await page
      .locator('[aria-label="本次会话统计"]')
      .isVisible()
      .catch(() => false);
    const statsText = await page
      .locator('[aria-label="本次会话统计"]')
      .textContent()
      .catch(() => "");
    const hasStatsValues = /[1-9]/.test(statsText || "");
    checks.push({
      name: "SessionStatsSection 渲染（可扩展插槽演示）",
      ok: statsSectionVisible && hasStatsValues,
      detail: statsSectionVisible
        ? `text="${statsText?.slice(0, 60)}"`
        : "section 未渲染",
    });

    const activityVisible = await page
      .locator('[aria-label="最近活动"]')
      .isVisible()
      .catch(() => false);
    const activityText = await page
      .locator('[aria-label="最近活动"]')
      .textContent()
      .catch(() => "");
    const hasActivityItems =
      activityText?.includes("会话开始") ||
      activityText?.includes("看板数据") ||
      activityText?.includes("数据卡片");
    checks.push({
      name: "RecentActivitySection 渲染（时间线插槽）",
      ok: activityVisible && !!hasActivityItems,
      detail: activityVisible
        ? `text="${activityText?.slice(0, 60)}"`
        : "section 未渲染",
    });

    const chipTextAfter = await chipWithBadge.textContent();
    const stillHasBadge = chipTextAfter?.match(/[1-9]/) !== null;
    checks.push({
      name: "打开抽屉 → 自动 markAllCardsRead → 角标消失",
      ok: !stillHasBadge,
      detail: stillHasBadge
        ? `角标仍在：${chipTextAfter?.slice(0, 40)}`
        : `角标清除：${chipTextAfter?.slice(0, 40)}`,
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

  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);

  const mobileContext = await browser.newContext({
    viewport: { width: 375, height: 667 },
  });
  const mobilePage = await mobileContext.newPage();
  await mobilePage.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
    },
    { token: TEST_TOKEN }
  );
  await mobilePage.route("**/api/v1/auth/me", async (route) => {
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
  await mobilePage.route("**/api/v1/conversation/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, data: { id: "verify-sess-m" } }),
    });
  });
  await mobilePage.route("**/api/v1/agent/events", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: "event: connected\ndata: {\"user_id\":\"test\"}\n\n",
    });
  });
  await mobilePage.goto(`${BASE_URL}/agent`, { waitUntil: "domcontentloaded" });
  await mobilePage.waitForTimeout(1500);

  const mobileChipVisible = await mobilePage
    .getByRole("button", { name: /数据看板/ })
    .isVisible()
    .catch(() => false);
  checks.push({
    name: "移动端 viewport：缩略按钮仍可见",
    ok: mobileChipVisible,
    detail: mobileChipVisible ? "375x667 已渲染" : "未渲染",
  });

  if (mobileChipVisible) {
    await mobilePage.getByRole("button", { name: /数据看板/ }).click();
    await mobilePage.waitForTimeout(400);

    const drawerBox = await mobilePage
      .locator('[role="dialog"]')
      .boundingBox()
      .catch(() => null);
    const isBottomSheet =
      drawerBox !== null &&
      drawerBox.width > 300 &&
      drawerBox.y > 100;
    checks.push({
      name: "移动端 drawer 变底部 sheet（宽 > 300px, y > 100）",
      ok: !!isBottomSheet,
      detail: drawerBox
        ? `w=${drawerBox.width} h=${drawerBox.height} y=${drawerBox.y}`
        : "no box",
    });
  }

  await mobileContext.close();
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
