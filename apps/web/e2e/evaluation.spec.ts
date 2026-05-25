import { test, expect } from "@playwright/test";

test.describe("Evaluation Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("评估报告");
  });

  test("search input is interactive", async ({ page }) => {
    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    if (await searchInput.isVisible()) {
      await searchInput.fill("测试候选人");
      await expect(searchInput).toHaveValue("测试候选人");
    }
  });

  test("radar chart or table is present", async ({ page }) => {
    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    const chart = page.locator(".recharts-responsive-container").first();
    const table = page.locator("table").first();
    const chartVisible = await chart.isVisible().catch(() => false);
    const tableVisible = await table.isVisible().catch(() => false);
    expect(chartVisible || tableVisible).toBeTruthy();
  });
});
