import { test, expect } from "@playwright/test";

test.describe("Settings Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("系统设置");
  });

  test("settings form fields are present", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const inputs = page.locator("input");
    const count = await inputs.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test("save button is visible", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const saveBtn = page.locator("button").filter({ hasText: /保存|Save/i }).first();
    await expect(saveBtn).toBeVisible();
  });

  test("settings groups use Card layout", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const cards = page.locator('[class*="card"], [class*="Card"]');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });
});
