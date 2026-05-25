import { test, expect } from "@playwright/test";

test.describe("Candidates Page", () => {
  test("page renders with correct title and table", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("候选人库");
    await expect(page.locator("text=浏览、搜索和管理候选人信息")).toBeVisible();
    await expect(page.locator("table")).toBeVisible({ timeout: 10000 });
  });

  test("search input and status filter are interactive", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill("张");
    await expect(searchInput).toHaveValue("张");

    const statusSelect = page.locator("select").first();
    await expect(statusSelect).toBeVisible();
    await statusSelect.selectOption("active");
    await expect(statusSelect).toHaveValue("active");
  });

  test("creates candidate via API and shows in list", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    const token = await page.evaluate(() => localStorage.getItem("ai-recruitment-token"));
    if (token) {
      const apiBase = process.env.API_URL || "http://localhost:8000/api/v1";
      await page.request.post(`${apiBase}/candidates`, {
        data: {
          name: "张三",
          email: "zhangsan-e2e@test.com",
          phone: "13800138001",
          skills: ["Python", "React", "PostgreSQL"],
          current_title: "高级工程师",
          current_company: "某科技公司",
          experience_years: 5,
        },
        headers: { Authorization: `Bearer ${token}` },
      });
    }

    await page.reload();
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("cell", { name: "张三" }).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("cell", { name: "高级工程师" }).first()).toBeVisible();
  });

  test("detail dialog opens on click", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    const detailBtn = page.locator('button[title*="详情"]').first();
    await expect(detailBtn).toBeVisible({ timeout: 10000 });
    await detailBtn.click();

    await page.locator("button:has-text('关闭')").waitFor({ state: "visible", timeout: 5000 });
    await page.locator("button:has-text('关闭')").click();
  });
});
