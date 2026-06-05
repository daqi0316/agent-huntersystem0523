import { chromium } from "@playwright/test";
const WEB_BASE = "http://localhost:3007";
const TEST_EMAIL = "e2e-tester@test.com";
const TEST_PASSWORD = "E2ePass123!";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
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
  console.log("等 40s");
  await page.waitForTimeout(40000);
  // 用 .last() 找最后一条消息
  const messages = await page.locator(".bg-muted, [class*='message'], [class*='chat-message']").all();
  console.log(`找到 ${messages.length} 条消息元素`);
  if (messages.length > 0) {
    const lastMsg = await messages[messages.length - 1].innerText();
    console.log("\n=== 最后一条消息 ===");
    console.log(lastMsg);
  }
  // 退而求其次：抓页面里所有"黄金"相关文本
  console.log("\n=== 页面里含'黄金'的所有片段 ===");
  const html = await page.content();
  const matches = html.match(/黄金[\s\S]{0,200}/g) || [];
  matches.slice(0, 5).forEach(m => console.log("--- " + m.replace(/<[^>]+>/g, "").substring(0, 250)));
  await browser.close();
}
main();
