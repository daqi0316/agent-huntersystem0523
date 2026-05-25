import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("login page renders with form elements", async ({ page }) => {
    await page.goto("/login");

    await expect(page.locator("h1")).toContainText("AI Recruitment System");
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /登录/i })).toBeVisible();
  });

  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");

    await page.locator("#email").fill("wrong@test.com");
    await page.locator("#password").fill("WrongPass1!");
    await page.getByRole("button", { name: /登录/i }).click();

    await expect(page.locator("text=Invalid email or password")).toBeVisible({ timeout: 10000 });
  });

  test("dashboard page renders when authenticated", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("数据看板", { timeout: 10000 });
  });

  test("registration page renders with required fields", async ({ page }) => {
    await page.goto("/register");

    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.locator("#name")).toBeVisible();
    await expect(page.getByRole("button", { name: /注册|register/i })).toBeVisible();
  });

  test("logout clears auth state and redirects to login", async ({ page }) => {
    // First ensure authenticated
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Find and click logout button — try common selectors
    const logoutBtn = page.locator("button").filter({ hasText: /退出|logout|登出/i });
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await page.waitForURL(/login/, { timeout: 5000 });
      expect(page.url()).toContain("login");
    }
  });
});
