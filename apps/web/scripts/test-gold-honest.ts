import { chromium } from "@playwright/test";
const WEB_BASE = process.env.WEB_BASE || "http://localhost:3000";
const TEST_EMAIL = "e2e-tester@test.com";
const TEST_PASSWORD = "E2ePass123!";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const consoleErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(`PAGE: ${err.message.substring(0, 200)}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(`CONSOLE: ${msg.text().substring(0, 200)}`);
  });

  try {
    console.log("[1] 登录");
    await page.goto(`${WEB_BASE}/login`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await page.locator('input[type="email"]').first().fill(TEST_EMAIL);
    await page.locator('input[type="password"]').first().fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 });

    console.log("[2] /agent");
    await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const inputs = await page.locator("textarea, input[type='text']").all();
    if (inputs.length === 0) { console.log("找不到输入框"); return; }

    console.log("[3] 问'昨天黄金价格'");
    await inputs[0].fill("昨天黄金价格是多少");
    await page.waitForTimeout(500);

    const buttons = await page.locator("button").all();
    for (const btn of buttons) {
      const text = (await btn.textContent()) || "";
      if (text.includes("发送") || text.includes("Send")) {
        await btn.click();
        break;
      }
    }
    console.log("[4] 等 35s");
    await page.waitForTimeout(35000);

    const bodyText = await page.locator("body").innerText();
    console.log("\n=== 页面最后 1500 字符（AI 回复 + tool_calls）===");
    console.log(bodyText.substring(Math.max(0, bodyText.length - 1500)));
  } catch (e) {
    console.error("ERR:", (e as Error).message);
  }
  console.log("\n=== console errors（前 5）===");
  consoleErrors.slice(0, 5).forEach((e) => console.log(" -", e));
  await browser.close();
}

main();
