// B1: the engine runs in the browser, the demo gives the native engine's flags, and the data survives a reload.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

type Flag = { flag_id: string; check_name: string; rule: string; severity: string; score: number; amount_at_risk_ron: number | null };
const native: Flag[] = JSON.parse(readFileSync(new URL("./fixtures/demo_flags.json", import.meta.url), "utf-8"));

async function engineReady(page: Page) {
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
}

test("demo audit in the browser matches the native engine and is kept after a reload", async ({ page, context }) => {
  await page.goto("/#/overview");
  await engineReady(page);
  await page.getByRole("button", { name: "Încarcă date demo (sintetice)" }).click();
  await expect(page.getByTestId("kpi-flags")).toContainText(String(native.length), { timeout: 120_000 });

  const flags = await page.evaluate(() => (window as any).__engine.call("flags")) as Flag[];
  const byId = new Map(flags.map((f) => [f.flag_id, f]));
  expect([...byId.keys()].sort()).toEqual(native.map((f) => f.flag_id));
  for (const n of native) {
    const f = byId.get(n.flag_id)!;
    expect([f.check_name, f.rule, f.severity]).toEqual([n.check_name, n.rule, n.severity]);
    expect(f.score).toBeCloseTo(n.score, 9);
    expect(f.amount_at_risk_ron ?? 0).toBeCloseTo(n.amount_at_risk_ron ?? 0, 6);
  }

  // a second tab must not open its own copy of the database
  const other = await context.newPage();
  await other.goto("/#/overview");
  await expect(other.getByTestId("engine-chip")).toHaveAttribute("data-phase", "locked", { timeout: 200_000 });
  await other.close();

  // a browser without OPFS (Playwright's WebKit on Windows) must say the data is not kept, instead of losing it silently
  const persistent = await page.evaluate(() => (window as any).__engine.state.persistent as boolean);
  if (!persistent) {
    await expect(page.getByRole("status").filter({ hasText: "nu permite păstrarea datelor" })).toBeVisible();
    test.info().annotations.push({ type: "storage", description: "no OPFS in this browser: reload persistence not tested" });
    return;
  }

  await page.reload();
  await engineReady(page);
  await expect(page.getByTestId("kpi-flags")).toContainText(String(native.length));
  await expect(page.getByRole("button", { name: "Încarcă date demo (sintetice)" })).toHaveCount(0);
});
