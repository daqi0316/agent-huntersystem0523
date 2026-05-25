import { test, expect } from "@playwright/test";

test.describe("Reports Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("数据报表");
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
