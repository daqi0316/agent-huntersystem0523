/**
 * P2-1 移动端响应式 E2E 验证 — apps/web/scripts/verify-mobile.ts
 *
 * 测：
 *  - 375x667 (iPhone SE) viewport 下 chip 可见
 *  - chip 触摸面积 >= 44px (Apple HIG)
 *  - 点击 chip 抽屉以 bottom sheet 形式展开 (not right panel)
 *  - 抽屉在 mobile 高度为 80vh (max-md:h-[80vh])
 *  - Esc 关闭
 *  - ⌘K 提示在 mobile 隐藏
 *
 * 用法：cd apps/web && npx tsx scripts/verify-mobile.ts
 */

import { chromium, devices } from "@playwright/test";

import { getE2eToken } from "./lib/auth";
const WEB_BASE = "http://localhost:3007";
const API_BASE = "http://localhost:8000/api/v1";
interface CheckResult {
  name: string;
  pass: boolean;
  detail?: string;
}

async function main() {
  const token = await getE2eToken();
  const results: CheckResult[] = [];

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 375, height: 667 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });
  const page = await context.newPage();

  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
      const now = new Date().toISOString();
      const seed = {
        state: {
          dataCards: [
            {
              id: "mobile-card-1",
              type: "candidate_list",
              title: "Mobile 候选人",
              summary: "",
              payload: null,
              messageId: "msg_mobile-1",
              createdAt: now,
              isRead: false,
            },
          ],
          currentContext: {
            currentCandidateIds: [],
            currentJobIds: [],
            recentTopic: "Mobile test",
            lastToolUsed: undefined,
          },
        },
        version: 1,
      };
      localStorage.setItem("ai-recruitment-agent-store", JSON.stringify(seed));
      const origSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key === "ai-recruitment-agent-store") return;
        return origSetItem.call(this, key, value);
      };
    },
    { token }
  );

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { id: "m-user", email: "m@test.com", role: "hr" },
      }),
    });
  });

  await page.goto(`${WEB_BASE}/agent`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);

  // 1. viewport meta 存在
  const viewportMeta = await page
    .locator('meta[name="viewport"]')
    .first()
    .getAttribute("content");
  results.push({
    name: "viewport meta 存在 (width=device-width)",
    pass: !!viewportMeta && viewportMeta.includes("width=device-width"),
    detail: viewportMeta ?? "missing",
  });

  // 2. chip 可见 + 触摸面积 >= 44px
  const chip = page.locator('button[aria-label*="看板"]').first();
  const chipVisible = await chip.isVisible();
  const chipBox = await chip.boundingBox();
  const touchOk = chipBox !== null && chipBox.height >= 44;
  results.push({
    name: "chip 可见 (375px viewport)",
    pass: chipVisible,
  });
  results.push({
    name: "chip 触摸面积 >= 44px (Apple HIG)",
    pass: touchOk,
    detail: chipBox ? `h=${chipBox.height}px` : "no box",
  });

  // 3. 点击 chip → 抽屉以 bottom sheet 展开
  await chip.click();
  await page.waitForTimeout(800);

  const drawer = page.locator('[role="dialog"]').first();
  const drawerBox = await drawer.boundingBox();
  const isBottomSheet =
    drawerBox !== null &&
    drawerBox.y > 100 &&
    drawerBox.height >= 400;
  results.push({
    name: "抽屉在 mobile 呈 bottom sheet (top > 100, h >= 400)",
    pass: isBottomSheet,
    detail: drawerBox
      ? `y=${drawerBox.y} h=${drawerBox.height} w=${drawerBox.width}`
      : "no box",
  });

  // 4. 抽屉宽度 = 100% viewport (375px)
  const fullWidth = drawerBox !== null && drawerBox.width >= 360;
  results.push({
    name: "抽屉宽度 = viewport (>= 360px)",
    pass: fullWidth,
    detail: `w=${drawerBox?.width ?? 0}px`,
  });

  // 5. ⌘K 提示在 mobile 隐藏
  const cmdKVisible = await page
    .locator("text=/快捷键：⌘K/")
    .first()
    .isVisible()
    .catch(() => false);
  results.push({
    name: "⌘K 提示在 mobile 隐藏 (md:inline 不命中)",
    pass: !cmdKVisible,
  });

  // 6. X 关闭按钮在 mobile 可见可点
  const closeBtnVisible = await page
    .locator('button[aria-label="关闭抽屉"]')
    .first()
    .isVisible();
  results.push({
    name: "X 关闭按钮在 mobile 可见 (用户主关闭路径)",
    pass: closeBtnVisible,
  });

  // 7. dataCard 在 mobile 可见
  const cardVisible = await page
    .locator("text=Mobile 候选人")
    .first()
    .isVisible()
    .catch(() => false);
  results.push({
    name: "dataCard 在 mobile 渲染",
    pass: cardVisible,
  });

  // 8. Esc 关闭 (看 aria-hidden=true 表示关闭)
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
  const ariaHiddenAfterEsc = await drawer.getAttribute("aria-hidden");
  results.push({
    name: "Esc 关闭抽屉 (aria-hidden=true)",
    pass: ariaHiddenAfterEsc === "true",
    detail: `aria-hidden=${ariaHiddenAfterEsc}`,
  });

  await browser.close();

  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;
  console.log("\n=== P2-1 Mobile Responsive 验证 (375x667 iPhone SE) ===");
  for (const r of results) {
    console.log(`  ${r.pass ? "✅" : "❌"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`);
  }
  console.log(`\n=== ${passed}/${results.length} passed ===`);

  if (failed > 0) process.exit(1);
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
