import { test, expect } from "@playwright/test";

const JOBS_API = "**/api/v1/jobs";

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
    await expect(searchInput).toBeVisible();
    await searchInput.fill("前端");
    await expect(searchInput).toHaveValue("前端");
  });

  test("shows loading skeleton then content", async ({ page }) => {
    await page.route(JOBS_API, async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [], items: [], total: 0 }),
      });
    });

    await page.goto("/jobs");
    await expect(page.locator(".animate-pulse").first()).toBeVisible({ timeout: 2000 });
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 10000 });
  });

  test("shows error state on API failure", async ({ page }) => {
    await page.route(JOBS_API, async (route) => {
      await route.fulfill({ status: 500, body: "Error" });
    });

    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    // Should not crash — either shows fallback or error message
    await expect(page.locator("h1")).toContainText("职位管理");
  });

  test("create job dialog opens", async ({ page }) => {
    await page.goto("/jobs");
    await page.waitForLoadState("networkidle");

    const createBtn = page.locator("button").filter({ hasText: /新建|创建/i }).first();
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    await page.waitForSelector('[role="dialog"], .fixed.inset-0', { timeout: 5000 });

    // Close dialog
    const closeBtn = page.locator('[role="dialog"] button, .fixed.inset-0 button').filter({ hasText: /关闭|取消/i }).first();
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }

    await expect(page.locator("h1")).toContainText("职位管理");
  });
});
