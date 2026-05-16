import { defineConfig } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://localhost:5899";
const isRemoteTarget = !!process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["html", { open: "on-failure" }], ["list"]],
  outputDir: "./test-results",

  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
  },

  ...(isRemoteTarget
    ? {}
    : {
        webServer: [
          {
            command: "cd ../agent && python api_server.py --port 8899",
            port: 8899,
            reuseExistingServer: true,
            timeout: 30_000,
          },
          {
            command: "cd ../frontend && npm run dev",
            port: 5899,
            reuseExistingServer: true,
            timeout: 30_000,
          },
        ],
      }),

  projects: [
    {
      name: "setup",
      testMatch: /global-setup\.ts/,
    },
    {
      name: "smoke",
      testMatch: /smoke\.spec\.ts/,
      dependencies: ["setup"],
    },
    {
      name: "chromium",
      testIgnore: /smoke\.spec\.ts/,
      dependencies: ["setup"],
      use: { browserName: "chromium" },
    },
  ],
});
