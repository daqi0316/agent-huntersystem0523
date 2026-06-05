import { chromium } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";

async function main() {
  const loginRes = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "e2e-tester@test.com", password: "E2ePass123!" }),
  });
  const loginData: any = await loginRes.json();
  console.log("login:", loginRes.status, "token:", loginData.access_token?.slice(0, 16));

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.addInitScript(
    (token: string) => localStorage.setItem("ai-recruitment-token", token),
    loginData.access_token
  );
  await page.goto("http://localhost:3007/agent");
  await page.waitForLoadState("networkidle");

  // Check existing messages have id + createdAt
  const ls = await page.evaluate(() => {
    const raw = localStorage.getItem("agent-chat-history");
    if (!raw) return { found: false, reason: "no key" };
    const msgs = JSON.parse(raw);
    return {
      found: true,
      count: msgs.length,
      allHaveId: msgs.every((m: any) => typeof m.id === "string" && m.id.length > 0),
      allHaveCreatedAt: msgs.every((m: any) => typeof m.createdAt === "string" && m.createdAt.length > 0),
      sample: msgs[0] ? { id: msgs[0].id, createdAt: msgs[0].createdAt } : null,
    };
  });
  console.log("initial localstorage:", JSON.stringify(ls, null, 2));

  // Send a message and verify new message has id
  const ta = page.locator("textarea");
  if ((await ta.count()) > 0) {
    await ta.fill("verify id field ext0");
    await ta.press("Enter");
    await page.waitForTimeout(3000);
  }

  const ls2 = await page.evaluate(() => {
    const raw = localStorage.getItem("agent-chat-history");
    if (!raw) return { found: false };
    const msgs = JSON.parse(raw);
    const last = msgs[msgs.length - 1];
    return {
      count: msgs.length,
      lastHasId: typeof last?.id === "string" && last.id.length > 0,
      lastHasCreatedAt: typeof last?.createdAt === "string",
      lastId: last?.id?.slice(0, 20),
    };
  });
  console.log("after message:", JSON.stringify(ls2, null, 2));

  await browser.close();
  const pass = ls.found && ls.allHaveId && ls.allHaveCreatedAt && ls2.lastHasId;
  console.log(`\n=== VERDICT: ${pass ? "PASS ✅" : "FAIL ❌"} ===`);
  process.exit(pass ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
