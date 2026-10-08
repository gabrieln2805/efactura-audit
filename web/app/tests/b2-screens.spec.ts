// B2: Overview, Flags, Invoices and Suppliers show the same numbers as the Streamlit app on the demo data.
// One page for the whole file: the engine starts once.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const expected = JSON.parse(readFileSync(new URL("./fixtures/demo_expect.json", import.meta.url), "utf-8"));
test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await page.goto("/");
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
  await page.getByRole("button", { name: "Încarcă date demo (sintetice)" }).click();
  await expect(page.getByTestId("kpi-flags")).toContainText(expected.kpi.flags, { timeout: 120_000 });
});

test.afterAll(async () => page.close());

test("overview: KPIs, both charts and the top 10 flags", async () => {
  for (const [key, value] of Object.entries(expected.kpi)) {
    await expect(page.getByTestId(`kpi-${key}`).locator(".kpi-value")).toHaveText(value as string);
  }
  await expect(page.getByTestId("chart-by-check").locator(".main-svg").first()).toBeVisible();
  await expect(page.getByTestId("chart-monthly").locator(".main-svg").first()).toBeVisible();
  await expect(page.getByTestId("top-flags").locator("tbody tr")).toHaveCount(10);
});

test("flags: filters, detail and review", async () => {
  await page.goto("/#/flags");
  await expect(page.getByTestId("flags-caption")).toHaveText(expected.flags_caption);
  await page.getByRole("button", { name: "Toate" }).first().click();
  await page.getByRole("option", { name: "Creștere de preț" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("flags-caption")).toHaveText(expected.price_caption);

  await page.getByTestId("flags-table").locator("tbody tr").first().click();
  const detail = page.getByTestId("flag-detail");
  await expect(detail.getByTestId("price-history").locator(".main-svg").first()).toBeVisible();
  await detail.getByRole("button", { name: /^HVO-|^[A-Z]{2,4}-/ }).first().click();
  await expect(detail.locator(".disclosure-body table").first()).toBeVisible();

  // dismiss with a note: it leaves the open list, comes back with "show dismissed", then reopen
  const flagId = (await detail.locator(".mono").first().textContent())!.split(" · ")[0];
  await detail.getByRole("radio", { name: "Respinsă" }).click();
  await detail.getByLabel("Notă").fill("test");
  await detail.getByRole("button", { name: "Salvează" }).click();
  await expect(page.getByText("Salvat.")).toBeVisible();
  const n = Number(expected.price_caption.split(" ")[0]);
  await expect(page.getByTestId("flags-caption")).toHaveText(new RegExp(`^${n - 1} rezultate`));
  await page.getByText("Arată și semnalările respinse").click();
  await expect(page.getByTestId("flags-caption")).toHaveText(expected.price_caption);
  const back = await page.evaluate((id) => (window as any).__engine.call("set_feedback", { flag_id: id, status: "open", note: "" }), flagId);
  expect(back).toMatchObject({ status: "open" });
});

test("invoices: search and detail", async () => {
  await page.goto("/#/invoices");
  await expect(page.getByTestId("invoices-caption")).toHaveText(expected.invoices_caption);
  await expect(page.getByTestId("invoices-table").locator("tbody tr")).toHaveCount(100);
  await page.getByLabel("Furnizor").fill("Betonex");
  await expect(page.getByTestId("invoices-caption")).toHaveText(expected.betonex_caption);
  await page.getByTestId("invoices-table").locator("tbody tr").first().click();
  await expect(page.getByTestId("invoice-detail").locator("tbody tr").first()).toBeVisible();
});

test("suppliers: table and detail", async () => {
  await page.goto("/#/suppliers");
  const rows = page.getByTestId("suppliers-table").locator("tbody tr");
  await expect(rows).toHaveCount(expected.suppliers);
  await expect(rows.first()).toContainText(expected.top_supplier);
  await rows.first().click();
  const detail = page.getByTestId("supplier-detail");
  await expect(detail).toContainText("CUI");
  await expect(detail.getByTestId("supplier-monthly").locator(".main-svg").first()).toBeVisible();
});

test("language switch re-renders in English", async () => {
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Suppliers");
  await page.getByRole("button", { name: "RO" }).click();
});
