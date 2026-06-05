/**
 * E2E 真实登录 helper
 * ────────────────────────────────────────────────────────────
 * 为 verify-*.ts 脚本提供"调真后端拿 token"的能力, 替代历史
 * 写死的 fake JWT (那些 token 调真后端会 401, console 噪音)。
 *
 * 用法:
 *   import { getE2eToken } from "./lib/auth";
 *   const token = await getE2eToken();
 *
 * 行为:
 *   - 调 /auth/register, 已存在则 fall back 到 /auth/login
 *   - 最多 3 次重试 (后端启动 / 容器 race)
 *   - 用户复用 health-check 的 e2e-tester@test.com (单租户默认用户)
 *
 * P5-1 兼容: 返回的 token 含 current_org_id claim, 业务端点 RLS 可正常隔离。
 */

const API_BASE = process.env.API_BASE || "http://localhost:8000/api/v1";

const TEST_USER = {
  email: process.env.E2E_EMAIL || "e2e-tester@test.com",
  password: process.env.E2E_PASSWORD || "E2ePass123!",
  name: "E2E Tester",
};

interface AuthResponse {
  access_token?: string;
  token?: string;
}

async function tryRegister(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(TEST_USER),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = (await res.json()) as AuthResponse;
      return data.access_token || data.token || null;
    }
  } catch {
    /* fall through to login */
  }
  return null;
}

async function tryLogin(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: TEST_USER.email,
        password: TEST_USER.password,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = (await res.json()) as AuthResponse;
      return data.access_token || data.token || null;
    }
  } catch {
    /* swallow */
  }
  return null;
}

export async function getE2eToken(): Promise<string> {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const token = (await tryRegister()) || (await tryLogin());
    if (token) {
      if (attempt > 1) {
        console.log(`[auth] token 拿到 (重试 ${attempt - 1} 次)`);
      }
      return token;
    }
    if (attempt < 3) {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  throw new Error(
    `Failed to get E2E token from ${API_BASE} after 3 attempts (user: ${TEST_USER.email})`
  );
}
