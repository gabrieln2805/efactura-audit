# STATUS: e-Factura Anomaly Audit

**Start every session here.** Update the "Now", "Next" and "Session log" sections at the end of each session.

Last updated: 7 Oct 2026 · Version 0.2.0 · Phase: **Validation (step 2 of 5)**

## Now

The MVP works end to end on synthetic data and is installed on Gabriel's PC. The next job is not more code:
it's finding out whether controllers will commit to a pilot. The validation kit is ready in `docs/validation/`.

| Area | State |
|---|---|
| Audit engine (import, 5 checks, review, reports) | Done. 99–100 % recall on synthetic data; 9,895 invoices audit in 12 s |
| Data layer (dbt-style SQL models + data tests) | Done (0.2.0): raw → staging → intermediate → marts; 35 data tests; flags identical to 0.1.1 on 3 seeds |
| App (Streamlit, RO/EN) | Done; runs on Gabriel's PC |
| AI assistant + MCP server | Built; **no model approved yet** (Ollama not yet installed on the PC). MCP fixed (pinned `mcp<2`) |
| Tests | 59 passing |
| Version control | Git since 7 Oct 2026; private GitHub repo gabrieln2805/efactura-audit (branch `main`) |
| Real invoices | **Never tested.** First real data comes from a pilot |
| Validation | Kit ready (outreach, interview script, demo walkthrough, tracker); **0 conversations so far** |
| Employment IP check | **Not done**: required before any paid work |

## Next

In order. Owner in brackets.

1. ~~**[Gabriel] Switch to an editable install.**~~ Done 30 Sep: the package loads from
   `D:\DS ML\efactura-audit\src`, so Claude's changes apply after an app restart.
2. ~~**[Gabriel] Pick up 0.2.0.**~~ Done 7 Oct: 0.2.0 installed, demo and default workspaces migrated, 35/35
   data tests pass on both.
