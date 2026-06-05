import { chromium } from "@playwright/test";

const WEB_BASE = process.env.WEB_BASE || "http://localhost:3000";
const TEST_EMAIL = "e2e-tester@test.com";
const TEST_PASSWORD = "E2ePass123!";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const consoleErrors: string[] = [];
  const networkErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(`PAGE: ${err.message.substring(0, 200)}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(`CONSOLE: ${msg.text().substring(0, 200)}`);
  });
  page.on("response", (resp) => {
    if (resp.status() >= 400) networkErrors.push(`HTTP ${resp.status()} ${resp.url()}`);
  });

  try {
    console.log("[1] 打开 /login");
    await page.goto(`${WEB_BASE}/login`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    console.log("[2] 填表登录");
    await page.locator('input[type="email"]').first().fill(TEST_EMAIL);
    await page.locator('input[type="password"]').first().fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 });
    console.log("    登录后 URL:", page.url());
    console.log("[3] 跳到 /agent");
    await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    console.log("[4] 找输入框");
    const inputs = await page.locator("textarea, input[type='text']").all();
    console.log("    输入框数:", inputs.length);
    if (inputs.length === 0) {
      const html = await page.content();
      console.log("    HTML 前 2000:", html.substring(0, 2000));
      return;
    }
    console.log("[5] 输入问题");
    await inputs[0].fill("明天佛山天气怎么样");
    await page.waitForTimeout(500);
    console.log("[6] 找发送按钮");
    const buttons = await page.locator("button").all();
    let clicked = false;
    for (const btn of buttons) {
      const text = (await btn.textContent()) || "";
      if (text.includes("发送") || text.includes("Send")) {
        console.log("    找到:", text.trim().substring(0, 30));
        await btn.click();
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      console.log("    没找到发送按钮，按 Enter");
      await inputs[0].press("Enter");
    }
    console.log("[7] 等 35s 看响应");
    await page.waitForTimeout(35000);
    const bodyText = await page.locator("body").innerText();
    console.log("    'Failed to fetch' 出现:", bodyText.includes("Failed to fetch"));
    console.log("    '天气' 出现:", bodyText.includes("天气"));
    console.log("    页面最后 800 字符:", bodyText.substring(Math.max(0, bodyText.length - 800)));
  } catch (e) {
    console.error("ERR:", (e as Error).message);
  }

  console.log("\n=== console errors ===");
  consoleErrors.slice(0, 10).forEach((e) => console.log(" -", e));
  console.log("\n=== network errors ===");
  networkErrors.slice(0, 15).forEach((e) => console.log(" -", e));
  await browser.close();
}

main();
