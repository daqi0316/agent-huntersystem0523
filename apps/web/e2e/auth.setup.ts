import { test as setup, expect } from "@playwright/test";
import { writeFileSync, mkdirSync, existsSync } from "fs";
import path from "path";

const API_BASE = process.env.API_URL || "http://localhost:8000/api/v1";
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
 */
setup("authenticate as test user", async ({ page }) => {
  // Try to register first
  let token: string | null = null;

  const registerRes = await page.request.post(`${API_BASE}/auth/register`, {
    data: TEST_USER,
  });

  if (registerRes.ok()) {
    const data = await registerRes.json();
    token = data.access_token;
  } else {
    // User may already exist — try login
    const loginRes = await page.request.post(`${API_BASE}/auth/login`, {
      data: { email: TEST_USER.email, password: TEST_USER.password },
    });
    expect(loginRes.ok()).toBeTruthy();
    const data = await loginRes.json();
    token = data.access_token;
  }

  expect(token).toBeTruthy();

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
