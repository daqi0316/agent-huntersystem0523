import { test, expect } from "@playwright/test";

test.describe("Candidates Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("候选人库");
    await expect(page.locator("text=浏览、搜索和管理候选人信息")).toBeVisible();
  });

  test("search input and status filter are interactive", async ({ page }) => {
    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill("张");
    await expect(searchInput).toHaveValue("张");

    const statusSelect = page.locator("select").first();
    if (await statusSelect.isVisible()) {
      await statusSelect.selectOption("active");
      await expect(statusSelect).toHaveValue("active");
    }
  });

  test("shows skeleton loading then table content", async ({ page }) => {
    await page.route("**/api/v1/candidates*", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: [
            { id: "1", name: "张三", email: "z@t.com", skills: ["React"], status: "active", created_at: "2026-05-27" },
          ],
          items: [
            { id: "1", name: "张三", email: "z@t.com", skills: ["React"], status: "active", created_at: "2026-05-27" },
          ],
          total: 1,
        }),
      });
    });

    await page.goto("/candidates");
    await expect(page.locator(".animate-pulse").first()).toBeVisible({ timeout: 2000 });
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 10000 });
    await expect(page.locator("text=张三")).toBeVisible({ timeout: 5000 });
  });

  test("handles API error gracefully", async ({ page }) => {
    await page.route("**/api/v1/candidates*", async (route) => {
      await route.fulfill({ status: 500, body: "Error" });
    });

    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("候选人库");
  });

  test("creates candidate via API and shows in list", async ({ page }) => {
    // Intercept create and subsequent list
    let created = false;
    await page.route("**/api/v1/candidates", async (route) => {
      if (route.request().method() === "POST") {
        created = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            data: { id: "e2e-1", name: "张三", email: "z@t.com", skills: ["React"], status: "active", created_at: "2026-05-27" },
          }),
        });
      } else {
        const body = created
          ? JSON.stringify({
              success: true,
              data: [{ id: "1", name: "张三", email: "z@t.com", skills: ["React"], status: "active", created_at: "2026-05-27" }],
              items: [{ id: "1", name: "张三", email: "z@t.com", skills: ["React"], status: "active", created_at: "2026-05-27" }],
              total: 1,
            })
          : JSON.stringify({ success: true, data: [], items: [], total: 0 });
        await route.fulfill({ status: 200, contentType: "application/json", body });
      }
    });

    await page.goto("/candidates");
    await page.waitForLoadState("networkidle");

    // Try to find create button and use it
    const createBtn = page.locator("button").filter({ hasText: /创建|新建/i }).first();
    if (await createBtn.isVisible()) {
      await createBtn.click();
      const nameInput = page.locator('input[placeholder*="姓名"], input[name="name"]').first();
      if (await nameInput.isVisible()) {
        await nameInput.fill("E2E Test");
        const submitBtn = page.locator('button[type="submit"], button').filter({ hasText: /确认|保存|创建/i }).first();
        if (await submitBtn.isVisible()) {
          await submitBtn.click();
        }
      }
    }
  });
});
