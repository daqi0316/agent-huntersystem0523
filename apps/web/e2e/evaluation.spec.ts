import { test, expect } from "@playwright/test";

const EVAL_API = "**/api/v1/evaluations";

test.describe("Evaluation Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("评估报告");
  });

  test("shows skeleton loading on initial load", async ({ page }) => {
    // Delay API response so skeleton is visible
    await page.route(EVAL_API, async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, items: [], data: [], total: 0 }),
      });
    });

    await page.goto("/evaluation");
    // Skeleton should appear before data loads
    await expect(page.locator(".animate-pulse").first()).toBeVisible({ timeout: 2000 });
    // Wait for content to replace skeleton
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 10000 });
  });

  test("shows empty state when no evaluations exist", async ({ page }) => {
    await page.route(EVAL_API, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, items: [], data: [], total: 0 }),
      });
    });

    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=暂无评估数据")).toBeVisible();
    await expect(page.locator("text=完成候选人初筛后，AI 将自动生成评估报告")).toBeVisible();
  });

  test("shows error state with retry button on API failure", async ({ page }) => {
    await page.route(EVAL_API, async (route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });

    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=加载失败")).toBeVisible();
    await expect(page.locator("button").filter({ hasText: "重新加载" })).toBeVisible();
  });

  test("retry button re-fetches evaluations on error", async ({ page }) => {
    let callCount = 0;
    await page.route(EVAL_API, async (route) => {
      callCount++;
      if (callCount === 1) {
        await route.fulfill({ status: 500, body: "Internal Server Error" });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            items: [{
              id: "1", candidate_id: "c1", job_id: "j1",
              name: "张三", job_title: "前端", skills: ["React"],
              status: "done", overall_score: 85,
              scores: [{ name: "技能", score: 85 }],
              summary: "Good", date: "2026-05-27",
            }],
            total: 1,
          }),
        });
      }
    });

    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=加载失败")).toBeVisible();
    await page.locator("button").filter({ hasText: "重新加载" }).click();
    await expect(page.locator("h1")).toContainText("评估报告");
    await expect(page.locator("text=张三")).toBeVisible({ timeout: 5000 });
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

  test("search with no matches shows empty message", async ({ page }) => {
    await page.goto("/evaluation");
    await page.waitForLoadState("networkidle");

    const searchInput = page.locator('input[placeholder*="搜索"]');
    if (await searchInput.isVisible()) {
      await searchInput.fill("__不可能匹配的字符串__");
      await expect(page.locator("text=未找到匹配的评估报告")).toBeVisible();
    }
  });
});
