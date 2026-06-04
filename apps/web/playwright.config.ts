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
      },
    },
    {
      name: "standalone",
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
        baseURL: "http://localhost:3001",
      },
    },
  ],
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --port 3001",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    timeout: 120 * 1000,
    cwd: ".",
  },
});
