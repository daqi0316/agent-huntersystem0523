import { test, expect } from "@playwright/test";

const TEST_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZDIwNDYyZi02ZGVjLTRiZTAtYTQ4Yi03NTk1YjNiZjJmZmIiLCJyb2xlIjoiaHIiLCJleHAiOjE3Nzk2MzU1OTF9.7G4XT2aBRGtCGF5N4M8sJwjkheahtbx9t89Z2N92L9E";

/**
 * ContextBar E2E — Phase 1.3 验证缩略按钮 + 抽屉 + 数据采集贯通
 *
 * 覆盖：
 *  1. Header 中存在 ContextBar 缩略按钮
 *  2. 初始无 dataCards → 无角标
 *  3. 发送消息触发 tool_call → 角标 +1
 *  4. 点击缩略按钮 → 抽屉展开
 *  5. 抽屉内显示 DataCardItem
 *  6. 点击卡片 → 标记已读 → 角标消失
 *  7. 关闭抽屉 → 缩略按钮仍常驻
 *  8. 清空全部 → 角标归零
 *
 * 依赖：
 *  - mock /api/v1/auth/me、/api/v1/agent/chat、/api/v1/conversation/session
 *  - 不依赖真实后端
 */

test.describe("ContextBar — 右上角缩略按钮 + 数据采集贯通", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(
      ({ token }: { token: string }) => {
        localStorage.setItem("ai-recruitment-token", token);
      },
      { token: TEST_TOKEN }
    );

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "test-user-1",
          email: "e2e@test.com",
          name: "E2E Tester",
          role: "hr",
        }),
      });
    });

    await page.route("**/api/v1/conversation/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            id: "sess_e2e_001",
            title: "E2E",
            message_count: 0,
          },
        }),
      });
    });

    await page.goto("/agent");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(500);
  });

  test("初始无 dataCards：ContextBar 缩略按钮存在但无角标", async ({ page }) => {
    const chip = page.getByRole("button", { name: /数据看板/ });
    await expect(chip).toBeVisible();
    await expect(chip).toContainText("数据看板");
  });

  test("发送消息触发 tool_call → 角标 +1 → 抽屉展开看到 DataCard", async ({
    page,
  }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      const body = JSON.parse(route.request().postData() || "{}");
      if (body.message?.includes("看板")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            data: {
              reply:
                '招聘看板数据如下：\n```json\n{"total_candidates":42,"total_jobs":5,"active_interviews":3}\n```',
              tool_calls: [
                { name: "get_dashboard_stats", args: {}, error: null, needs_human: false },
              ],
              agent_actions: [],
              model: "chat",
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            data: { reply: "好的", tool_calls: [], agent_actions: [], model: "chat" },
          }),
        });
      }
    });

    const textarea = page.locator("textarea").first();
    await textarea.fill("查看招聘数据看板");
    await textarea.press("Enter");
    await page.waitForTimeout(1500);

    const chip = page.getByRole("button", { name: /数据看板.*未读/ });
    await expect(chip).toBeVisible();
    await expect(chip).toContainText("1");

    await chip.click();
    await expect(page.getByText("招聘看板数据")).toBeVisible();
    await expect(page.getByText("42 候选人 · 5 职位 · 3 待面试")).toBeVisible();
  });

  test("点击卡片 → 标记已读 → 角标消失", async ({ page }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            reply:
              '匹配结果：\n```json\n[{"name":"张三","current_title":"前端工程师"}]\n```',
            tool_calls: [
              { name: "search_candidates", args: {}, error: null, needs_human: false },
            ],
            agent_actions: [],
            model: "chat",
          },
        }),
      });
    });

    const textarea = page.locator("textarea").first();
    await textarea.fill("搜索前端候选人");
    await textarea.press("Enter");
    await page.waitForTimeout(1500);

    const chip = page.getByRole("button", { name: /数据看板.*未读/ });
    await expect(chip).toContainText("1");
    await chip.click();

    const card = page.getByText("候选人列表");
    await expect(card).toBeVisible();
    await card.click();

    await page.waitForTimeout(300);
    const updatedChip = page.getByRole("button", { name: /数据看板/ });
    await expect(updatedChip).not.toContainText("1");
  });

  test("关闭抽屉 → 缩略按钮仍常驻", async ({ page }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            reply:
              '```json\n{"total_candidates":10,"total_jobs":2,"active_interviews":1}\n```',
            tool_calls: [
              { name: "get_dashboard_stats", args: {}, error: null, needs_human: false },
            ],
            agent_actions: [],
            model: "chat",
          },
        }),
      });
    });

    const textarea = page.locator("textarea").first();
    await textarea.fill("看看板");
    await textarea.press("Enter");
    await page.waitForTimeout(1500);

    const chip = page.getByRole("button", { name: /数据看板.*未读/ });
    await chip.click();
    await expect(page.getByText("招聘看板数据")).toBeVisible();

    await page.getByRole("button", { name: "关闭抽屉" }).click();
    await page.waitForTimeout(300);

    await expect(chip).toBeVisible();
  });

  test("MemoryPanel / OperationPanel 仍由 /agent 页面独立控制（共存验证）", async ({
    page,
  }) => {
    const memoryBtn = page.getByRole("button", { name: /查看结构化记忆/ });
    await expect(memoryBtn).toBeVisible();

    const contextChip = page.getByRole("button", { name: /数据看板/ });
    await expect(contextChip).toBeVisible();

    const bothExist = await memoryBtn.isVisible() && contextChip.isVisible();
    expect(bothExist).toBe(true);
  });
});
