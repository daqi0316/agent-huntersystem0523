import { test, expect } from "@playwright/test";

test.describe("Jobs Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("职位管理");
  });

  test("search input works", async ({ page }) => {
    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]').first();
    if (await searchInput.isVisible()) {
      await searchInput.fill("前端");
      await expect(searchInput).toHaveValue("前端");
    }
  });

  test("status filter is interactive", async ({ page }) => {
    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    const statusSelect = page.locator("select").first();
    if (await statusSelect.isVisible()) {
      await statusSelect.selectOption("active");
      await expect(statusSelect).toHaveValue("active");
    }
  });

  test("create job dialog opens", async ({ page }) => {
    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    const createBtn = page.locator("button").filter({ hasText: /新建|创建/i }).first();
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    await page.waitForSelector(".fixed.inset-0", { timeout: 5000 });

    // Fill form inside dialog
    const titleInput = page.locator('input').first();
    if (await titleInput.isVisible()) {
      await titleInput.fill("高级前端工程师");
    }

    // Close dialog
    const closeBtn = page.locator(".fixed button").filter({ hasText: /关闭|取消/i }).first();
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }

    await expect(page.locator("h1")).toContainText("职位管理");
  });
});
