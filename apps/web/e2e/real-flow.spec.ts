import { test, expect } from "@playwright/test";

const API_URL = process.env.API_URL || "http://localhost:8000";
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";
const DEMO_EMAIL = "hr@acme-demo.com";
const DEMO_PASSWORD = "demo123456";

test.describe("real backend reachability (no mock)", () => {
  test("API health endpoint", async ({ request }) => {
    const r = await request.get(`${API_URL}/health`);
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.status).toBe("ok");
  });

  test("API login returns real JWT", async ({ request }) => {
    const r = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.access_token).toBeTruthy();
    expect(body.access_token.length).toBeGreaterThan(100);
  });

  test("auth me returns demo user", async ({ request }) => {
    const login = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    });
    const { access_token } = await login.json();
    const r = await request.get(`${API_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.email).toBe(DEMO_EMAIL);
  });

  test("legal status reflects not-yet-accepted", async ({ request }) => {
    const login = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    });
    const { access_token } = await login.json();
    const r = await request.get(`${API_URL}/api/v1/legal/status`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.data).toBeTruthy();
  });
});

test.describe("marketing pages (no auth)", () => {
  test("login page renders", async ({ page }) => {
    await page.goto(`${WEB_URL}/login`);
    await expect(page).toHaveTitle(/登录/);
  });

  test("help page renders", async ({ page }) => {
    await page.goto(`${WEB_URL}/help`);
    await expect(page.locator("h1").first()).toBeVisible();
    const html = await page.content();
    expect(html).toContain("帮助中心");
  });

  test("cases list renders 3 demo cases", async ({ page }) => {
    await page.goto(`${WEB_URL}/cases`);
    await expect(page.locator("h1").first()).toBeVisible();
    const html = await page.content();
    expect(html).toContain("客户案例");
    const article_count = await page.locator("article").count();
    expect(article_count).toBeGreaterThanOrEqual(3);
  });

  test("integrations page lists 4 platforms", async ({ page }) => {
    await page.goto(`${WEB_URL}/integrations`);
    await expect(page.locator("h1").first()).toBeVisible();
    const html = await page.content();
    expect(html).toContain("集成指南");
    const articles = await page.locator("article").count();
    expect(articles).toBeGreaterThanOrEqual(4);
  });
});

test.describe("dashboard redirect when no auth", () => {
  test("agent → /login redirect", async ({ page }) => {
    const r = await page.goto(`${WEB_URL}/agent`);
    expect(page.url()).toContain("/login");
    expect(r?.status()).toBe(200);
  });

  test("legal → /login redirect", async ({ page }) => {
    await page.goto(`${WEB_URL}/legal`);
    expect(page.url()).toContain("/login");
  });

  test("support → /login redirect", async ({ page }) => {
    await page.goto(`${WEB_URL}/support`);
    expect(page.url()).toContain("/login");
  });
});
