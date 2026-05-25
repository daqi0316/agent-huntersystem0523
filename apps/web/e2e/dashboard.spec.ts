import { test, expect } from "@playwright/test";

test.describe("Dashboard Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("数据看板");
  });

  test("displays KPI metric cards", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const kpiCards = page.locator("h3");
    const count = await kpiCards.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test("contains chart area", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const chart = page.locator(".recharts-responsive-container");
    await expect(chart.first()).toBeVisible({ timeout: 10000 });
  });
});
