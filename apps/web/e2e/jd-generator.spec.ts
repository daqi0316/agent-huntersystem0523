import { test, expect } from "@playwright/test";

test.describe("JD Generator Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/jd-generator");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("JD 生成器");
  });

  test("page has input fields", async ({ page }) => {
    await page.goto("/jd-generator");
    await page.waitForLoadState("networkidle");

    const inputs = page.locator("input, textarea");
    await expect(inputs.first()).toBeVisible();
  });

  test("form fields accept input", async ({ page }) => {
    await page.goto("/jd-generator");
    await page.waitForLoadState("networkidle");

    const firstInput = page.locator("input").first();
    if (await firstInput.isVisible()) {
      await firstInput.fill("高级前端工程师");
      await expect(firstInput).toHaveValue("高级前端工程师");
    }
  });

  test("page has interactive buttons", async ({ page }) => {
    await page.goto("/jd-generator");
    await page.waitForLoadState("networkidle");

    const buttons = page.locator("button");
    await expect(buttons.first()).toBeVisible();
  });
});
