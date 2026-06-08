import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
      testDir: "./e2e",
    },
    {
      name: "chromium",
      dependencies: ["setup"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
        baseURL: "http://127.0.0.1:3000",
      },
    },
    {
      name: "standalone",
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
        baseURL: "http://127.0.0.1:3000",
      },
    },
  ],
  webServer: {
    // B6 修: 改用 :3000 (现有 Next dev + next.config.js rewrite), 不启新 :3001
    // reuseExistingServer: true 让本地已有 :3000 Next dev 不被新启
    command: "node node_modules/next/dist/bin/next dev --port 3000",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 60 * 1000,
    cwd: ".",
  },
});
