import { test, expect } from "@playwright/test";

const DASHBOARD_API = "**/api/v1/dashboard/stats";

test.describe("Dashboard Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("数据看板");
  });

  test("shows skeleton loading on initial load", async ({ page }) => {
    await page.route(DASHBOARD_API, async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            kpis: [
              { label: "候选人", value: 10, key: "candidates" },
              { label: "进行中", value: 5, key: "active" },
              { label: "面试", value: 3, key: "interviews" },
              { label: "录用", value: 1, key: "offers" },
            ],
            trend: [{ date: "2026-05-01", count: 5 }],
            recent_activities: [],
          },
        }),
      });
    });

    await page.goto("/dashboard");
    await expect(page.locator(".animate-pulse").first()).toBeVisible({ timeout: 2000 });
    // Wait for skeleton to disappear
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 10000 });
  });

  test("displays KPI metric cards", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const kpiCards = page.locator("h3");
    const count = await kpiCards.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test("fails gracefully on API error", async ({ page }) => {
    await page.route(DASHBOARD_API, async (route) => {
      await route.fulfill({ status: 500, body: "Server Error" });
    });

    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Should show fallback data or error badge, not crash
    await expect(page.locator("h1")).toContainText("数据看板");
    const errorBadge = page.locator("text=无法连接");
    const kpiCards = page.locator("h3");
    // Either error badge shows or fallback KPIs render
    const hasError = await errorBadge.isVisible().catch(() => false);
    const hasKpis = (await kpiCards.count()) >= 3;
    expect(hasError || hasKpis).toBeTruthy();
  });

  test("contains chart area", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const chart = page.locator(".recharts-responsive-container");
    await expect(chart.first()).toBeVisible({ timeout: 10000 });
  });
});
