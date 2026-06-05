/**
 * T4 候选人详情抽屉验证 — apps/web/scripts/verify-t4-detail.ts
 *
 * 测 T4 核心机制：ContextBar 抽屉内候选人 chip ➕ 按钮 → 展开详情卡片 → 渲染数据
 *  - 不依赖真实后端，mock /candidates/{id} 路由
 *  - 验证：
 *    1. ContextBar 渲染（缩略按钮可见）
 *    2. 打开抽屉
 *    3. 候选人 chip 旁 ➕ 按钮可见且 aria-expanded=false
 *    4. 点击 ➕ → 详情卡片 fetch 候选人 API
 *    5. 详情卡片显示 mock 数据（name / skills / 在助手中讨论按钮）
 *    6. aria-expanded=true
 *    7. 再次点击 ➕ → 收起
 *
 * 用法：cd apps/web && npx tsx scripts/verify-t4-detail.ts
 */

import { chromium } from "@playwright/test";

const WEB_BASE = "http://localhost:3000";
const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZDIwNDYyZi02ZGVjLTRiZTAtYTQ4Yi03NTk1YjNiZjJmZmIiLCJyb2xlIjoiaHIiLCJleHAiOjE3Nzk2MzU1OTF9.7G4XT2aBRGtCGF5N4M8sJwjkheahtbx9t89Z2N92L9E";

const CANDIDATE_ID = "f50bcfdc-b655-4c3b-b7fc-1737d9d2d1e5";
const CANDIDATE_NAME = "Bob";

