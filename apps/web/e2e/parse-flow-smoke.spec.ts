import { test, expect } from "@playwright/test";

test.describe("v1.1 Phase D smoke — frontend serves pages", () => {
  test("/login page renders (no auth required)", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(1000);
    await expect(page.locator("body")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