3. **[Gabriel] Rehearse the demo:** follow `docs/validation/demo-walkthrough.md` once, start to finish.
4. **[Gabriel] Local model (optional for demos):** install Ollama, run `ollama pull qwen3:8b`, then
   `.venv\Scripts\efactura-audit test-model --model qwen3:8b` (Ollama's folder already exists on the PC). Paste the result to Claude if it isn't approved.
5. **[Gabriel] Confirm the go/no-go threshold** in `docs/validation/README.md` (proposal: ≥ 10 conversations,
   ≥ 3 dated pilot commitments, ≥ 3 costly incidents reported, within 2 weeks).
6. **[Gabriel] Read the employment contract** (IP, side activity, non-compete) before the first conversation.
7. **[Gabriel] Outreach:** 7–10 companies + 3 accounting firms using `outreach-ro.md`; log each call in
   `tracker.csv` the same day.
8. **[Claude, when there's data] Review the tracker** and recommend go / adjust / stop.
9. **[Both] Pilots:** run on the client's machine; the controller marks each flag confirmed/dismissed; tune
   thresholds from `efactura-audit status` feedback stats.
10. **[Gabriel] Go/no-go and pricing** based on what the pilots found.

## Setup on Gabriel's PC

- Project: `D:\DS ML\efactura-audit`, virtualenv in `.venv` (Windows, PowerShell, Python 3.14). Claude Code
  running on the PC can use the `.venv` directly (tests, demo, CLI); a session that is only linked to the
  folder can write files but not run it. Git: `main`, pushed to the private repo github.com/gabrieln2805/efactura-audit.
- Editable install (`pip install -e .`): code changes need only an app restart. **Stop the app and any
  `explore` window before any pip install**, or Windows locks `efactura-audit.exe` (WinError 32). A failed
  install leaves `.venv\Lib\site-packages\~factura_audit-*.dist-info` and "No module named efactura_audit":
  delete that folder and re-run the install. Pasting several commands at once runs them all even if the first fails.
- An old app copy can keep port 8501 after its window closes. `efactura-audit app` now moves to the next free
  port and says so; to stop the old one:
  `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8501 -State Listen).OwningProcess -Force`.
- Workspaces: default `C:\Users\Gabriel\.efactura-audit`; demo `C:\Users\Gabriel\efactura-demo`. Use one
  workspace per client.
- Start the app: `scripts\start_app.bat -w C:\Users\Gabriel\efactura-demo`.
- Gotchas already hit: Windows blocks the unsigned `.ps1` (use `scripts\install_windows.bat` or
  `-ExecutionPolicy Bypass`); `-w` goes before the command; in PowerShell use `$env:USERPROFILE`, not
  `%USERPROFILE%`; paste one command at a time.
- Test data: `test-pack-964-invoices.zip` (upload in the Import tab) or the "Încarcă date demo" button.

## Open issues / backlog

| Issue | Priority | Note |
|---|---|---|
| Real-data validation | High | Only possible via pilot |
| No approved model | Medium | Needed for the assistant part of the demo only |
| Repeat purchases with identical totals raise medium duplicate flags | Medium | Tune after pilot feedback |
| Strict item matching can split one product into two (toner example) | Low | Seller item codes avoid it; `utils._SYNONYMS` for per-client fixes |
| Sparse suppliers can look "new" | Low | Medium/low severity only |
| Opt-in CUI lookup against ANAF's VAT register | Later | Sends CUIs out, so off by default |
| Packaged desktop installer | Later | After validation |
| Data-test messages are English only | Low | Shown in the Import tab; add RO text if controllers will read them |
| `amount_ron` / `unit_price_ron` still converted in Python at import | Low | Could move to staging (rounding must match Python's) |
| `mcp` pinned below 2 | Low | Migrate `mcp_server.py` to `MCPServer` (mcp 2.x API) when convenient |

## Decisions

- Everything runs on the client's machine; cloud models only with the client's key, off by default; cloud
  gets redacted tool results (IBAN/CNP masked, sole traders pseudonymised), never raw invoices.
- Item matching is strict on purpose (a wrong merge invents price increases).
- Duplicate totals must match within ±0.05 lei by default.
- New-supplier flags are high only with another risk signal.
- Autoencoder uses scikit-learn, not PyTorch, to keep installs light.
- Approved models are stored per computer (`~/.efactura-audit/approved_models.json`), not per workspace (0.1.1).
- Validation happened after the build (the plan said before); the demo is now the validation tool.
- Data layer is dbt-style but built in (0.2.0), not real dbt-duckdb: dbt adds 34 packages and sends usage
  telemetry by default, which conflicts with the light, fully local client install. Models use dbt syntax
  (`ref`, `source`, `schema.yml`) so a later move to dbt is mechanical.
- All models are views (small data, always current). SQL computes measures; Python applies `config.toml`
  thresholds and keeps the stateful algorithms. Consumers read marts only; checks may read intermediate models.
- Refactors are checked against a snapshot of every flag, score, item group and tool output on seeds 7, 3, 11.

## Session log

- **24 Sep 2026:** Built the MVP (0.1.0): importer, 5 checks, reports, app, assistant, MCP server, model test,
  synthetic data, 48 tests. Installed on Gabriel's PC (execution-policy workaround, reinstall for a stale
  package). Made a single test invoice and a 964-invoice test pack.
- **30 Sep 2026:** 0.1.1: approved models shared across workspaces (older per-workspace results still read),
  `<think>` blocks from reasoning models stripped, robust `--version`; 51 tests. Added the validation kit
  (`docs/validation/`) and this file. Wrote 0.1.1 straight into `D:\DS ML\efactura-audit`, keeping
  Gabriel's own `__init__.py` fix (version read from the installed package). Switched the PC to an editable
  install (first attempt failed because the running app locked the exe; cleaned leftover `~factura-audit`).
  `app` command now picks the next free port when 8501 is taken; 52 tests.
- **7 Oct 2026:** Tested the install: 51/52 passed. The MCP server was broken because pip had pulled `mcp 2.2.0`
  (FastMCP renamed); pinned `mcp<2`. Set up git (baseline commit). 0.2.0: dbt-style data layer in
  `transform/` (3 staging, 5 intermediate, 7 mart views, 35 data tests, `efactura-audit build`), checks, app,
  report and assistant read the models, `item_groups` replaces the in-place update, 0.1.x workspaces
  migrate on open. Flags, ML scores and item groups are identical to 0.1.1 on seeds 7, 3 and 11, and all tool
  outputs are unchanged. Two intended differences: suppliers sharing a bank account now count that flag in
  the report and Suppliers tab, and `top_suppliers` groups by CUI. 59 tests.

## For Claude at the start of a session

Read this file, then `README.md`. For validation work, read `docs/validation/` and the latest `tracker.csv`
the user shares. Run `python -m pytest` before changing code. The project doc `claude/status.md` in the
"efactura anomaly" Project mirrors this file.
