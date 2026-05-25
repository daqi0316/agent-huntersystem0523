import { test, expect } from "@playwright/test";

test.describe("AI Screening Page", () => {
  test("page renders with correct title", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("AI初筛");
  });

  test("page has tabs for different screening modes", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");

    const tabs = page.locator('[role="tablist"] button, [role="tab"]');
    const tabCount = await tabs.count();
    expect(tabCount).toBeGreaterThanOrEqual(2);

    const firstTabAttr = await tabs.first().getAttribute("data-state");
    expect(firstTabAttr === "active" || firstTabAttr === "true").toBeTruthy();
  });

  test("tab switching works", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");

    const tabs = page.locator('[role="tablist"] button, [role="tab"]');
    const tabCount = await tabs.count();

    if (tabCount >= 2) {
      for (let i = 1; i < tabCount; i++) {
        await tabs.nth(i).click();
        await page.waitForTimeout(200);
      }
    }
  });

  test("page has input fields", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");

    const inputs = page.locator("input, textarea");
    const count = await inputs.count();
    expect(count).toBeGreaterThanOrEqual(1);

    await inputs.first().fill("test-value");
    await expect(inputs.first()).toHaveValue("test-value");
  });
});
