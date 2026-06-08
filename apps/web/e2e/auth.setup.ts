import { test as setup, expect, request } from "@playwright/test";
import { writeFileSync, mkdirSync, existsSync } from "fs";
import path from "path";

const API_BASE = process.env.API_URL || "http://127.0.0.1:8000/api/v1";
console.log(`[B6 setup] API_BASE=${API_BASE} env.API_URL=${process.env.API_URL}`);
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
 * B6 完整修: 用 Node native fetch (Node 18+) 完全 bypass Playwright APIRequestContext.
 * 根因: Playwright setup project 注入 webServer URL (3001) 作 baseURL 到 request fixture,
 * 绝对 URL 在 ctx.post() 里被 baseURL 截断 (路径前缀 /api/v1 被吃).
 * Node fetch 用 process.env API_URL 直连 8000, 不依赖 Playwright runner 注入.
 */
setup("authenticate as test user", async ({ page }) => {
  let token: string | null = null;
  let lastError: unknown = null;

  // Try up to 3 times with short delay (handles boot-up race)
  for (let attempt = 0; attempt < 3 && !token; attempt++) {
    if (attempt > 0) await page.waitForTimeout(1000);
    try {
      // Try to register first (Node fetch 直连 8000, bypass Playwright)
      const registerRes = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(TEST_USER),
        signal: AbortSignal.timeout(5000),
      });
      console.log(`[B6 setup] attempt ${attempt} register status=${registerRes.status}`);
      if (registerRes.ok) {
        const data = await registerRes.json();
        token = data.access_token || data.token;
      }
    } catch (e) {
      console.log(`[B6 setup] attempt ${attempt} register EXC: ${e}`);
      lastError = e;
    }

    if (!token) {
      try {
        const loginRes = await fetch(`${API_BASE}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: TEST_USER.email, password: TEST_USER.password }),
          signal: AbortSignal.timeout(5000),
        });
        console.log(`[B6 setup] attempt ${attempt} login status=${loginRes.status}`);
        if (loginRes.ok) {
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
