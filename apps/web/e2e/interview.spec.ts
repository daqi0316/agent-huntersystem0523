import { test, expect } from "@playwright/test";

test.describe("Interview Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/interview");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("面试管理");
  });

  test("page has DataTable with columns", async ({ page }) => {
    await page.goto("/interview");
    await page.waitForLoadState("networkidle");

    const table = page.locator("table");
    await expect(table).toBeVisible({ timeout: 10000 });

    const ths = page.locator("th");
    const count = await ths.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test("create interview button works", async ({ page }) => {
    await page.goto("/interview");
    await page.waitForLoadState("networkidle");

    const createBtn = page.locator("button").filter({ hasText: /新建面试|创建/i }).first();
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    // Dialog or modal should appear
    const dialog = page.locator('[role="dialog"], .fixed.inset-0');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Close dialog
    const closeBtn = page.locator("button").filter({ hasText: /关闭|取消/i }).first();
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    }
  });
});
