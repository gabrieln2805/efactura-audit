# STATUS: e-Factura Anomaly Audit

**Start every session here.** Update the "Now", "Next" and "Session log" sections at the end of each session.

Last updated: 8 Oct 2026 · Version 0.2.0 · Phase: **Web product: phase B built, waiting for Gabriel's review**

## Now

**Direction changed on 7 Oct 2026:** the product becomes a website (working name auditefactura.ro). Users log
in, add their company and audit their invoices, free at first, with a paid subscription later. The Streamlit
app, CLI and MCP server stay for internal testing.

**Phase B is built** (`web/app/`): every screen of the Streamlit app, with the engine running in the browser
and the same numbers (37 flags with identical IDs, scores and amounts on the demo). It is not deployed
anywhere yet; it runs locally with `npm run dev`.

| Area | State |
|---|---|
| Audit engine (import, 5 checks, review, reports) | Done. 99–100 % recall on synthetic data; 9,895 invoices audit in 12 s natively |
| Engine in the browser (Pyodide) | Done. First visit about 15 s to start (about 50 MB), return visit 8 s; demo audit 4 s. Data kept in the browser (OPFS) |
| Data layer (dbt-style SQL models + data tests) | Done: raw → staging → intermediate → marts; 35 data tests. The web UI reads the marts |
| Streamlit app (internal) | Done, with Data tab (lineage, table browser, charts, data tests, SQL) |
| AI assistant + MCP server | Built for local use; moves to the server for the web paid tier |
| Web app (phase B) | **Built**: landing page plus all 9 screens, RO/EN, light/dark, phone layout. Own design (dark rail, cards). Parity checklist: `docs/web-parity-checklist.md` |
| Login, hosting, domain | After phase B works (Gabriel's decision, 8 Oct) |
| Competitors | in-balanta.ro (cloud, SPV sync, IBAN-change and inactive-supplier alerts, cash flow; 4,000+ companies) and ARHIVAR (SPV archive, thresholds; 8 RON/company/month). Neither analyses invoice lines |
| Tests | 74 Python + 13 browser tests (Edge); engine and landing also pass in Chrome, Firefox and WebKit |
| Version control | Private GitHub repo gabrieln2805/efactura-audit, branch `main` |
| Real invoices | **Never tested** |
| Demand | **Untested** for a self-serve web tool |

## Next

In order; owner in brackets. Details and acceptance checks are in "Action plan" below.

1. **[Gabriel] Review phase B:** `cd web/app`, `npm install`, `npm run dev`, open http://127.0.0.1:5180, go
   through `docs/web-parity-checklist.md` next to the Streamlit app, and sign it off. If possible, also open it
   on an iPhone or Mac (Safari is the one browser not tested on a real device).
2. **[Claude] Fixes from the review.**
3. **[Gabriel] Phase C set-up** (domain, legal entity, Supabase and Cloudflare accounts); then **[Claude]**
   login, company profile, deploy (including serving Pyodide from our own domain), and **[Gabriel]** the demand test.
4. **[Both] Phase D:** the differentiators, in the ranked order below.

## Product direction (ranked 8 Oct 2026)

**Positioning:** not another e-Factura archive or SPV connector (those cost 5–8 RON/company/month). Instead,
purchase control for SMEs and their accountants: price intelligence per invoice line, checks before
payment, AI that turns flags into money recovered, and invoices that never leave the user's computer.

| # | Differentiator | What it is |
|---|---|---|
| 1 | **Supplier price-increase report** (launch hook) | "How much did your suppliers' price increases cost you?" Net price changes per item since the August 2025 VAT change, extra cost in lei, compared with official inflation for the category (INS CPI/PPI) |
| 2 | **Check before paying** | Upload the payment batch or bank export (CSV, MT940, CAMT.053) before sending it. Flags: a different account than the supplier's e-Factura history, invoices paid twice, payments for flagged invoices, invoices that never went through e-Factura. Name-to-IBAN verification doesn't cover RON transfers until 2027 |
| 3 | **AI that closes the loop** | For each flag, the assistant gathers the evidence and drafts the Romanian email to the supplier (credit note request, account confirmation, price justification) or an internal note; the user approves. Paid tier: hosted MCP server with login, so Claude or ChatGPT can use the company's data |
| 4 | **Tax-deduction protection** | e-Factura compared with the purchase ledger (SAF-T D406 or an accounting export): invoices booked without e-Factura (15 % fine for the buyer, no VAT deduction) and e-Factura invoices not booked (missed deductions). Supplier fiscal status from ANAF's public API (inactive, VAT cancelled, cash-accounting VAT, e-Factura register). Preview of the pre-filled VAT return (P300) |
| 5 | **Price benchmarks across companies** (long-term moat) | Invoice lines classified into CPV codes (embeddings running in the browser, which also fixes the "toner 85A" split); opt-in sharing of aggregates only (category, unit price, month), shown when at least 5 companies contribute; seeded from public procurement prices (SEAP) |
| 6 | **Accountants as the sales channel** | Portfolio view of all clients ranked by risk; a monthly supplier-control report under the accountant's brand, which they can bill as a service |
| 7 | **Privacy, proven** | A strict browser policy that blocks uploads of invoice data; optionally open-source the engine so the claim can be checked |

**Basics to match cheaply (paid tier):** SPV sync and legal archive (ANAF keeps messages about 60 days),
inactive-supplier alerts, several companies per account, notifications.
**Pricing hypothesis:** basics at market level; the insights tier at 49–149 RON/month, justified by the lei
the reports find. To be validated in the demand test.

## Architecture

- **Free tier, local-first:** a static site; the engine runs in the user's browser (Pyodide in a Web Worker).
  Invoices are uploaded as ZIPs, processed and stored in the browser, and never reach our servers. Login
  (Supabase) stores only the account, the company's CUI and name, and the subscription.
- **Paid tier, server-side:** ANAF SPV sync through ANAF's OAuth API (the company authorizes once with its
  qualified certificate; the token lasts 90 days), alerts, the hosted assistant and MCP server, several
  companies per account, benchmark aggregation. Paid features live on the server because browser-side
  gating can be bypassed.
