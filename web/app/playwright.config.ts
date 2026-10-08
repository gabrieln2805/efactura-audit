import { defineConfig } from "@playwright/test";

// Runs in the Edge that is installed on the PC (no browser download). The first run fetches Pyodide's
// packages (~50 MB), so timeouts are generous.
export default defineConfig({
  testDir: "tests",
  timeout: 240_000,
  expect: { timeout: 120_000 },
  workers: 1,
  reporter: "list",
  use: { channel: "msedge", baseURL: "http://127.0.0.1:5180/", trace: "retain-on-failure" },
  webServer: { command: "npx vite", url: "http://127.0.0.1:5180/", reuseExistingServer: true, timeout: 60_000 },
});
