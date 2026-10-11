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
    await expect(page.locator(".app-foot > span")).toHaveText("Semnalările sunt indicii de verificat, nu concluzii.");
  }
  await page.locator(".rail .brand").click();
  await expect(page.getByTestId("try-demo")).toBeVisible();
});

test("about, privacy and terms: linked from every page, in both languages; the site sets no cookies", async ({ page, context }) => {
  await page.goto("/");
  await page.locator(".landing-foot").getByRole("link", { name: "Confidențialitate" }).click();
  await expect(page.getByTestId("page-privacy")).toContainText("facturile dumneavoastră nu ajung la noi");
  await expect(page.getByTestId("page-privacy")).toContainText("Nu folosim cookie-uri");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Privacy");
  await page.getByRole("button", { name: "RO" }).click();
  await page.goto("/#/terms");
  await expect(page.getByTestId("page-terms")).toContainText("nu este un audit financiar");
  await page.goto("/#/about");
  await expect(page.getByTestId("page-about")).toContainText("gratuit și necomercial");
  await expect(page.getByTestId("feedback-link")).toHaveAttribute("href", /^mailto:contact@clarifact\.ro\?subject=Feedback/);

  await page.goto("/#/overview");   // the app footer carries the same links
  await expect(page.locator(".app-foot").getByRole("link", { name: "Termeni" })).toHaveAttribute("href", "#/terms");
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
  expect(await context.cookies()).toEqual([]);
});
