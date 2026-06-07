import { test as setup, expect, request } from "@playwright/test";
import { writeFileSync, mkdirSync, existsSync } from "fs";
import path from "path";

const API_BASE = process.env.API_URL || "http://127.0.0.1:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";
const AUTH_FILE = path.resolve(".auth/user.json");

const TEST_USER = {
  email: "e2e-tester@test.com",
  password: "E2ePass123!",
  name: "E2E Tester",
};

/**
 * Register a test user via API and persist the auth state.
 * If registration fails (e.g., duplicate user), fall back to login.
 *
 * B6 修: 用独立 APIRequestContext (request fixture) 直连 8000, 不走 page baseURL.
 * 原版 page.request 走 :3000 (Next dev), 之前 404 (无 rewrite) 现在 200 (有 rewrite) 但仍
 * 不可靠 — fetch 直连 8000 是最稳路径.
 */
setup("authenticate as test user", async ({ page }) => {
  let token: string | null = null;
  let lastError: unknown = null;

  // 用独立 request context + 绝对 URL (避免 baseURL 解析问题)
  const ctx = await request.newContext();

  // Try up to 3 times with short delay (handles boot-up race)
  for (let attempt = 0; attempt < 3 && !token; attempt++) {
    if (attempt > 0) await page.waitForTimeout(1000);
    try {
      // Try to register first
      const registerRes = await ctx.post(`${API_BASE}/auth/register`, {
        data: TEST_USER,
        timeout: 5000,
      });
      console.log(`[B6 setup] attempt ${attempt} register status=${registerRes.status()}`);
      if (registerRes.ok()) {
        const data = await registerRes.json();
        token = data.access_token || data.token;
      }
    } catch (e) {
      console.log(`[B6 setup] attempt ${attempt} register EXC: ${e}`);
      lastError = e;
    }

    if (!token) {
      try {
        const loginRes = await ctx.post(`${API_BASE}/auth/login`, {
          data: { email: TEST_USER.email, password: TEST_USER.password },
          timeout: 5000,
        });
        console.log(`[B6 setup] attempt ${attempt} login status=${loginRes.status()}`);
        if (loginRes.ok()) {
          const data = await loginRes.json();
          token = data.access_token || data.token;
          console.log(`[B6 setup] attempt ${attempt} login token_len=${token?.length}`);
        }
      } catch (e) {
        console.log(`[B6 setup] attempt ${attempt} login EXC: ${e}`);
        lastError = e;
      }
    }
  }

  await ctx.dispose();
  expect(token, `Failed to authenticate after 3 attempts: ${lastError}`).toBeTruthy();

  // Set the token in localStorage so the app treats the user as authenticated
  await page.goto("/");
  await page.evaluate(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: TOKEN_KEY, value: token! }
  );

  // Persist storage state for reuse by other tests
  if (!existsSync(path.dirname(AUTH_FILE))) {
    mkdirSync(path.dirname(AUTH_FILE), { recursive: true });
  }
  await page.context().storageState({ path: AUTH_FILE });
});
