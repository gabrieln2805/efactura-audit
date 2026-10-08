// B4 performance budget, in a browser profile that keeps its cache between visits (like a real user's):
// a return visit has the engine ready in <= 10 s and the demo audit runs in <= 8 s.
import { chromium, expect, test, type Page } from "@playwright/test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

async function readySeconds(page: Page): Promise<number> {
  await page.goto("/#/overview");
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 240_000 });
  const st = await page.evaluate(() => (window as any).__engine.state as { seconds: number; stages: unknown });
  console.log("stages", JSON.stringify(st.stages));
  return st.seconds;
}

test("performance budget: return visit and demo audit", async ({ baseURL }, info) => {
  const dir = mkdtempSync(join(tmpdir(), "efa-perf-"));
  try {
    const ctx = await chromium.launchPersistentContext(dir, { channel: "msedge", baseURL });
    const page = ctx.pages()[0] ?? await ctx.newPage();
    const first = await readySeconds(page);
    const demo = await page.evaluate(() => (window as any).__engine.call("load_demo")) as { seconds: number };
    const audit = await page.evaluate(() => (window as any).__engine.call("run_audit")) as { seconds: number };
    await page.close();
    const again = await ctx.newPage();   // a new tab of the same browser: HTTP cache and OPFS kept
    const second = await readySeconds(again);
    await expect(again.getByTestId("kpi-flags").locator(".kpi-value")).toHaveText("37");
    await ctx.close();
    const timings = { first_visit_s: first, return_visit_s: second, demo_load_s: demo.seconds, audit_s: audit.seconds };
    console.log(JSON.stringify(timings));
    info.annotations.push({ type: "timings", description: JSON.stringify(timings) });
    expect(second).toBeLessThanOrEqual(10);
    expect(audit.seconds).toBeLessThanOrEqual(8);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
