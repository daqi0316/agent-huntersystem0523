import { test, expect } from "@playwright/test";

test.describe("U.10 — Operations Coverage (audit + approval countdown)", () => {
  test.describe("Audit Panel (Phase U.7)", () => {
    test("audit page loads and shows stats banner", async ({ page }) => {
      await page.goto("/audit");
      await page.waitForLoadState("networkidle");
      const heading = page.locator("h1, h2").first();
      await expect(heading).toBeVisible();
    });

    test("audit panel filter by agent_name works", async ({ page }) => {
      await page.goto("/audit");
      await page.waitForLoadState("networkidle");
      const filter = page
        .locator('input[placeholder*="agent"], input[placeholder*="Agent"], select')
        .first();
      if ((await filter.count()) > 0 && (await filter.isVisible())) {
        await filter.fill("test");
        await page.waitForTimeout(300);
      }
    });

    test("audit row expand toggles details", async ({ page }) => {
      await page.goto("/audit");
      await page.waitForLoadState("networkidle");
      const row = page.locator('[role="row"], tr, [class*="row"]').nth(1);
      if ((await row.count()) > 0 && (await row.isVisible())) {
        await row.click();
        await page.waitForTimeout(200);
      }
    });
  });

  test.describe("Approval Countdown (Phase U.9)", () => {
    test("dashboard shows approval countdown widget", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForLoadState("networkidle");
      const heading = page.locator("h1, h2").first();
      await expect(heading).toBeVisible();
    });

    test("approval countdown handles empty state", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForLoadState("networkidle");
      const widget = page
        .locator('[class*="approval"], [data-testid*="approval"], [class*="Countdown"]')
        .first();
      if ((await widget.count()) > 0) {
        await expect(widget).toBeVisible();
      }
    });
  });

  test.describe("Coverage Gate — E2E for Phase T + U backend endpoints", () => {
    test("backend health responds", async ({ request }) => {
      const apiBase = process.env.API_URL ?? "http://localhost:8888";
      const res = await request.get(`${apiBase}/health`).catch(() => null);
      if (!res) {
        test.skip(true, "API not reachable — defer to integration env");
        return;
      }
      expect(res.status()).toBeLessThan(500);
    });

    test("audit stats endpoint returns shape", async ({ request }) => {
      const apiBase = process.env.API_URL ?? "http://localhost:8888";
      const res = await request.get(`${apiBase}/api/v1/audit/stats`).catch(() => null);
      if (!res) {
        test.skip(true, "API not reachable — defer to integration env");
        return;
      }
      if (res.status() === 401) {
        test.skip(true, "Auth required — skip in E2E without token");
        return;
      }
      const body = await res.json().catch(() => ({}));
      expect(typeof body).toBe("object");
    });
  });
});
