/**
 * Playwright configuration — E2E smoke tests (story-4-6).
 *
 * Runs against the deployed dev environment (https://app.choka.dev).
 * Test credentials are read from environment variables set as GitHub Actions
 * secrets — never hard-coded here.
 *
 * Usage (local):
 *   E2E_USERNAME=... E2E_PASSWORD=... pnpm e2e
 *
 * Usage (CI):
 *   Secrets E2E_USERNAME and E2E_PASSWORD must be set in the repository.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,

  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://app.choka.dev",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  reporter: process.env.CI ? "github" : "list",
});
