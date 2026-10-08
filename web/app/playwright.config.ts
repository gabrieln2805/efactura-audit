import { defineConfig } from "@playwright/test";

// `npm test` runs everything in the Edge installed on the PC. `npm run test:browsers` runs the engine and landing
// tests in Chrome, Firefox and WebKit (Safari's engine; `npx playwright install firefox webkit` once).
// The first run fetches Pyodide's packages (~50 MB), so timeouts are generous.
const crossBrowser = /b1-engine|b4-landing/;

export default defineConfig({
  testDir: "tests",
  timeout: 300_000,
  expect: { timeout: 120_000 },
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5180/", trace: "retain-on-failure" },
  projects: [
    { name: "edge", use: { channel: "msedge" } },
    { name: "chrome", use: { channel: "chrome" }, testMatch: crossBrowser },
    { name: "firefox", use: { browserName: "firefox" }, testMatch: crossBrowser },
    { name: "webkit", use: { browserName: "webkit" }, testMatch: crossBrowser },
  ],
  webServer: { command: "npx vite", url: "http://127.0.0.1:5180/", reuseExistingServer: true, timeout: 60_000 },
});
