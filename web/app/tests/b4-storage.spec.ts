// B4: the storage fallback for browsers without createWritable (older Safari) keeps the data across a reload.
// Forced with ?storage=snapshot so it runs in any Chromium.
import { expect, test } from "@playwright/test";

test("snapshot storage fallback keeps the demo and a review across a reload", async ({ page }) => {
  await page.goto("/?storage=snapshot#/overview");
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
  await page.getByRole("button", { name: "Încarcă date demo (sintetice)" }).click();
  await expect(page.getByTestId("kpi-flags").locator(".kpi-value")).toHaveText("37", { timeout: 120_000 });
  const id = await page.evaluate(async () => {
    const e = (window as any).__engine;
    const flags = await e.call("flags");
    await e.call("set_feedback", { flag_id: flags[0].flag_id, status: "dismissed", note: "" });
    return flags[0].flag_id as string;
  });
  await page.reload();
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
  await expect(page.getByTestId("kpi-flags").locator(".kpi-value")).toHaveText("36");
  await expect(page.locator(".callout.warn")).toHaveCount(0);   // persistent: no warning
  const status = await page.evaluate(async (fid) => {
    const flags = await (window as any).__engine.call("flags", { include_dismissed: true });
    return flags.find((f: { flag_id: string }) => f.flag_id === fid).status;
  }, id);
  expect(status).toBe("dismissed");
});
