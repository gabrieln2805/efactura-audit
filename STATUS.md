# STATUS: e-Factura Anomaly Audit

**Start every session here.** Update the "Now", "Next" and "Session log" sections at the end of each session.

Last updated: 30 Sep 2026 · Version 0.1.1 · Phase: **Validation (step 2 of 5)**

## Now

The MVP works end to end on synthetic data and is installed on Gabriel's PC. The next job is not more code:
it's finding out whether controllers will commit to a pilot. The validation kit is ready in `docs/validation/`.

| Area | State |
|---|---|
| Audit engine (import, 5 checks, review, reports) | Done. 99–100 % recall on synthetic data; 9,895 invoices audit in 12 s |
| App (Streamlit, RO/EN) | Done; runs on Gabriel's PC |
| AI assistant + MCP server | Built; **no model approved yet** (Ollama not yet installed on the PC) |
| Tests | 52 passing |
| Real invoices | **Never tested.** First real data comes from a pilot |
| Validation | Kit ready (outreach, interview script, demo walkthrough, tracker); **0 conversations so far** |
| Employment IP check | **Not done**: required before any paid work |

## Next

In order. Owner in brackets.

1. ~~**[Gabriel] Switch to an editable install.**~~ Done 30 Sep: the package loads from
   `D:\DS ML\efactura-audit\src`, so Claude's changes apply after an app restart.
2. **[Gabriel] Rehearse the demo:** follow `docs/validation/demo-walkthrough.md` once, start to finish.
3. **[Gabriel] Local model (optional for demos):** install Ollama, run `ollama pull qwen3:8b`, then
   `.venv\Scripts\efactura-audit test-model --model qwen3:8b` (Ollama's folder already exists on the PC). Paste the result to Claude if it isn't approved.
4. **[Gabriel] Confirm the go/no-go threshold** in `docs/validation/README.md` (proposal: ≥ 10 conversations,
   ≥ 3 dated pilot commitments, ≥ 3 costly incidents reported, within 2 weeks).
5. **[Gabriel] Read the employment contract** (IP, side activity, non-compete) before the first conversation.
6. **[Gabriel] Outreach:** 7–10 companies + 3 accounting firms using `outreach-ro.md`; log each call in
   `tracker.csv` the same day.
7. **[Claude, when there's data] Review the tracker** and recommend go / adjust / stop.
8. **[Both] Pilots:** run on the client's machine; the controller marks each flag confirmed/dismissed; tune
   thresholds from `efactura-audit status` feedback stats.
9. **[Gabriel] Go/no-go and pricing** based on what the pilots found.

## Setup on Gabriel's PC

- Project: `D:\DS ML\efactura-audit`, virtualenv in `.venv` (Windows, PowerShell). Claude can write to this
  folder directly when the session is linked to the PC (it can't run the Windows `.venv` itself).
- Editable install (`pip install -e .`): code changes need only an app restart. **Stop the app before any
  pip install**, or Windows locks `efactura-audit.exe` (WinError 32).
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

## Decisions

- Everything runs on the client's machine; cloud models only with the client's key, off by default; cloud
  gets redacted tool results (IBAN/CNP masked, sole traders pseudonymised), never raw invoices.
- Item matching is strict on purpose (a wrong merge invents price increases).
- Duplicate totals must match within ±0.05 lei by default.
- New-supplier flags are high only with another risk signal.
- Autoencoder uses scikit-learn, not PyTorch, to keep installs light.
- Approved models are stored per computer (`~/.efactura-audit/approved_models.json`), not per workspace (0.1.1).
- Validation happened after the build (the plan said before); the demo is now the validation tool.

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

## For Claude at the start of a session

Read this file, then `README.md`. For validation work, read `docs/validation/` and the latest `tracker.csv`
the user shares. Run `python -m pytest` before changing code. The project doc `claude/status.md` in the
"efactura anomaly" Project mirrors this file.
