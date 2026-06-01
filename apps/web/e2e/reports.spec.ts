import { test, expect } from "@playwright/test";

test.describe("Reports Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("数据报表");
  });

  test("shows skeleton loading then chart containers", async ({ page }) => {
    await page.route("**/api/v1/dashboard/reports", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            kpis: [],
            funnel: [],
            source: [],
            monthly_trend: [],
          },
        }),
      });
    });

    await page.goto("/reports");
    await expect(page.locator(".animate-pulse").first()).toBeVisible({ timeout: 2000 });
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 10000 });
  });

  test("displays chart containers", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    const charts = page.locator(".recharts-responsive-container");
    const count = await charts.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("shows data cards with metrics", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    const cards = page.locator("h3");
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });
});
