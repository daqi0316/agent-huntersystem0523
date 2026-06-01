import { test, expect } from "@playwright/test";

const TEST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZDIwNDYyZi02ZGVjLTRiZTAtYTQ4Yi03NTk1YjNiZjJmZmIiLCJyb2xlIjoiaHIiLCJleHAiOjE3Nzk2MzU1OTF9.7G4XT2aBRGtCGF5N4M8sJwjkheahtbx9t89Z2N92L9E";

test.describe("Agent Chat Operation Panel — human-in-the-loop fallback", () => {

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
    }, { token: TEST_TOKEN });

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "test-user-1", email: "e2e@test.com", name: "E2E Tester", role: "hr" }),
      });
    });

    await page.goto("/agent");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);
  });

  test("agent API error → operation panel auto-opens", async ({ page }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Agent service unavailable" }),
      });
    });

    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.fill("帮我创建候选人张三");
    await input.press("Enter");
    await page.waitForTimeout(1000);

    const panel = page.locator('[class*="fixed"][class*="right-0"]').filter({ has: page.locator("h2:has-text('手动操作')") });
    await expect(panel).toBeVisible({ timeout: 5000 });
  });

  test("agent returns tool_call with error → panel pre-fills operation type", async ({ page }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          reply: "创建候选人失败，请稍后重试",
          tool_calls: [
            { name: "create_candidate", args: { name: "张三", email: "zhangsan@example.com" }, error: "网络错误" },
          ],
          agent_actions: [],
        }),
      });
    });

    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.fill("创建候选人张三 zhangsan@example.com");
    await input.press("Enter");

    await page.waitForTimeout(1500);

    const panel = page.locator('[class*="fixed"][class*="right-0"]').filter({ has: page.locator("h2:has-text('手动操作')") });
    await expect(panel).toBeVisible({ timeout: 5000 });

    const createCandidateBtn = panel.locator('button:has-text("创建候选人")').first();
    await expect(createCandidateBtn).toBeVisible();
  });

  test("panel submit → success message appended to chat", async ({ page }) => {
    let capturedCandidatePayload: Record<string, unknown> | null = null;

    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          reply: "无法完成操作",
          tool_calls: [{ name: "create_candidate", args: { name: "李四", email: "lisi@example.com" }, error: "service error" }],
          agent_actions: [],
        }),
      });
    });

    await page.route("**/api/v1/candidates", async (route) => {
      if (route.request().method() === "POST") {
        capturedCandidatePayload = route.request().postDataJSON();
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data: { id: "cand_test_123" } }) });
        return;
      }
      await route.fulfill({ status: 404 });
    });

    await page.route("**/api/v1/operations", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true }) });
        return;
      }
      await route.fulfill({ status: 404 });
    });

    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.fill("创建候选人李四");
    await input.press("Enter");

    await page.waitForTimeout(1500);

    const panel = page.locator('[class*="fixed"][class*="right-0"]').filter({ has: page.locator("h2:has-text('手动操作')") });
    await expect(panel).toBeVisible({ timeout: 5000 });

    const emailField = panel.locator('input[name="email"]');
    await expect(emailField).toBeVisible({ timeout: 3000 });

    await emailField.evaluate((el: HTMLInputElement) => {
      const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      nativeSetter?.call(el, "lisi@example.com");
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const nameField = panel.locator('input[name="name"]');
    if ((await nameField.count()) > 0) {
      await nameField.evaluate((el: HTMLInputElement) => {
        const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        nativeSetter?.call(el, "李四");
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    const confirmBtn = panel.locator('button:has-text("确认")');
    await expect(confirmBtn).toBeEnabled({ timeout: 3000 });
    await confirmBtn.click();

    await page.waitForTimeout(2000);

    const chatMessages = page.locator('[class*="rounded-2xl"]');
    const lastMsg = chatMessages.last();
    await expect(lastMsg).toContainText(/成功|success/i);

    expect(capturedCandidatePayload).not.toBeNull();
    expect(capturedCandidatePayload).toHaveProperty("email", "lisi@example.com");
  });

  test("panel has all 11 operation type tabs", async ({ page }) => {
    await page.route("**/api/v1/agent/chat", async (route) => {
      await route.fulfill({ status: 500, body: JSON.stringify({ detail: "error" }) });
    });

    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.fill("test");
    await input.press("Enter");
    await page.waitForTimeout(1000);

    const panel = page.locator('[class*="fixed"][class*="right-0"]').filter({ has: page.locator("h2:has-text('手动操作')") });
    await expect(panel).toBeVisible({ timeout: 5000 });

    const expectedTabs = [
      "创建候选人",
      "更新候选人",
      "归档候选人",
      "取消面试",
      "创建职位",
      "更新职位",
      "关闭职位",
      "创建申请",
      "更新申请状态",
      "改期面试",
      "保存评估",
    ];

    for (const tab of expectedTabs) {
      const tabBtn = panel.locator(`button:has-text("${tab}")`).first();
      await expect(tabBtn).toBeVisible({ timeout: 3000 });
    }
  });
});

test.describe("Command Palette — V.6 E2E", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ token }: { token: string }) => {
      localStorage.setItem("ai-recruitment-token", token);
    }, { token: TEST_TOKEN });

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "test-user-1", email: "e2e@test.com", name: "E2E Tester", role: "hr" }),
      });
    });

    await page.goto("/agent");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(1500);
  });

  test("/ opens command palette", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    const searchInput = palette.locator('input[placeholder*="搜索命令"]');
    await expect(searchInput).toBeVisible();
  });

  test("command palette shows 4 categories", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    await expect(palette.locator("text=任务控制")).toBeVisible();
    await expect(palette.locator("text=对话管理")).toBeVisible();
    await expect(palette.locator("text=增删改查")).toBeVisible();
    await expect(palette.locator("text=系统操作")).toBeVisible();
  });

  test("keyboard navigation: arrow keys + enter selects command", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(palette).not.toBeVisible({ timeout: 2000 });
    await expect(input).toHaveValue(/^\/\w+ /);
  });

  test("typing filters commands", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    const searchInput = palette.locator('input[placeholder*="搜索命令"]');
    await searchInput.fill("restart");

    await expect(palette.locator("text=/restart")).toBeVisible();
  });

  test("escape closes palette without selecting", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    await page.keyboard.press("Escape");

    await expect(palette).not.toBeVisible({ timeout: 2000 });
    await expect(input).toHaveValue("");
  });

  test("clicking command inserts it into input and closes palette", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    const restartBtn = palette.locator("button", { hasText: "/restart" });
    await restartBtn.click();

    await expect(palette).not.toBeVisible({ timeout: 2000 });
    await expect(input).toHaveValue("/restart ");
  });

  test("footer shows keyboard hints and command count", async ({ page }) => {
    const input = page.getByRole("textbox", { name: /输入你的需求/ });
    await input.click();
    await input.press("/");

    const palette = page.locator('[class*="fixed"][class*="inset-0"][class*="z-\\[100\\]"]');
    await expect(palette).toBeVisible({ timeout: 3000 });

    await expect(palette.locator("text=导航")).toBeVisible();
    await expect(palette.locator("text=选择")).toBeVisible();
    await expect(palette.locator("text=关闭")).toBeVisible();
    await expect(palette.locator("text=31 个命令")).toBeVisible();
  });
});
