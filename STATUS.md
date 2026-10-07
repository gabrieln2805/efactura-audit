# STATUS: e-Factura Anomaly Audit

**Start every session here.** Update the "Now", "Next" and "Session log" sections at the end of each session.

Last updated: 7 Oct 2026 · Version 0.2.0 · Phase: **Web product, phase A (set-up and demand test)**

## Now

**Direction changed on 7 Oct 2026:** the product becomes a website (working name auditefactura.ro). Users log
in, add their company and audit their invoices, free at first, with a paid subscription later. The Streamlit
app, CLI and MCP server stay for internal testing.

The engine runs unchanged in a browser: the spike (`web/spike/`) imported 964 invoices and produced the same
37 flags as the native run, with the same IDs, scores and amounts, plus the Excel and PDF reports.

| Area | State |
|---|---|
| Audit engine (import, 5 checks, review, reports) | Done. 99–100 % recall on synthetic data; 9,895 invoices audit in 12 s natively |
| Engine in the browser (Pyodide) | **Proven** (spike): first visit 16–25 s to load (52 MB), return visit about 8 s; import 3 s and audit 6 s for 964 invoices |
| Data layer (dbt-style SQL models + data tests) | Done: raw → staging → intermediate → marts; 35 data tests. The marts are what the web UI will read |
| Streamlit app (internal) | Done, with Data tab (lineage, table browser, charts, data tests, SQL) |
| AI assistant + MCP server | Built for local use; moves to the server for the web paid tier |
| Web frontend, login, hosting | **Not started** |
| Tests | 67 passing |
| Version control | Private GitHub repo gabrieln2805/efactura-audit, branch `main` |
| Real invoices | **Never tested** |
| Demand | **Untested** for a self-serve web tool |

## Next

The full plan with reasoning is in "Web product plan" below. In order; owner in brackets.

1. **[Gabriel] Set-up decisions:** register the domain (auditefactura.ro or another); choose the legal entity
   that will sell the subscription (SRL or PFA); confirm the stack (Supabase EU for login and data,
   Cloudflare Pages for the static site, React or SvelteKit for the UI).
2. **[Gabriel] Accounts:** create the Supabase project (region Frankfurt) and the Cloudflare account; share
   the project URLs (not the secret keys) with Claude.
3. **[Claude] Landing page + live demo (phase B):** a Romanian landing page with a waitlist, and a "try it"
   page that runs the engine on synthetic data in the browser (built from the spike).
4. **[Gabriel] Demand test:** send people to the landing page (LinkedIn, accountants' groups, the outreach
   list in `docs/validation/`); talk to 5–10 controllers and accountants about the paid tier (ANAF sync,
   alerts). Decide the success threshold before starting (e.g. signups and demo runs over 3–4 weeks).
5. **[Claude] Free web MVP (phase C)**, once phase B shows interest.
6. **[Both] Paid tier (phase D)** after the free tier has users.

## Web product plan (agreed 7 Oct 2026)

**Architecture: local-first first, server features for the paid tier.**

- **Free tier, local-first:** a static site; the engine runs in the user's browser (Pyodide in a Web Worker).
  Invoices are uploaded as ZIPs, processed and stored in the browser, and never reach our servers. Login
  (Supabase) stores only the account, the company's CUI and name, and the subscription. This costs almost
  nothing per free user, keeps "your invoices never leave your computer", and keeps GDPR exposure to account
  data.
- **Paid tier, server-side:**
  - ANAF SPV sync through ANAF's OAuth API: the company authorizes once with its qualified certificate; the
    token lasts 90 days.
  - Continuous monitoring and alerts, e.g. a changed IBAN before an invoice is paid.
  - The AI assistant, with the existing redaction.
  - Several companies per account (accounting firms) and history across devices.

  These need a server, and they are what is worth a subscription. Browser-side gating could be bypassed, so
  paid features must not live in the browser.

| Phase | Content | Effort (solo) |
|---|---|---|
| A. Set-up | Domain, legal entity, Supabase and Cloudflare accounts, stack choice | days |
| B. Landing + demo | Romanian landing page, waitlist (Supabase table), in-browser demo on synthetic data, privacy-friendly analytics | 1–2 weeks |
| C. Free MVP | Engine in a Web Worker started when the page opens; database kept between visits (OPFS/IndexedDB); UI for import, overview, flag review, invoices, suppliers, data checks and Excel/PDF; Supabase login and company profile (name looked up by CUI in ANAF's public register through an edge function); terms, privacy policy, cookie notice; tax-advice disclaimer on every page | 5–8 weeks |
| D. Paid tier | Backend (EU region) for ANAF OAuth sync, alerts, assistant and multiple companies; GDPR processor documents (DPA, sub-processors, breach procedure); Stripe; our own subscription invoices go through e-Factura (B2B in Romania), e.g. via the SmartBill or Oblio API | 6–10 weeks |

**Repo layout:** `src/efactura_audit` stays the engine, shared by the website, the Streamlit app and the CLI.
The web app goes in `web/` (the spike is `web/spike/`), Supabase migrations and edge functions in `supabase/`.
The marts (`fct_invoices`, `fct_flags`, `dim_suppliers`, …) are what the UI reads.

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
- Browser spike: `python web/spike/prepare.py`, then
  `python -m http.server 8731 --bind 127.0.0.1 --directory web/spike` and open http://127.0.0.1:8731/.
- Gotchas already hit: Windows blocks the unsigned `.ps1` (use `scripts\install_windows.bat` or
  `-ExecutionPolicy Bypass`); `-w` goes before the command; in PowerShell use `$env:USERPROFILE`, not
  `%USERPROFILE%`; paste one command at a time.

## Open issues / backlog

| Issue | Priority | Note |
|---|---|---|
| Demand for a self-serve web tool | High | Phase B tests it |
| Real-data validation | High | First real archives come from early web users or friendly companies |
| Browser: database lost on reload | High (phase C) | Spike uses Pyodide's in-memory file system; use OPFS/IndexedDB or keep the uploaded ZIPs |
| Browser: first-visit load 16–25 s, 52 MB | Medium | Web Worker started on page open; load report packages only on demand; matplotlib is only there for its font, so ship the DejaVu TTF instead (−7 MB); serve Pyodide from our own origin with a Service Worker |
| Browser: audit about 3× slower than native | Low | 6 s for 964 invoices; show progress; check with 10k invoices |
| Data-test messages are English only | Medium | Users will see them on the website; add RO text |
| Engine code is visible in the browser | Accepted | The value is the product, sync and monitoring, not secret rules |
| Repeat purchases with identical totals raise medium duplicate flags | Medium | Tune after real-data feedback |
| Strict item matching can split one product into two (toner example) | Low | Seller item codes avoid it; `utils._SYNONYMS` for per-client fixes |
| Sparse suppliers can look "new" | Low | Medium/low severity only |
| `amount_ron` / `unit_price_ron` still converted in Python at import | Low | Could move to staging (rounding must match Python's) |
| `mcp` pinned below 2 | Low | Internal tool now; migrate to `MCPServer` when convenient |
| Local-model approval (Ollama) | Low | Internal only; the web assistant will use a server-side model |

## Decisions

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

## For Claude at the start of a session

Read this file, then `README.md`. For web work, read "Web product plan" above and `web/spike/README.md`. Run
`python -m pytest` before changing code; for engine changes, compare flags against the 3-seed snapshot.
The project doc `claude/status.md` in the "efactura anomaly" Project mirrors this file.
