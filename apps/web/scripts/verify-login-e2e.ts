/**
 * 端到端真实登录验证
 * 区别于 verify-contextbar.ts：使用真实后端 /auth/login，**不 mock token**。
 *
 * 前置：必须先跑过 health-check.sh Step 3（POST /auth/login 能拿到 token）
 * 否则此脚本会失败。
 *
 * 用法：npx tsx apps/web/scripts/verify-login-e2e.ts
 */

import { chromium } from "@playwright/test";

const WEB_BASE = process.env.WEB_BASE || "http://localhost:3007";
const TEST_EMAIL = "e2e-tester@test.com";
const TEST_PASSWORD = "E2ePass123!";

async function prewarmLogin(): Promise<void> {
  const maxAttempts = 30;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${WEB_BASE}/login`, { method: "GET" });
      if (res.status === 200) {
        if (i > 0) console.log(`[prewarm] /login ready after ${i} retries`);
        return;
      }
    } catch {
      void 0;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`/login did not return 200 after ${maxAttempts}s prewarm`);
}

async function main() {
  console.log(`[prewarm] 等待 ${WEB_BASE}/login 稳定（dev server 编译就绪）...`);
  await prewarmLogin();

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(`PAGE ERROR: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const t = msg.text();
      if (t.includes("agent/events")) return;
      consoleErrors.push(`CONSOLE ERROR: ${t}`);
    }
  });
  page.on("response", (resp) => {
    const status = resp.status();
    if (status >= 400) {
      failedRequests.push(`HTTP ${status} ${resp.url()}`);
    }
  });

  try {
    // 1. 打开 /login（不注入任何 token）
    let navOk = false;
    for (let attempt = 0; attempt < 3; attempt++) {
      const resp = await page.goto(`${WEB_BASE}/login`, {
        waitUntil: "domcontentloaded",
      });
      if (resp && resp.status() === 200) {
        navOk = true;
        break;
      }
      console.log(`[retry] /login 返回 ${resp?.status()}, 第 ${attempt + 1} 次重试...`);
      await new Promise((r) => setTimeout(r, 1500));
    }
    if (!navOk) throw new Error("/login 连续 3 次未返回 200");
    await page.waitForTimeout(1000);

    // 2. 找表单字段（按 type=email / type=password 找）
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passInput = page.locator('input[type="password"], input[name="password"]').first();
    await emailInput.fill(TEST_EMAIL);
    await passInput.fill(TEST_PASSWORD);

    // 3. 提交表单（找 type=submit 按钮）
    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    // 4. 等待跳转
    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 10000 });

    const afterLoginUrl = page.url();
    const isDashboard = afterLoginUrl.includes("/dashboard") || afterLoginUrl.includes("/agent");
    if (!isDashboard) {
      throw new Error(`登录后未跳到 dashboard/agent：${afterLoginUrl}`);
    }

    // 5. 跳到 /agent 看 ContextBar
    await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    const chipVisible = await page
      .getByRole("button", { name: /数据看板/ })
      .isVisible()
      .catch(() => false);
    if (!chipVisible) {
      throw new Error("ContextBar 缩略按钮在 /agent 不可见");
    }

    // 6. ⌘K 打开抽屉
    const isMac = process.platform === "darwin";
    const modKey = isMac ? "Meta" : "Control";
    await page.keyboard.down(modKey);
    await page.keyboard.press("k");
    await page.keyboard.up(modKey);
    await page.waitForTimeout(500);

    const drawerAriaHidden = await page
      .locator('[role="dialog"]')
      .getAttribute("aria-hidden")
      .catch(() => null);
    if (drawerAriaHidden === "true" || drawerAriaHidden === null) {
      throw new Error(`抽屉未正确打开：aria-hidden=${drawerAriaHidden}`);
    }

    if (consoleErrors.length > 0) {
      throw new Error(`有 console error：${consoleErrors.slice(0, 3).join(" | ")}`);
    }

    console.log("\n=== 真实端到端登录验证通过 ===\n");
    console.log("  ✅ /login 渲染表单");
    console.log(`  ✅ 填表 + 提交 → 跳到 ${afterLoginUrl}`);
    console.log("  ✅ /agent 页面 ContextBar 缩略按钮可见");
    console.log("  ✅ ⌘K 打开抽屉");
    console.log("  ✅ 0 console error");
    await browser.close();
    process.exit(0);
  } catch (err) {
    console.error("\n❌ 真实端到端登录验证失败：", (err as Error).message);
    if (consoleErrors.length > 0) {
      console.error("   console errors:", consoleErrors.slice(0, 5));
    }
    if (failedRequests.length > 0) {
      console.error("   failed requests:");
      for (const r of failedRequests.slice(0, 10)) console.error(`     ${r}`);
    }
    await browser.close();
    process.exit(1);
  }
}

main();
