# STATUS: Clarifact (code name efactura-audit)

**Start every session here.** Update the "Now", "Next" and "Session log" sections at the end of each session.

Last updated: 11 Oct 2026 · Version 0.2.0 · Phase: **launch preparation (free beta)**

## Now

**Product:** Clarifact (clarifact.ro, not yet registered), a website that checks a company's supplier invoices
from e-Factura: near-duplicates, supplier price increases, unusual amounts, VAT patterns, supplier and bank
account changes. Invoices are processed and stored only in the user's browser. Free beta first, paid tier later.
The name avoids "e-Factura" (a state system) and "audit" (statutory financial audit is a regulated profession).
The Python package keeps its code name `efactura_audit`; the web app takes the name from `web/app/src/brand.ts`.

| Area | State |
|---|---|
| Checking engine (import, 5 checks, review, reports) | Done. 99–100 % recall on synthetic data (33/33 planted anomalies on the test-pack client); 9,895 invoices in 12 s natively |
| Web app (`web/app/`) | Built: landing page and 9 screens, RO/EN, light/dark, phone layout; engine in the browser (Pyodide), data in the browser (OPFS). Import history with undo, "keep one company", "start fresh". Runs locally only |
| Performance (Edge, Gabriel's PC) | First visit about 15 s (about 50 MB), return visit 6–8 s; demo check 3–4 s; 8,217 invoices imported and checked in 44 s |
| AI assistant | **Parked**, shown as "coming soon". Works behind Settings → Developer options with an open-source model (Qwen3 via Ollama) through the site's `/api/assistant` endpoint |
| Streamlit app, CLI, MCP server | Internal testing tools |
| Tests | 80 Python + 17 browser tests (Edge); engine and landing also pass in Chrome, Firefox and WebKit |
| Test pack | `scripts/make_test_pack.py` → `~/efactura-test-pack` (3 invented clients, problem files, 8,217-invoice stress file, `TEST_PLAN.md` with expected numbers) |
| Login, hosting, domain, legal pages | **Not done** |
| Real invoices | **Never tested** |
| Demand | **Untested** |
| Version control | Private GitHub repo gabrieln2805/efactura-audit, branch `main` |

## Next (immediate)

In order; owner in brackets.

1. **[Gabriel] Name:** search "Clarifact" in the OSIM and EUIPO trademark databases (class 9 software, 42 SaaS),
   then register clarifact.ro. clarifact.com is taken by someone else (unknown use). Fallbacks: Contrapreț,
   Lupa Facturi (both .ro looked free on 11 Oct).
2. **[Gabriel] Entity:** decide the company that publishes the site (Law 365/2002 requires its name, address,
   trade-register number, CUI and contact on the site).
3. **[Gabriel] Try the app with the test pack** (`TEST_PLAN.md`) and sign off `docs/web-parity-checklist.md`;
   open it once on an iPhone or Mac (Safari untested on a real device).
4. **[Claude] Launch basics, no accounts needed:**
   - serve Pyodide and its packages from our own domain (no third-party CDN);
   - draft terms of use, privacy policy, storage notice and the provider-identification page, for a lawyer to review;
   - hide developer options in the production build;
   - wording pass: "verificare", and "not a financial audit" in the disclaimer;
   - Romanian text for the data-test messages.
5. **[Claude] First-run experience:** guided import ("Where are your invoices?": from SPV, from the accounting
   software, a folder or ZIP), company detected from the invoices (no CUI field), plain-language import results.
6. **[Claude] Several clients in one browser** (a client switcher, one workspace each): the accountant use case.
7. **[Claude] Supplier price-increase report**, the launch hook, with a demo scenario where suppliers pass on the
   August 2025 VAT change.
8. **[Gabriel] Lawyer review** of the name, terms and privacy policy; then **publish the free beta** and run
   5–10 conversations with accountants and controllers.
9. **[Claude] Investigate:** whether SPV sync can run entirely in the browser (ANAF OAuth and CORS), and whether
   ANAF's public company-status API can be called from the browser. These decide what needs a server.

## Market (researched 11 Oct 2026)

| Category | Examples | Overlap |
|---|---|---|
| Invoicing and accounting software with SPV retrieval | SmartBill, FGO, Oblio, Facturis, SAGA, WinMentor, NextUp, Keez, Nexus ERP | Low: they fetch and book invoices; some add AI chat (FGO, Facturis). No line-level price analysis found |
| SPV download and archive apps | efacturaspv.ro, ispv.ro, iApp, SimpluSPV (from 49 EUR/month), 4Secunde, e-Tigris, ARHIVAR | None: commodity |
| **in-balanta.ro** (closest for SMEs) | VAT dashboard, cash flow; checks: VAT rate, inactive supplier, duplicates at import, bank-account change alert; multi-company for accountants; automatic SPV sync; 3 months free; claims 4,000+ companies | Medium: covers header-level checks; no line-price or near-duplicate analysis found |
| **Profluo** (large companies) | Automated commercial verification: prices vs contracts, orders and goods receipts (2-/3-way matching), duplicates, supplier price trends, ML | High on prices, but needs contracts/ERP data and an implementation; not self-serve for SMEs |
| Supplier-risk monitoring | Termene.ro (insolvency, state debts, shareholder changes; in SmartBill), Zarina CRM | Low: company-level |
| Accountant portfolio | ManagerConta (SmartBill, free) | Indirect |

**Gap:** no self-serve SME tool found that measures supplier price increases from invoice lines without contracts
or an ERP. **Our weak spot:** manual import versus in-balanta's automatic SPV sync. **Changed context:** OUG
13/2026 (March 2026) removed the e-TVA notices for P300 differences, so the P300 preview is less urgent.

## Product direction (re-ranked 11 Oct 2026)

**Positioning:** purchase control for SMEs and their accountants: price intelligence per invoice line, checks
before payment, and invoices that never leave the user's computer. Not an SPV archive or connector.

| # | Focus | Why |
|---|---|---|
| 1 | **Supplier price-increase report** (launch hook) | Unique, measured in lei, works without contracts; shareable PDF |
| 2 | **Effortless first import** | Users who get stuck at import never see the value |
| 3 | **Accountants as the channel** | Several clients per browser now; a monthly supplier-control report per client they can bill |
| 4 | **Basics in-balanta has** | Supplier fiscal status from ANAF (inactive, VAT cancelled); our near-duplicate check already goes further |
| 5 | **Check before paying** | Bank payment batch vs e-Factura history (different account, paid twice, flagged invoices) |
| 6 | **SPV sync** | Browser-only if technically possible (unique with privacy); otherwise a paid server feature |
| Later | Tax-deduction protection (SAF-T/ledger vs e-Factura, P300 preview), cross-company price benchmarks, AI assistant (parked; open-source model hosted in the EU) | |

**Pricing hypothesis:** free beta; later basics at market level and an insights tier at 49–149 RON/month,
justified by the lei the reports find. To validate in the conversations.

## Launch checklist (legal and trust)

Not legal advice; a Romanian lawyer reviews it once before going public.

- **Invoices never reach us** (processed and stored in the browser): keep it literally true. No analytics or
  error reporting that captures content; the AI assistant, when it returns, says exactly what it sends.
- **Provider identification** on the site (Law 365/2002): company name, address, trade-register number, CUI, contact.
- **Privacy policy:** what we process (server and CDN logs, IP addresses), storage in the browser, third parties.
  Self-host Pyodide so no third-party CDN sees users' IPs.
- **Storage notice** (Law 506/2004): the local database and preferences are strictly necessary for the service
  the user asked for, so no consent banner while there are no analytics or advertising cookies (to confirm).
- **Terms of use:** free beta, as is, limited liability; flags are prompts to check, not conclusions; no tax or
  accounting advice; **not a financial audit**; the user confirms the right to process the invoices imported.
- **Wording:** no suggestion of a financial audit (Law 162/2017) or of any link with ANAF; "e-Factura" only to
  describe the invoices.

## Architecture

- **Free tier, local-first:** a static site; the engine runs in the user's browser (Pyodide in a Web Worker).
  Invoices are uploaded as ZIPs, processed and stored in the browser, and never reach our servers. Login
  (later) stores only the account, the company's CUI and name, and the subscription.
- **Server-side, only where needed:** the AI assistant endpoint (`/api/assistant`, open-source model in the EU),
  ANAF company-status lookups if the browser cannot call ANAF directly, SPV sync if it cannot run in the browser,
  alerts. Paid features live on the server because browser-side gating can be bypassed.
- **Repo layout:** `src/efactura_audit` is the engine, shared by the website, the Streamlit app and the CLI;
  the web app is `web/app/` (the spike is `web/spike/`). The marts (`fct_invoices`, `fct_flags`,
  `dim_suppliers`, ...) are what the UI reads.

## History of phase B (web version of the tool)

Built 8 Oct 2026 and tested automatically (B1 engine and shell, B2 main screens, B3 remaining screens, B4 landing,
cross-browser, performance budget); Gabriel's sign-off of `docs/web-parity-checklist.md` is still open. Stack:
Vite, React, TypeScript; Pyodide worker; Plotly.js; `@hpcc-js/wasm-graphviz`; own sortable table; UI strings
from `app/i18n.py`; OPFS; Playwright. scikit-learn loads in the background after start-up and is awaited only
before a check run, which halved the start-up time.

## Setup on Gabriel's PC

- Project: `D:\DS ML\efactura-audit`, virtualenv in `.venv` (Windows, PowerShell, Python 3.14). Claude Code
  running on the PC can use the `.venv` directly (tests, demo, CLI); a session that is only linked to the
  folder can write files but not run it. Git: `main`, pushed to the private repo github.com/gabrieln2805/efactura-audit.
- Editable install (`pip install -e ".[all,dev]"`): code changes need only an app restart. **Stop the app and
  any `explore` window before any pip install**, or Windows locks `efactura-audit.exe` (WinError 32). A failed
  install leaves `.venv\Lib\site-packages\~factura_audit-*.dist-info` and "No module named efactura_audit":
  delete that folder and re-run the install. Pasting several commands at once runs them all even if the first fails.
- Dependencies: `pip install .` installs only the engine (what the browser needs). Extras: `reports`,
  `assistant`, `app`, `all`, and `dev` (pytest, plus rapidfuzz for the parity test). The install scripts use `[all]`.
- An old app copy can keep port 8501 after its window closes. `efactura-audit app` now moves to the next free
  port and says so; to stop the old one:
  `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8501 -State Listen).OwningProcess -Force`.
- Workspaces: default `C:\Users\Gabriel\.efactura-audit`; demo `C:\Users\Gabriel\efactura-demo`.
- Start the app: `scripts\start_app.bat -w C:\Users\Gabriel\efactura-demo`.
- Web app: `cd web/app`, `npm install` once, then `npm run dev` (http://127.0.0.1:5180) or `npm test`
  (Playwright in the installed Edge; Firefox and WebKit were installed with `npx playwright install firefox webkit`).
  The dev server uses the repo's `.venv` to rebuild the engine wheel when Python code changes.
- Browser spike: `python web/spike/prepare.py`, then
  `python -m http.server 8731 --bind 127.0.0.1 --directory web/spike` and open http://127.0.0.1:8731/.
- Gotchas already hit: Windows blocks the unsigned `.ps1` (use `scripts\install_windows.bat` or
  `-ExecutionPolicy Bypass`); `-w` goes before the command; in PowerShell use `$env:USERPROFILE`, not
  `%USERPROFILE%`; paste one command at a time.

## Open issues / backlog

| Issue | Priority | Note |
|---|---|---|
| Demand for a self-serve web tool | High | Free beta and 5–10 conversations (Next, step 8) |
| Name "Clarifact" not yet checked | High | OSIM/EUIPO search and domain registration (Next, step 1) |
| Safari on a real device untested | High | Playwright's WebKit on Windows has no OPFS, so only the "data not kept" warning was checked there. Safari without `createWritable` uses the snapshot fallback (tested in Chromium with `?storage=snapshot`) |
| Pyodide loads from the jsDelivr CDN | High (before launch) | Third-party CDN sees users' IPs; serve it from our own domain, with a strict content security policy |
| Hosted assistant server for production | Parked | Same contract as `web/app/dev/assistantProxy.ts`, deployed with login and per-account quotas. Model: open source (decided 11 Oct), served in the EU, either by an inference provider for open models or on our own GPU server (vLLM/Ollama); compare cost per question vs a fixed GPU. Ship it with `approved: true` only after the Romanian test passes. Qwen3 8B is the first candidate; larger open models if it fails |
| Local Ollama from the website | Medium | Needs `OLLAMA_ORIGINS` set to the site's address; Chrome may also need Private Network Access headers. The web assistant has no MCP option (no subprocess in a browser) |
| Real-data validation | High | First real archives come from early web users or friendly companies |
| Browser: first visit about 15 s and 50 MB | Medium | Report packages load only when a report is built, scikit-learn after start-up. Still to do: ship the DejaVu font instead of matplotlib (−7 MB), Service Worker cache |
| Browser: audit about 2× slower than native | Low | 4 s for 964 invoices; check with 10k invoices |
| Data-test messages are English only | Medium | Users will see them on the website; add RO text |
| Engine code is visible in the browser | Accepted | The value is the product, sync and monitoring, not secret rules |
| Repeat purchases with identical totals raise medium duplicate flags | Medium | Tune after real-data feedback |
| Strict item matching can split one product into two (toner example) | Low | Seller item codes avoid it; `utils._SYNONYMS` for per-client fixes |
| Sparse suppliers can look "new" | Low | Medium/low severity only |
| `amount_ron` / `unit_price_ron` still converted in Python at import | Low | Could move to staging (rounding must match Python's) |
| `mcp` pinned below 2 | Low | Internal tool now; migrate to `MCPServer` when convenient |
| Local-model approval (Ollama) | Low | Internal only; the web assistant will use a server-side model |

## Decisions

- **11 Oct 2026:**
  - Product name **Clarifact** (no "e-Factura", no "audit"); UI says "verificare" / "checks" instead of "audit".
  - AI assistant parked ("coming soon"); when it returns it uses open-source models hosted in the EU, not GPT.
  - Focus to win clients: price-increase report, effortless import, accountants (several clients per browser),
    ANAF supplier status; not SPV archiving. Free beta first.
- **8 Oct 2026:**
  - The web app has its own design (dark navigation rail, cards, Inter font), not Streamlit's; functions and
    numbers match.
  - The assistant runs in the browser engine: providers call the APIs with synchronous XMLHttpRequest from the
    worker when httpx is missing, so the agent loop, redaction and model test stay unchanged Python.
  - Phase B is an exact web version of today's tool; new features come only after login and go-live.
  - Positioning is purchase control (price intelligence per line, checks before payment, AI that closes the
    loop, privacy), not SPV sync or archiving, which competitors sell at 5–8 RON/month.
  - Differentiators in ranked order: price-increase report, check before paying, AI that closes the loop,
    tax-deduction protection, cross-company benchmarks, accountant channel, proven privacy.
  - Gabriel sets up login and accounts after phase B works.
- **7 Oct 2026: the product becomes a website.** Free tier local-first: invoices processed in the user's
  browser. Paid tier: server-side ANAF sync, alerts, assistant, multiple companies, used only when the
  company opts in. The Streamlit app, CLI and MCP server are kept for internal testing. This replaces "everything
  runs on the client's machine": invoices stay on the user's device unless they turn on a paid server feature.
- The engine core depends only on duckdb, pandas, numpy, scikit-learn, lxml and pyyaml, all available in
  Pyodide. rapidfuzz was replaced by `fuzzy.py`, which gives bit-identical scores (tested on 200k random pairs
  and every real item-name pair).
- Cloud models get redacted tool results (IBAN/CNP masked, sole traders pseudonymised), never raw invoices.
- Item matching is strict on purpose (a wrong merge invents price increases).
- Duplicate totals must match within ±0.05 lei by default.
- New-supplier flags are high only with another risk signal.
- Autoencoder uses scikit-learn, not PyTorch (also keeps it runnable in the browser).
- Data layer is dbt-style but built in, not real dbt-duckdb (dbt adds 34 packages and sends usage telemetry by
  default). Models use dbt syntax (`ref`, `source`, `schema.yml`) so a later move is mechanical.
- All models are views. SQL computes measures; Python applies `config.toml` thresholds and keeps the stateful
  algorithms. Consumers read marts only; checks may read intermediate models.
- Refactors are checked against a snapshot of every flag, score, item group and tool output on seeds 7, 3, 11.

## Session log

- **24 Sep 2026:** Built the MVP (0.1.0): importer, 5 checks, reports, app, assistant, MCP server, model test,
  synthetic data, 48 tests. Installed on Gabriel's PC. Made a single test invoice and a 964-invoice test pack.
- **30 Sep 2026:** 0.1.1: approved models shared across workspaces, `<think>` blocks from reasoning models
  stripped, robust `--version`. Added the validation kit (`docs/validation/`) and this file. Switched the PC
  to an editable install. `app` picks the next free port when 8501 is taken; 52 tests.
- **7 Oct 2026:**
  - Tested the install (51/52; MCP broken by `mcp 2.2.0`, pinned `mcp<2`) and set up git.
  - 0.2.0: dbt-style data layer (3 staging, 5 intermediate, 7 mart views, 35 data tests, `build`); checks,
    app, report and assistant read the models; 0.1.x workspaces migrate on open. Flags, ML scores, item groups
    and tool outputs are identical on seeds 7, 3 and 11.
  - `explore` command (DuckDB UI). 0.2.0 installed on the PC. Private GitHub repo.
  - Streamlit Data tab (lineage, table browser, charts, data tests, SQL), checked in light and dark themes.
  - **Direction changed to a website.** Feasibility spike: the engine runs in Pyodide with identical flags
    (`web/spike/README.md` has the timings). rapidfuzz replaced by `fuzzy.py`; dependencies split into a light
    core plus `reports`/`assistant`/`app`/`all`/`dev` extras. Plan written in this file. 67 tests.
- **8 Oct 2026:** Competitor check (in-balanta, ARHIVAR) and 2026 context (e-TVA compliance notices removed,
  P300 still published; 15 % fine and no VAT deduction for B2B invoices outside e-Factura; ANAF public API for
  supplier status; name-to-IBAN check for RON only from 2027; ViDA 2030). Ranked the differentiators; wrote the
  phased action plan (B: web parity, C: accounts and go-live, D: differentiators, E: paid tier).
- **8 Oct 2026 (later):** Built phase B, `web/app/`:
  - B1: `efactura_audit.web` JSON API; Pyodide worker with OPFS storage and a one-tab lock; app shell.
  - B2: Overview, Flags (with review), Invoices, Suppliers.
  - B3: Import, Data, Report, Settings, AI assistant.
  - B4: landing page, disclaimer footer, parity checklist, Chrome/Firefox/WebKit runs, storage fallback for
    Safari, performance budget met.
  - Browser tests compare every KPI and caption with the native engine and the Python formatting.
  - Model test: Ollama is not installed on the PC, so the test could not run. It now stops with the reason when
    the model cannot be reached, and the web Settings screen disables it while Ollama is off.
- **9 Oct 2026:** Test pack for trying the web app as an accounting firm (`scripts/make_test_pack.py` →
  `~/efactura-test-pack`, with `TEST_PLAN.md` and expected numbers; all steps checked in Edge, including 8,217
  invoices imported and audited in 44 s). Fixed: a corrupt ZIP in an upload stopped the whole import. New on the
  Import screen: import history with Remove, "keep only this company" when buyers are mixed, and "start fresh"
  (reviews kept unless asked). Every import now gets an id (`imports` table, `raw_invoices.import_id`); older
  workspaces show their invoices as one "earlier imports" row.
- **10 Oct 2026:** The web assistant uses the site's own AI endpoint (`/api/assistant`, OpenAI wire format): the
  engine's new `auditefactura` provider sends no key; the local dev server forwards to OpenAI or Mistral with the
  key from the environment. Users see no provider or model pickers; a model that has not passed the Romanian test
  shows "run the test now" instead of a blank list. Ollama, own keys, untested models and the model test moved
  to Settings → Developer options. The model test also stops at once when the key or model is rejected.
- **11 Oct 2026:** The assistant's model is open source, not GPT: the assistant server defaults to Qwen3 8B through
  Ollama's OpenAI-compatible API, and no longer picks up OPENAI_API_KEY/MISTRAL_API_KEY from the environment (only
  explicit ASSISTANT_* settings). The Assistant and Settings screens show why the server is unavailable (e.g.
  "Ollama is not running"). Gabriel's PC (RTX 5050 8 GB, 32 GB RAM) fits qwen3:8b on the GPU.
  AI work is **parked**: users see "coming soon" on the Assistant screen, the menu and the landing page; the
  working assistant stays reachable through Settings → Developer options.
  Market research (Romanian tools: in-balanta, Profluo, SPV apps, invoicing software, Termene) and the legal
  checklist for publishing; focus re-ranked. **Renamed to Clarifact**: brand, page titles, report titles and file
  names, Streamlit title; "audit" replaced by "verificare"/"checks" in the UI; hosted provider id is now `hosted`.

## For Claude at the start of a session

Read this file, then `README.md`. For web work, read README's "Web app" section; run
`npm test` in `web/app` after web changes. Run
`python -m pytest` before changing code; for engine changes, compare flags against the 3-seed snapshot.
The project doc `claude/status.md` in the "efactura anomaly" Project mirrors this file.
