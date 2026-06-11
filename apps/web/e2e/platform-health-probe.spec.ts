import { test, expect } from "@playwright/test";

const API_BASE = process.env.API_URL || "http://localhost:8000/api/v1";

test.describe("Platform Health Probe", () => {
  test("API /health endpoint returns ok", async ({ request }) => {
    const resp = await request.get(`${API_BASE.replace("/api/v1", "")}/health`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("status");
  });

  test("Sourcing health endpoint is reachable", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/sourcing/health`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("services");
    expect(body).toHaveProperty("status");
  });

  test("Sourcing health: database is ok", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/sourcing/health`);
    const body = await resp.json();
    expect(body.services?.database).toBe("ok");
  });

  test("Sourcing health: redis is ok", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/sourcing/health`);
    const body = await resp.json();
    expect(body.services?.redis).toBe("ok");
  });

  test("Sourcing health: queue counts are integers", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/sourcing/health`);
    const body = await resp.json();
    expect(body).toHaveProperty("queue");
    if (body.queue && typeof body.queue === "object") {
      if (body.queue.pending !== undefined) {
        expect(typeof body.queue.pending).toBe("number");
      }
      if (body.queue.running !== undefined) {
        expect(typeof body.queue.running).toBe("number");
      }
    }
  });

  test("Sourcing health: platform status is present", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/sourcing/health`);
    const body = await resp.json();
    expect(body).toHaveProperty("platforms");
    expect(typeof body.platforms?.total).toBe("number");
    expect(typeof body.platforms?.available).toBe("number");
  });

  test("Frontend login page loads correctly", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("body")).toBeVisible();
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });

  test("Frontend reports no console errors on login page", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    expect(consoleErrors.length).toBe(0);
  });
});
