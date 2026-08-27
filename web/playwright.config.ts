import { defineConfig, devices } from "@playwright/test";

// The Next.js dev server is started by Playwright (see `webServer`). Specs run
// fully offline: every backend call (`/research/stream`, `/health`, `/library`)
// is intercepted with page.route — see tests/e2e/mock-backend.ts.
const PORT = 3000;
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // Deterministic backend origin; specs intercept it, so nothing real is hit.
      NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
    },
  },
});
