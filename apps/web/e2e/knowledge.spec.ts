import { test, expect } from "@playwright/test";

test.describe("Knowledge Base Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("知识库");
  });

  test("has tabs for different sections", async ({ page }) => {
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");

    const tabs = page.locator('[role="tablist"] button, [role="tab"]');
    const count = await tabs.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test("tab switching works", async ({ page }) => {
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");

    const tabs = page.locator('[role="tablist"] button, [role="tab"]');
    const count = await tabs.count();

    if (count >= 2) {
      // Click second tab
      await tabs.nth(1).click();
      await page.waitForTimeout(300);

      const activeTab = page.locator('[role="tab"][data-state="active"], [role="tab"].active');
      await expect(activeTab).toHaveCount(1);
    }
  });

  test("search input is present", async ({ page }) => {
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    await expect(searchInput.first()).toBeVisible();
  });
});
