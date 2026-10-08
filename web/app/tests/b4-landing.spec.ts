// B4: the landing page leads into the demo, and every app page carries the disclaimer.
import { expect, test } from "@playwright/test";

test("landing: 'try the demo' opens the app and loads the demo data", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("e-Factura");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByTestId("try-demo")).toHaveText("Try the demo");
  await page.getByRole("button", { name: "RO" }).click();
  await page.getByTestId("try-demo").click();
  await expect(page).toHaveURL(/#\/overview/);
  await expect(page.getByTestId("kpi-flags").locator(".kpi-value")).toHaveText("37", { timeout: 300_000 });
  await expect(page).not.toHaveURL(/demo/);
  for (const screen of ["overview", "flags", "data", "settings"]) {
    await page.goto(`/#/${screen}`);
    await expect(page.locator(".app-foot")).toHaveText("Semnalările sunt indicii de verificat, nu concluzii.");
  }
  await page.locator(".rail .brand").click();
  await expect(page.getByTestId("try-demo")).toBeVisible();
});
