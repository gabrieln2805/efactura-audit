# Browser spike: the engine in Pyodide

Answers one question: can the existing Python engine run entirely in a user's browser? It can.
`index.html` loads Pyodide from the jsDelivr CDN, installs the engine wheel, imports a ZIP of 964
ANAF ZIPs, runs the audit, queries a mart, and builds the Excel and PDF reports.

```bash
python web/spike/prepare.py                                   # wheel + upload.zip + manifest.json
python -m http.server 8731 --bind 127.0.0.1 --directory web/spike
# open http://127.0.0.1:8731/
```

## Result (7 Oct 2026, Pyodide 314.0.7, headless Edge on Gabriel's PC)

| Step | First visit | Second visit (browser cache) |
|---|---|---|
| Pyodide runtime | 3.8–4.2 s | 0.9 s |
| Engine packages (numpy, pandas, scipy, scikit-learn, lxml, duckdb, pyyaml) | 11.9–21.5 s | 6.9 s |
| Import 964 invoices | 3.1–3.3 s | 2.6 s |
| Audit (5 checks, ML, 35 data tests) | 6.0–6.1 s (native: 2.0 s) | 5.7 s |
| Report packages (matplotlib, openpyxl, reportlab) | 4.4–4.7 s | 0.7 s |
| Excel + PDF | 2.1 s | 2.2 s |

- **Same result as native:** 37 flags with identical IDs, rules, severities, scores and amounts (ML scores
  included); 35/35 data tests pass.
- **Download:** about 52 MB on the first visit (scipy 13 MB, duckdb 8 MB, matplotlib 7 MB, scikit-learn 4 MB,
  pandas 4 MB), cached afterwards.
- **What it took:** replacing rapidfuzz (no Pyodide build) with `efactura_audit/fuzzy.py`, which gives
  bit-identical scores, and installing the wheel with `deps=False`. openpyxl and reportlab install from PyPI
  at runtime.

## What a product needs on top of this

- Load the engine in a Web Worker, started when the page opens, so the UI stays responsive and the first-visit
  wait overlaps with login.
- Load the report packages only when a report is requested; matplotlib is there only for its DejaVu font.
- Persist the database across visits. The spike keeps it in Pyodide's in-memory file system, so it is gone on
  reload: use OPFS or IndexedDB, or keep the uploaded ZIPs and re-import.
- Serve Pyodide and the wheels from our own origin, with a Service Worker cache, instead of jsDelivr.