- **Repo layout:** `src/efactura_audit` stays the engine, shared by the website, the Streamlit app and the CLI.
  The web app goes in `web/app/` (the spike is `web/spike/`), Supabase migrations and edge functions in
  `supabase/`. The marts (`fct_invoices`, `fct_flags`, `dim_suppliers`, ...) are what the UI reads.

## Action plan

### Phase B: web version of today's tool (built 8 Oct 2026; waiting for the sign-off)

**Scope: exactly what the Streamlit app does today.** Same screens, same results, nothing new; the engine
runs in the browser. Out of scope: login, payments, server, new features.

**Stack:** Vite, React and TypeScript; the engine in a Pyodide Web Worker behind a typed message API; Plotly.js
(cartesian bundle) so the charts match the current app; `@hpcc-js/wasm-graphviz` for the lineage graph (the same
Graphviz engine Streamlit uses); a small sortable table component of our own (TanStack Table 9 changed its API
and was more than needed); UI strings exported from `app/i18n.py`, so RO/EN has one source;
the database kept in OPFS (the browser's private file storage); Playwright tests in Edge. Node.js 24 is
installed on the PC.

| Milestone | Deliverables | Done when |
|---|---|---|
| **B1. Engine and shell** (week 1) | `efactura_audit.web` module with JSON in and out (import files, run audit, query a mart, save feedback, reports, settings); worker that starts loading when the page opens, with progress; database kept between visits; "load demo data"; app shell with tabs, RO/EN and light/dark | A Playwright test loads the demo and gets the same 37 flags as native; a reload keeps the data |
| **B2. Main screens** (weeks 2–3) | Overview (KPIs, flags by check, monthly spend, top flags); Flags (filters, detail with evidence and price chart, invoices involved, confirm/dismiss with note); Invoices (search, detail with lines and flags); Suppliers (table, monthly spend, bank accounts, flags) | Every element of these four Streamlit tabs is present, with the same numbers on the demo |
| **B3. Remaining screens** (weeks 3–4) | Import (ZIP/XML upload, buyer CUI filter, data checks, import log); Data (lineage, table browser, charts, data tests, SQL); Report (Excel and PDF download); Settings (thresholds, review statistics); AI assistant (cloud providers off by default, key kept for the session only, same redaction; local Ollama when it allows the site's origin; providers call the APIs with `fetch` instead of httpx) | Same as B2 for these tabs; a deliberately broken workspace shows its failing data tests |
| **B4. Landing page and finish** (week 5) | Romanian landing page (English too): what the tool does, privacy, "try the demo"; disclaimer on every page; parity checklist against Streamlit; cross-browser check (Edge, Chrome, Firefox, Safari); performance budget | Gabriel signs off the checklist; return-visit load ≤ 10 s; demo audit ≤ 8 s |

**Result:** B1–B4 done and tested automatically; only Gabriel's sign-off is left. Return visit 7.9 s, first visit
14.9 s, audit 4.1 s (Edge, Gabriel's PC). scikit-learn (with scipy, the slowest packages) loads in the background
after start-up and is awaited only before an audit, which halved the start-up time.

### Phase C: accounts and go-live (about 1–2 weeks, after B)

- **[Gabriel]** Domain (auditefactura.ro or another), legal entity, Supabase (Frankfurt) and Cloudflare accounts.
- **[Claude]** Supabase login (email and passkeys); company profile with the name looked up by CUI in ANAF's
  public register (through an edge function); waitlist; terms, privacy policy, cookie notice; deploy to
  Cloudflare Pages with a strict content security policy; privacy-friendly analytics.
- **[Gabriel] Demand test:** share the site; 5–10 conversations with controllers and accountants; decide the
  success threshold before starting.

### Phase D: differentiators in the free tier, in ranked order (each about 1–3 weeks)

1. **Price-increase report:** add a scenario to the synthetic data where suppliers pass on the VAT change, so the
   demo has something to show; bring in INS price indices.
2. **Check before paying:** parsers for the bank export formats of the main Romanian banks.
3. **AI that closes the loop:** drafts per flag, using the user's own key until the server exists.
4. **Tax-deduction protection:** SAF-T D406 parser, ANAF status lookup through the edge function, P300 preview.

**Verify before building:** INS indices per product category; SEAP unit-price open data; the export formats
of the main banks.

### Phase E: paid tier and server

SPV OAuth sync, archive and alerts; hosted assistant and MCP server with login; benchmark aggregation (#5);
accountant portfolio (#6); Stripe plus our own e-Factura invoicing for subscriptions; GDPR processor documents
(DPA, sub-processors, breach procedure).

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
| Demand for a self-serve web tool | High | The demand test in phase C |
| Safari on a real device untested | High | Playwright's WebKit on Windows has no OPFS, so only the "data not kept" warning was checked there. Safari without `createWritable` uses the snapshot fallback (tested in Chromium with `?storage=snapshot`) |
| Pyodide loads from the jsDelivr CDN | Medium (phase C) | Serve it from our own domain, with a strict content security policy |
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

## For Claude at the start of a session

Read this file, then `README.md`. For web work, read "Action plan" above and README's "Web app" section; run
`npm test` in `web/app` after web changes. Run
`python -m pytest` before changing code; for engine changes, compare flags against the 3-seed snapshot.
The project doc `claude/status.md` in the "efactura anomaly" Project mirrors this file.
