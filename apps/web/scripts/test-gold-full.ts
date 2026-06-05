import { chromium } from "@playwright/test";
const WEB_BASE = "http://localhost:3007";
const TEST_EMAIL = "e2e-tester@test.com";
const TEST_PASSWORD = "E2ePass123!";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.goto(`${WEB_BASE}/login`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await page.locator('input[type="email"]').first().fill(TEST_EMAIL);
    await page.locator('input[type="password"]').first().fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 });
    await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    const inputs = await page.locator("textarea, input[type='text']").all();
    if (inputs.length === 0) { console.log("NO INPUT"); return; }
    await inputs[0].fill("昨天黄金价格是多少");
    await page.waitForTimeout(500);
    for (const btn of await page.locator("button").all()) {
      const t = (await btn.textContent()) || "";
      if (t.includes("发送") || t.includes("Send")) { await btn.click(); break; }
    }
    console.log("[等 40s 看 AI 回复]");
    await page.waitForTimeout(40000);
    const text = await page.locator("body").innerText();
    console.log("\n=== 页面最后 2000 字符 ===");
    console.log(text.substring(Math.max(0, text.length - 2000)));
  } catch (e) {
    console.error("ERR:", (e as Error).message);
  }
  await browser.close();
}
main();
