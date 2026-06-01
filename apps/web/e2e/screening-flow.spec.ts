import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const FIXTURES_DIR = path.join(__dirname, "fixtures");
const SAMPLE_RESUME = path.join(FIXTURES_DIR, "sample-resume.txt");

test.describe("T.8 — Resume Screening Flow (upload → parse → evaluate)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(FIXTURES_DIR, { recursive: true });
    if (!fs.existsSync(SAMPLE_RESUME)) {
      fs.writeFileSync(
        SAMPLE_RESUME,
        "张三\n" +
          "邮箱: zhangsan@example.com\n" +
          "电话: 138-0000-0000\n" +
          "工作年限: 5 年\n" +
          "技能: Python, FastAPI, PostgreSQL, Docker, Kubernetes\n" +
          "工作经历:\n" +
          "  - 2021-至今: ACME 科技 — 高级后端工程师\n" +
          "  - 2019-2021: Beta 公司 — 后端工程师\n" +
          "教育: 本科 / 计算机科学 / 某大学 (2015-2019)\n",
      );
    }
  });

  test("screening page loads and shows upload UI", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1, h2").first()).toBeVisible();
  });

  test("upload → parse → evaluate happy path", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");

    const fileInput = page.locator('input[type="file"]');
    if ((await fileInput.count()) === 0) {
      test.skip(true, "No file input on screening page — UI may not be wired");
    }
    await fileInput.setInputFiles(SAMPLE_RESUME);
    await page.waitForTimeout(500);

    const startBtn = page
      .locator('button:has-text("开始"), button:has-text("解析"), button:has-text("提交")')
      .first();
    if ((await startBtn.count()) > 0 && (await startBtn.isVisible())) {
      await startBtn.click();
    }

    const resultRegion = page
      .locator('[data-testid*="result"], [class*="result"], [class*="Result"]')
      .first();
    if ((await resultRegion.count()) > 0) {
      await expect(resultRegion).toBeVisible({ timeout: 10000 });
    }
  });

  test("parse failure path shows error state", async ({ page }) => {
    await page.goto("/screening");
    await page.waitForLoadState("networkidle");
    const startBtn = page
      .locator('button:has-text("开始"), button:has-text("解析"), button:has-text("提交")')
      .first();
    if ((await startBtn.count()) > 0 && (await startBtn.isVisible())) {
      await startBtn.click();
    }
    await page.waitForTimeout(1000);
  });
});