interface CheckResult {
  name: string;
  pass: boolean;
  detail?: string;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(`PAGE ERROR: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      if (text.includes("agent/events") || text.includes("ERR_CONNECTION_REFUSED")) {
        return;
      }
      consoleErrors.push(`CONSOLE ERROR: ${text}`);
    }
  });

  await page.addInitScript(
    ({ token, candidateId }: { token: string; candidateId: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
      // 预填 zustand persist 的 currentContext
      // zustand init 时会读 localStorage，但 partialize 写 default state 会覆盖
      // 解决：先注入正确 state，再 mock setItem 阻止 zustand 写 default state
      const seedState = {
        state: {
          dataCards: [],
          currentContext: {
            currentCandidateIds: [candidateId],
            currentJobIds: [],
            recentTopic: "T4 e2e 测试上下文",
            lastToolUsed: "search_candidates",
          },
        },
        version: 1,
      };
      localStorage.setItem("ai-recruitment-agent-store", JSON.stringify(seedState));
      const origSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key === "ai-recruitment-agent-store") {
          // 阻止 zustand 用 default state 覆盖
          return;
        }
        return origSetItem.call(this, key, value);
      };
    },
    { token: TEST_TOKEN, candidateId: CANDIDATE_ID }
  );

  // mock /auth/me 避免 401
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { id: "t4-user", email: "t4@test.com", role: "hr" },
      }),
    });
  });

  // mock /candidates/{id} — playwright glob 模式不 work；改用真实后端候选人 ID
  // 移除 mock，直接用真实后端数据（候选人 Bob 已 seed 过）

  // 网络监控：捕获所有 candidate-related 响应
  page.on("response", (resp) => {
    const url = resp.url();
    if (url.includes("/candidates/") || url.includes("/agent/events")) {
      console.log(`  [net] ${resp.status()} ${url.replace(WEB_BASE, "")}`);
    }
  });

  const results: CheckResult[] = [];

  // 1. 加载 /agent（zustand init 时 setItem 被 mock 阻止，会读我们的 seed）
  await page.goto(`${WEB_BASE}/agent`);
  await page.waitForLoadState("networkidle").catch(() => {});
  // 等 zustand 初始化完成
  await page.waitForTimeout(1000);

  // Debug：dump 当前 zustand state
  const agentStoreState = await page.evaluate(() => {
    const raw = localStorage.getItem("ai-recruitment-agent-store");
    return raw ? JSON.parse(raw) : null;
  });
  console.log("  [debug] agentStore localStorage:", JSON.stringify(agentStoreState?.state?.currentContext));

  // 2. ContextBar 缩略按钮可见
  const chipVisible = await page
    .locator('button[aria-label*="看板" i], button[title*="数据看板" i], [class*="ContextChip"]')
    .first()
    .isVisible()
    .catch(() => false);
  results.push({ name: "ContextBar 缩略按钮可见", pass: chipVisible });

  // 3. 打开抽屉（点 ContextBar 缩略按钮）
  await page
    .locator('button[aria-label*="看板" i], button[title*="数据看板" i], [class*="ContextChip"]')
    .first()
    .click({ force: true })
    .catch(() => {});
  await page.waitForTimeout(1200);

  // Debug: 截屏
  await page.screenshot({ path: "/tmp/t4-debug.png", fullPage: true });

  // Debug: 列出所有可见 text
  const visibleTexts = await page
    .locator(":visible")
    .allTextContents()
    .catch(() => []);
  const candidateIdVisible = visibleTexts.some((t) => t.includes(CANDIDATE_ID));
  console.log(`  [debug] candidateId visible: ${candidateIdVisible}, total visible: ${visibleTexts.length}`);

  // 4. 候选人 chip 可见
  const chipLocatorCount = await page
    .locator(`text=${CANDIDATE_ID}`)
    .count();
  results.push({
    name: "候选人 chip 可见",
    pass: chipLocatorCount > 0,
    detail: `count=${chipLocatorCount}`,
  });

  // 5. ➕ 按钮存在 + aria-expanded=false
  const allButtons = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button[aria-label="展开详情"]')).map(
      (b) => ({
        aria: b.getAttribute("aria-expanded"),
        visible: b.getBoundingClientRect().width > 0,
      })
    );
  });
  results.push({
    name: "➕ 展开按钮存在",
    pass: allButtons.length > 0,
    detail: `count=${allButtons.length}`,
  });

  if (allButtons.length > 0) {
    results.push({
      name: "➕ 初始 aria-expanded=false",
      pass: allButtons[0].aria === "false",
      detail: `aria-expanded=${allButtons[0].aria}`,
    });

    // 6. 点击 ➕
    await page.evaluate(() => {
      const btn = document.querySelector('button[aria-label="展开详情"]') as HTMLButtonElement | null;
      btn?.click();
    });
    // 监听 candidate fetch
    const candidateFetch = page.waitForResponse(
      (r) => r.url().includes(`/candidates/${CANDIDATE_ID}`),
      { timeout: 5000 }
    ).catch(() => null);
    const fetchResp = await candidateFetch;
    if (fetchResp) {
      console.log(`  [net] candidate fetch: ${fetchResp.status()} ${fetchResp.url()}`);
    } else {
      console.log("  [net] candidate fetch: NO RESPONSE (timeout)");
      // Debug: 查看 page 实际 console 错误（详细）
      const allErrors = await page.evaluate(() => {
        return (window as unknown as { __errors: string[] }).__errors || [];
      });
      console.log(`  [debug] page errors: ${JSON.stringify(allErrors)}`);
    }
    await page.waitForTimeout(800);

    // 7. 详情卡片渲染（name 出现）
    const detailNameVisible = await page
      .locator(`text=${CANDIDATE_NAME}`)
      .nth(1)
      .isVisible()
      .catch(() => false);
    results.push({
      name: "详情卡片显示候选人 name",
      pass: detailNameVisible,
    });

    // 8. aria-expanded=true
    const afterAria = await page.evaluate(() => {
      const btn = document.querySelector('button[aria-label="展开详情"], button[aria-label="收起"]');
      return btn?.getAttribute("aria-expanded");
    });
    results.push({
      name: "点击后 aria-expanded=true",
      pass: afterAria === "true",
      detail: `aria-expanded=${afterAria}`,
    });

    // 9. "在助手中讨论" 按钮可见
    const discussBtnVisible = await page
      .locator("text=在助手中讨论")
      .first()
      .isVisible()
      .catch(() => false);
    results.push({ name: "在助手中讨论按钮可见", pass: discussBtnVisible });

    // 10. 邮箱 / 任一字段渲染（Bob 没 skills 字段，用 email 验证数据展示）
    const emailVisible = await page
      .locator("text=bob.0facc9@test.com")
      .first()
      .isVisible()
      .catch(() => false);
    results.push({ name: "详情显示候选人 email 字段", pass: emailVisible });

    // 11. 再次点击 ➕/收起 → 收起
    await page.evaluate(() => {
      const btn = document.querySelector(
        'button[aria-label="收起"]'
      ) as HTMLButtonElement | null;
      btn?.click();
    });
    await page.waitForTimeout(400);
    const finalAria = await page.evaluate(() => {
      const btn = document.querySelector('button[aria-label="展开详情"], button[aria-label="收起"]');
      return btn?.getAttribute("aria-expanded");
    });
    results.push({
      name: "再次点击 ➕ → aria-expanded=false（收起）",
      pass: finalAria === "false",
      detail: `aria-expanded=${finalAria}`,
    });
  }

  await browser.close();

  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;
  console.log("\n=== T4 候选人详情抽屉验证 ===");
  for (const r of results) {
    console.log(`  ${r.pass ? "✅" : "❌"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`);
  }
  if (consoleErrors.length > 0) {
    console.log("\n⚠️ Console errors:");
    for (const e of consoleErrors) console.log(`  - ${e}`);
  }
  console.log(`\n=== ${passed}/${results.length} passed ===`);

  if (failed > 0) process.exit(1);
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
