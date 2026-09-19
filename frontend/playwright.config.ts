import { defineConfig } from "@playwright/test";

/**
 * Browser smoke test against the REAL backend and a REAL processed dataset.
 * Uses the system-installed Microsoft Edge (channel) so no browser download
 * is required on the presentation machine.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:4173",
    channel: "msedge",
    headless: true,
  },
  webServer: [
    {
      command: "python -m uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run preview",
      cwd: ".",
      url: "http://localhost:4173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
