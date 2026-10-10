// B3: Import (with a deliberately inconsistent upload), Data, Report, Settings and the AI assistant.
// One page for the whole file: the engine starts once.
import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const BROKEN = fileURLToPath(new URL("./fixtures/broken_upload.zip", import.meta.url));
test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await page.goto("/#/import");
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
});

test.afterAll(async () => page.close());

test("import: an upload with two buyers imports and its data tests warn", async () => {
  await page.getByTestId("file-input").setInputFiles(BROKEN);
  await expect(page.getByText("1 fișiere alese", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Importă", exact: true }).click();
  await expect(page.getByTestId("import-result")).toContainText("4 imported", { timeout: 120_000 });
  await expect(page.getByText("assert_single_buyer")).toBeVisible();
  await expect(page.getByTestId("imports")).toContainText("broken_upload.zip");
  await page.getByRole("button", { name: "Jurnal import" }).click();
  await expect(page.getByTestId("import-log")).toContainText("4 imported");

  await page.goto("/#/data");
  await page.getByRole("tab", { name: "Teste date" }).click();
  await expect(page.getByTestId("tests-summary")).toContainText("1 avertismente");
  await page.getByTestId("failing-test").getByRole("button").first().click();
  await expect(page.getByTestId("failing-test").locator("tbody tr")).toHaveCount(2);
});

test("import: keep one company, remove an import, start fresh", async () => {
  await page.goto("/#/import");
  const buyers = page.getByTestId("buyers");
  await expect(buyers.locator("tbody tr")).toHaveCount(2);
  await buyers.locator("tr", { hasText: "Client SRL" }).filter({ hasNotText: "Alt" }).getByRole("button", { name: "Păstrează doar aceasta" }).click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Au rămas doar facturile pentru Client SRL.")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("buyers")).toHaveCount(0);
  await expect(page.getByTestId("imports").locator("tbody tr").first()).toContainText("3");   // invoices kept

  await page.getByTestId("imports").getByRole("button", { name: /Șterge/ }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Ștergeți acest import?");
  await page.getByRole("button", { name: "Renunță" }).click();   // cancel keeps everything
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByTestId("imports").getByRole("button", { name: /Șterge/ }).first().click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Import șters: 3 facturi.")).toBeVisible({ timeout: 120_000 });

  // start fresh: the import history goes too
  await page.getByTestId("file-input").setInputFiles(BROKEN);
  await page.getByRole("button", { name: "Importă", exact: true }).click();
  await expect(page.getByTestId("import-result")).toContainText("4 imported", { timeout: 120_000 });
  await page.getByTestId("reset").click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Toate datele au fost șterse.")).toBeVisible();
  await expect(page.getByTestId("imports")).toHaveCount(0);
  await page.goto("/#/overview");
  await expect(page.getByRole("button", { name: "Încarcă date demo (sintetice)" })).toBeVisible();
});

test("data: lineage, table browser, charts and SQL on the demo", async () => {
  await page.goto("/#/import");
  await page.getByRole("button", { name: "Încarcă date demo (sintetice)" }).click();
  await expect(page.getByText("Date demo încărcate și auditate.")).toBeVisible({ timeout: 120_000 });

  await page.goto("/#/data");
  await expect(page.getByTestId("lineage").locator("svg")).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("table-select").selectOption("dim_suppliers");
  await expect(page.getByTestId("table-detail").locator("h3")).toHaveText("dim_suppliers");
  await expect(page.getByTestId("preview").locator("tbody tr")).toHaveCount(22);

  await page.getByRole("tab", { name: "Grafice" }).click();
  for (const id of ["heatmap", "supplier-invoices", "item-prices"]) {
    await expect(page.getByTestId(id).locator(".main-svg").first()).toBeVisible();
  }

  await page.getByRole("tab", { name: "Teste date" }).click();
  await expect(page.getByTestId("tests-summary")).toContainText("35 trecute · 0 avertismente");

  await page.getByRole("tab", { name: "SQL" }).click();
  await page.getByTestId("sql-input").fill("SELECT COUNT(*) AS n FROM fct_flags");
  await page.getByRole("button", { name: "Rulează", exact: true }).click();
  await expect(page.getByTestId("sql-result").locator("tbody td")).toHaveText("37");
  await page.getByTestId("sql-input").fill("DELETE FROM flags");
  await page.getByRole("button", { name: "Rulează", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("SELECT");
});

test("report: Excel and PDF are built in the browser", async () => {
  await page.goto("/#/report");
  for (const kind of ["xlsx", "pdf"]) {
    await page.getByTestId(`build-${kind}`).click();
    await expect(page.getByTestId(`download-${kind}`)).toBeVisible({ timeout: 180_000 });
    const [file] = await Promise.all([page.waitForEvent("download"), page.getByTestId(`download-${kind}`).click()]);
    expect(file.suggestedFilename()).toBe(`audit-efactura-ro.${kind}`);
  }
});

// a mocked model: first asks for audit_overview, then answers from its result
function fakeModel(seen: (string | undefined)[], cors = {}) {
  return async (route: import("@playwright/test").Route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    const body = route.request().postDataJSON();
    seen.push(route.request().headers()["authorization"]);
    const toolDone = body.messages.some((m: { role: string }) => m.role === "tool");
    const message = toolDone
      ? { role: "assistant", content: "Sunt **964** de facturi în perioada analizată." }
      : { role: "assistant", content: "", tool_calls: [{ id: "c1", type: "function", function: { name: "audit_overview", arguments: "{}" } }] };
    return route.fulfill({ status: 200, headers: cors, contentType: "application/json", body: JSON.stringify({ choices: [{ message }] }) });
  };
}

async function hostedInfo(info: object) {
  await page.context().unroute("**/api/assistant/info");
  await page.context().route("**/api/assistant/info", (r) => r.fulfill({ json: info }));
  await page.goto("/#/assistant");
  await page.reload();   // the app reads the assistant server's info once per visit
  await expect(page.getByTestId("engine-chip")).toHaveAttribute("data-phase", "ready", { timeout: 200_000 });
}

test("assistant: users get the site's assistant, with no key in the browser (server mocked)", async () => {
  const seen: (string | undefined)[] = [];
  await page.context().route("**/api/assistant/chat/completions", fakeModel(seen));

  await hostedInfo({ available: false });
  await expect(page.getByTestId("ai-not-set-up")).toBeVisible();

  await hostedInfo({ available: true, model: "gpt-test", upstream: "api.openai.com", approved: false });
  await expect(page.getByTestId("hosted-untested")).toContainText("gpt-test");
  await expect(page.getByRole("button", { name: "Rulează testul acum" })).toBeEnabled();

  await hostedInfo({ available: true, model: "gpt-test", upstream: "api.openai.com", approved: true });
  await expect(page.getByTestId("provider")).toHaveCount(0);   // no provider or model pickers for users
  await expect(page.getByText("Fișierele facturilor nu se trimit")).toBeVisible();
  await page.getByTestId("chat-input").fill("Câte facturi sunt?");
  await page.getByTestId("chat-input").press("Enter");
  const log = page.getByTestId("chat-log");
  await expect(log.locator(".md strong")).toHaveText("964", { timeout: 60_000 });
  await log.getByRole("button", { name: /Surse: apeluri de instrumente \(1\)/ }).click();
  await expect(log).toContainText("audit_overview({})");
  expect(seen).toEqual([undefined, undefined]);   // the browser never sends a key; the server adds it
});

test("assistant: developer options still allow a cloud model with your own key (API mocked)", async () => {
  const seen: (string | undefined)[] = [];
  const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, OPTIONS" };
  await page.context().route("https://api.openai.com/v1/chat/completions", fakeModel(seen, cors));
  await page.goto("/#/settings");
  await page.getByText("Opțiuni pentru dezvoltare").click();
  await page.getByText("Permite modele cloud").click();
  await page.getByText("Arată și modele netestate").click();
  await page.goto("/#/assistant");
  await page.getByTestId("provider").selectOption("openai");
  await page.getByLabel("Cheie API proprie").fill("sk-test");
  await page.getByRole("button", { name: "Conversație nouă" }).click();
  await page.getByTestId("chat-input").fill("Câte facturi sunt?");
  await page.getByTestId("chat-input").press("Enter");
  await expect(page.getByTestId("chat-log").locator(".md strong")).toHaveText("964", { timeout: 60_000 });
  expect(seen).toEqual(["Bearer sk-test", "Bearer sk-test"]);
});

test("settings: the Ollama model test is disabled, with the reason, when Ollama is not running", async () => {
  const running = await page.evaluate(() => (window as any).__engine.call("ollama_status")) as { models: string[] };
  test.skip(running.models.length > 0, "Ollama is running on this machine");
  await page.goto("/#/settings");
  await expect(page.getByTestId("ai-status")).toContainText("gpt-test");
  await page.getByTestId("test-provider").selectOption("ollama");   // developer options are still on
  await expect(page.getByTestId("run-model-test")).toBeDisabled();
  await expect(page.getByText("Ollama nu rulează la http://localhost:11434")).toHaveCount(2);   // status line and the warning
});
