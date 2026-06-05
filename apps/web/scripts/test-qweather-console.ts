import { chromium } from "@playwright/test";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.goto("https://console.qweather.com/project/47TPARKENY/credential/CJWETFQNHE?lang=zh", { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(3000);
    const url = page.url();
    const title = await page.title();
    const text = await page.locator("body").innerText();
    console.log("实际 URL:", url);
    console.log("页面 title:", title);
    console.log("页面文本前 800:", text.substring(0, 800));
  } catch (e) {
    console.error("ERR:", (e as Error).message);
  }
  await browser.close();
}

main();
