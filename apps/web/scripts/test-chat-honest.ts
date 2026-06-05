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
    console.log("[1] /login");
    await page.goto(`${WEB_BASE}/login`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await page.locator('input[type="email"]').first().fill(TEST_EMAIL);
    await page.locator('input[type="password"]').first().fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 });
    console.log("    登录后:", page.url());

    console.log("[2] /agent");
    await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    const inputs = await page.locator("textarea, input[type='text']").all();
    console.log("[3] 找到输入框:", inputs.length);
    if (inputs.length === 0) {
      const html = await page.content();
      console.log("    找不到输入框。HTML 前 500:", html.substring(0, 500));
      return;
    }

    console.log("[4] 输入 '明天佛山天气怎么样'");
    await inputs[0].fill("明天佛山天气怎么样");
    await page.waitForTimeout(500);

    console.log("[5] 找发送按钮 + 点");
    const buttons = await page.locator("button").all();
    let clicked = false;
    for (const btn of buttons) {
      const text = (await btn.textContent()) || "";
      if (text.includes("发送") || text.includes("Send")) {
        console.log("    点按钮:", text.trim().substring(0, 30));
        await btn.click();
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      console.log("    没找到发送按钮，按 Enter");
      await inputs[0].press("Enter");
    }

    console.log("[6] 等 40s 等 AI 回复");
    await page.waitForTimeout(40000);

    const bodyText = await page.locator("body").innerText();
    console.log("\n=== AI 实际回复（页面后 1200 字符）===");
    console.log(bodyText.substring(Math.max(0, bodyText.length - 1200)));
    console.log("\n=== 关键检查 ===");
    console.log("  'Failed to fetch' 出现:", bodyText.includes("Failed to fetch"));
    console.log("  包含 '天气' 或 '佛':", bodyText.includes("天气") || bodyText.includes("佛"));
    console.log("  包含 '不可达' 或 '暂不可':", bodyText.includes("不可达") || bodyText.includes("暂不可"));
    console.log("  包含温度数字（'31'/'35'/'26'）:", /31|35|26|29/.test(bodyText));
  } catch (e) {
    console.error("ERR:", (e as Error).message);
  }
  console.log("\n=== console errors ===");
  consoleErrors.slice(0, 5).forEach((e) => console.log(" -", e));
  await browser.close();
}

main();
