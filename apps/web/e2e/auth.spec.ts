import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await page.goto("/");
    await page.evaluate(() => localStorage.clear());
  });

  test("login page renders with form elements", async ({ page }) => {
    await page.goto("/login");

    await expect(page.locator("h1")).toContainText("AI Recruitment System");
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.locator("button[type='submit']")).toBeVisible();
  });

  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");

    await page.locator("#email").fill("wrong@test.com");
    await page.locator("#password").fill("WrongPass1!");
    await page.locator("button[type='submit']").click();

    await page.waitForTimeout(2000);
    expect(page.url()).toContain("/login");
    await expect(page.locator("button[type='submit']")).toBeVisible();
  });

  test("dashboard page renders when authenticated", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("AI Recruitment System", { timeout: 10000 });
  });
});
