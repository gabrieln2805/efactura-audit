# Web app parity checklist (Phase B sign-off)

Check each line in the web app against the Streamlit app, both on the demo data. Tick it when the web app shows
the same thing. Lines marked *(tested)* are also covered by an automated Playwright test.

How to run both:

```bash
efactura-audit app                 # Streamlit, http://127.0.0.1:8501
cd web/app && npm run dev          # web app, http://127.0.0.1:5180  (then "Încercați demo-ul")
```

## Overview
- [ ] Company and period line *(tested)*
- [ ] 5 KPIs: invoices, suppliers, spend, open flags, amount to review; hovering a compact amount shows the exact value *(tested)*
- [ ] Flags by check (bar chart) and spend per month (bar chart, hover shows the invoice count) *(tested)*
- [ ] Most important flags: 10 rows with severity, check, supplier, amount, finding *(tested)*

## Flags
- [ ] Filters: check, severity, supplier, minimum amount, show dismissed *(tested: check, show dismissed)*
- [ ] "N results · total X lei" caption *(tested)*
- [ ] Table: severity, check, supplier, invoice numbers (first 3), date, amount, finding, status
- [ ] Detail: severity and check, title, flag id · rule · score
- [ ] Notes (warning boxes), "what to check" box
- [ ] Price history chart for price increases: history line, flagged points, dotted baseline *(tested)*
- [ ] Evidence (open by default except for price increases)
- [ ] Invoices involved (first 6), each with its lines and ANAF id *(tested)*
- [ ] Review: open / confirmed / dismissed with a note; saving updates the list and the counts *(tested)*

## Invoices
- [ ] Filters: supplier, number, from, to, flagged only *(tested: supplier)*
- [ ] Caption with "· max 100" when there are more *(tested)*
- [ ] Table columns; selecting a row shows the invoice with its lines and flags *(tested)*

## Suppliers
- [ ] Table: name, CUI, invoices, spend, first/last invoice, flags *(tested)*
- [ ] Detail: monthly spend chart, bank accounts (IBANs masked), flags *(tested)*

## Data
- [ ] Tables & models: table picker, lineage graph with the selected table highlighted, catalog, columns with tests, first 500 rows, model SQL *(tested)*
- [ ] Charts: spend heatmap (95th-percentile cap, table view), supplier invoices over time (severity diamonds, median), item price history (flagged items first, ⚠) *(tested)*
- [ ] Data tests: re-run, summary line, table, failing rows and SQL for warnings/failures *(tested on a deliberately inconsistent upload)*
- [ ] SQL: read-only SELECT, 5000-row cap, error message, CSV download *(tested)*

## Import
- [ ] ANAF 60-day note, buyer CUI filter, upload of ZIP/XML, import summary and errors *(tested)*
- [ ] Load demo data
- [ ] Checks on the imported data (all passed, or the issues) and the import log *(tested)*

## Report
- [ ] Report language; Excel and PDF built and downloaded *(tested)*; same content as the Streamlit reports

## AI assistant
- [ ] AI disclaimer; provider (Ollama, cloud only when enabled); model list (tested models, untested when allowed)
- [ ] Cloud: own API key, warning about what is sent; local: "no data leaves the computer"
- [ ] "No approved model" warning; examples; conversation with tool-call sources; new conversation *(tested with a mocked cloud model)*

## Settings
- [ ] Allow cloud models; show untested models; Ollama status
- [ ] Romanian model test (progress while it runs, result, tested-models table)
- [ ] Review feedback per rule; thresholds

## Everywhere
- [ ] Romanian and English, light and dark theme, usable on a phone
- [ ] Disclaimer on every page *(tested)*; data kept after closing and reopening the browser *(tested)*

## Intentional differences
| Streamlit | Web | Why |
|---|---|---|
| Sidebar, tabs, Streamlit look | Dark navigation rail, cards, own components | Requested: not the Streamlit style |
| "Folder path on this computer" | "Choose a folder" picker and drag-and-drop | A web page cannot read paths |
| Assistant "via the MCP server" option | Not offered | The MCP server is a separate process; the browser has none. Planned as a hosted MCP server (Phase E) |
| Thresholds in `config.toml` | Shown read-only (defaults) | No config file in the browser; editing is a new feature, not parity |
| Workspace path in the sidebar | "Stored only in this browser" | The data lives in the browser's private storage |
| Tables show raw column names | Translated column labels | Presentation only |
| Import: only adds data (reset via CLI) | Import history with Remove per import, "keep only this company" for mixed buyers, "start fresh" with or without reviews | Asked for on 9 Oct 2026 |
| Ollama works out of the box | Ollama must allow the site's origin (`OLLAMA_ORIGINS`) | Browser security; noted in Settings |

Signed off by: ____________  Date: ________
