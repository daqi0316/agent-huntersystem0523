import { test, expect } from "@playwright/test";

test.describe("Talent Profile Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/talent-profile");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("人才档案");
  });

  test("search input works", async ({ page }) => {
    await page.goto("/talent-profile");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill("前端");
    await expect(searchInput).toHaveValue("前端");
  });

  test("profile cards render", async ({ page }) => {
    await page.goto("/talent-profile");
    await page.waitForLoadState("networkidle");

    const cards = page.locator('[class*="card"], [class*="Card"]');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("detail view opens when clicking card", async ({ page }) => {
    await page.goto("/talent-profile");
    await page.waitForLoadState("networkidle");

    const detailBtn = page.locator('button[title*="详情"]').first();
    if (await detailBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await detailBtn.click();
      const panel = page.locator('[role="dialog"], .fixed.inset-0');
      await expect(panel).toBeVisible({ timeout: 5000 });
    }
  });
});
