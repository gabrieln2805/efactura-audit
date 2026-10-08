"""Build a test pack for trying the web app the way an accounting firm would, with expected results.

    python scripts/make_test_pack.py [output folder]      (default: ~/efactura-test-pack)

Writes SPV-style uploads for three invented client companies (a main client split into two overlapping
exports, a second client, a 10x-volume client), a ZIP of problem files, a folder of single SPV downloads,
the answer key of planted anomalies, and TEST_PLAN.md. The expected numbers in the plan come from running
the same steps through the engine natively; the browser must show the same.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import sys
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from efactura_audit.app.i18n import fmt_compact, fmt_lei  # noqa: E402
from efactura_audit.evaluate import evaluate  # noqa: E402
from efactura_audit.synthetic import Generator  # noqa: E402
from efactura_audit.ubl_writer import SIGNATURE_STUB, render  # noqa: E402
from efactura_audit.web import Api  # noqa: E402

FIRM_A, FIRM_B, FIRM_C = "Solaris Prodcom SRL", "Mureș Agro Trade SRL", "Orizont Construct Grup SRL"
# the demo's suppliers under other (invented) names, so this client does not look like the demo
SUPPLIER_NAMES = {
    "Betonex Materiale SRL": "Cimentar Construct SRL", "Granit Trans Logistic SRL": "Transilvan Cargo SRL",
    "Hârtia Veche Office SRL": "Birotica Plus Office SRL", "Papetăria Delta Nord SRL": "Papetăria Mureș SRL",
    "Ambalaje Carpați SRL": "Pack Expert Ambalaje SRL", "Softlink Servicii IT SRL": "Cloudware Soluții IT SRL",
    "Voltaris Energie SRL": "Electra Furnizare Energie SRL", "Curățenie Profi Services SRL": "Clean Office Facility SRL",
    "Agro Fresh Distribuție SRL": "Bio Natura Distribuție SRL", "Eurosteel Trading SRL": "Metal Danubius SRL",
    "Pază Vigilent Grup SRL": "Scut Pază și Protecție SRL", "Anvelope Rapid SRL": "Roata Rapidă SRL",
    "Service Auto Motorex SRL": "Auto Expert Service SRL", "Netcom Fibră SRL": "Rețea Net Fibră SRL",
    "Tipografia Litera SRL": "Print Studio Grafic SRL", "Imobiliara Pipera Park SRL": "Logistic Park Ilfov SRL",
    "Echipamente Industriale Tehno SRL": "Industrial Rulmenți SRL", "Aquaserv Pure SRL": "Apa Clară Dozatoare SRL",
    "Materiale Rapid Construct SRL": "Construct Fast Materiale SRL",
    "Consulting Global Partners SRL": "Advisory Partners Group SRL", "Ionescu Mihai Andrei PFA": "Popescu Andrei Daniel PFA",
}


def generate(seed: int, buyer: str, months: int = 18, scale: float = 1.0):
    gen = Generator(seed=seed, months=months, scale=scale)
    gen.buyer.name = buyer
    out = gen.generate()
    for d in out.docs:   # rename after generating: the generator picks credit notes by supplier name
        d.supplier.name = SUPPLIER_NAMES.get(d.supplier.name, d.supplier.name)
    for t in out.truth:
        for k in ("supplier", "cheaper_supplier", "other_supplier"):
            if k in t:
                t[k] = SUPPLIER_NAMES.get(t[k], t[k])
    return out


def spv_zip(doc, anaf_id: str) -> bytes:
    """One invoice the way SPV delivers it: <id>.zip with <id>.xml and ANAF's signature."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{anaf_id}.xml", render(doc))
        z.writestr(f"semnatura_{anaf_id}.xml", SIGNATURE_STUB)
    return buf.getvalue()


def zip_of_spv(path: Path, items: list[tuple[str, object]]) -> None:
    """Several SPV downloads in one ZIP, as an accountant exports or collects them."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for anaf_id, doc in items:
            z.writestr(f"{anaf_id}.zip", spv_zip(doc, anaf_id))


def with_ids(docs, base: int) -> list[tuple[str, object]]:
    return [(str(base + i * 7), d) for i, d in enumerate(docs)]


def problem_files(path: Path, a_items, buyer_cui: str) -> None:
    """Files that must not break an import: corrupt archives, ANAF messages, a cut-off XML, a PDF,
    an invoice already imported, and one new invoice whose VAT does not add up."""
    known_id, known_doc = a_items[10]
    last_doc = next(d for _, d in reversed(a_items) if not d.credit_note and d.currency == "RON")
    new = copy.deepcopy(last_doc)
    new.number = new.number.split("-")[0] + "-990001"
    new.issue_date = date(2026, 6, 29)
    new.tax_error = 150.0
    good_xml = render(known_doc)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("4299000001.zip", b"PK\x03\x04 this archive was cut off during download")
        z.writestr("4299000002.xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<header xmlns="mfp:anaf:dgti:efactura:mesajEroriFactuta:v1.0.1" '
                   f'Index_incarcare="4299000002" Cif_emitent="{buyer_cui}">\n  <Error errorMessage="E: validarea '
                   'structurii a esuat"/>\n</header>\n')
        z.writestr("4299000003.xml", good_xml[: len(good_xml) // 2])
        z.writestr("4299000004.zip", _signature_only("4299000004"))
        z.writestr("factura_scanata.pdf", b"%PDF-1.4 not an e-invoice")
        z.writestr(f"{known_id}.zip", spv_zip(known_doc, known_id))
        z.writestr("4299000005.zip", spv_zip(new, "4299000005"))


def _signature_only(anaf_id: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"semnatura_{anaf_id}.xml", SIGNATURE_STUB)
    return buf.getvalue()


# ------------------------------------------------------------------ expected results (native engine)
class Native:
    def __init__(self, root: Path):
        self.api = Api(root)

    def call(self, method: str, **args):
        out = json.loads(self.api.call(method, json.dumps(args)))
        if not out["ok"]:
            raise RuntimeError(out["error"])
        return out["result"]

    def import_(self, paths: list[Path], buyer: str = "") -> tuple[dict, float]:
        t0 = time.perf_counter()
        res = self.call("import_files", paths=[str(p) for p in paths], buyer_cui=buyer)
        return res, time.perf_counter() - t0

    def kpis(self) -> str:
        ov = self.call("overview", lang="ro")["overview"]
        return (f"Facturi **{ov['invoices']:,}**".replace(",", ".") + f" · Furnizori **{ov['suppliers']}** · "
                f"Achiziții **{fmt_compact(ov['total_spend_ron'], 'ro')}** · Semnalări deschise **{ov['flags_total']}** · "
                f"Sumă de verificat **{fmt_compact(ov['amount_to_review_ron'], 'ro')}**")

    def tests_line(self) -> str:
        t = self.call("data_tests")["tests"]
        n = {s: sum(1 for x in t if x["status"] == s) for s in ("pass", "warn", "fail", "error")}
        bad = ", ".join(f"`{x['test_name']}` ({x['failures']})" for x in t if x["status"] != "pass")
        return f"{n['pass']} passed, {n['warn']} warnings, {n['fail']} failed" + (f": {bad}" if bad else "")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "efactura-test-pack"
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("*.zip")) + list(out.glob("*.csv")) + list(out.glob("*.md")):
        old.unlink()

    a = generate(11, FIRM_A)
    b = generate(23, FIRM_B)
    b.docs = [d for d in b.docs if d.issue_date <= date(2025, 6, 30)]   # half a year is enough for client B
    c = generate(31, FIRM_C, scale=10)
    a_items = with_ids(a.docs, 4_211_000_000)
    p1 = out / "01_client_A_2025.zip"
    p2 = out / "02_client_A_2025-11_to_2026-06.zip"
    zip_of_spv(p1, [x for x in a_items if x[1].issue_date <= date(2025, 12, 31)])
    zip_of_spv(p2, [x for x in a_items if x[1].issue_date >= date(2025, 11, 1)])
    zip_of_spv(out / "03_client_B_other_company.zip", with_ids(b.docs, 4_223_000_000))
    p4 = out / "04_problem_files.zip"
    problem_files(p4, a_items, a.buyer.cui)
    folder = out / "05_folder_client_A_june_2026"
    folder.mkdir(exist_ok=True)
    for f in folder.glob("*"):
        f.unlink()
    for anaf_id, doc in a_items:
        if doc.issue_date >= date(2026, 6, 1):
            (folder / f"{anaf_id}.zip").write_bytes(spv_zip(doc, anaf_id))
    p6 = out / "06_stress_client_C_10x.zip"
    zip_of_spv(p6, with_ids(c.docs, 4_231_000_000))

    # expected results: the same steps through the native engine
    with tempfile.TemporaryDirectory() as tmp:
        n = Native(Path(tmp) / "a")
        s1, t1 = n.import_([p1], a.buyer.cui)
        k1 = n.kpis()
        s2, t2 = n.import_([p2], a.buyer.cui)
        k2 = n.kpis()
        flags_a = n.call("flags", include_dismissed=True)
        s3, _ = n.import_(sorted(folder.glob("*.zip")), a.buyer.cui)
        s4, _ = n.import_([out / "03_client_B_other_company.zip"], a.buyer.cui)
        s5, _ = n.import_([p4], a.buyer.cui)
        k5 = n.kpis()
        tests5 = n.tests_line()
        s6, _ = n.import_([out / "03_client_B_other_company.zip"], "")
        k6 = n.kpis()
        tests6 = n.tests_line()
        n.api.store = None
        c_native = Native(Path(tmp) / "c")
        s7, t7 = c_native.import_([p6], c.buyer.cui)
        k7 = c_native.kpis()
        c_native.api.store = None

    # answer key: the anomalies planted in client A, and whether the engine found them
    truth_path = out / "client_A_ground_truth.json"
    truth_path.write_text(json.dumps({"anomalies": a.truth}, ensure_ascii=False, indent=1), encoding="utf-8")
    ev = evaluate(flags_a, truth_path)
    truth_path.unlink()
    with open(out / "client_A_answer_key.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["check", "rule", "supplier", "invoice", "duplicate_of", "item", "date_or_from", "found_by_engine", "flag_ids"])
        for r in ev.rows:
            w.writerow([r["check"], r["rule"], r.get("supplier", ""), r.get("number", ""), r.get("original", ""),
                        r.get("item", r.get("line", "")), r.get("date", r.get("from", "")),
                        "yes" if r["found"] else "no", " ".join(r["flags"])])
    found = sum(r["found"] for r in ev.rows)

    def summary(s: dict) -> str:
        return f"`{s['summary']}`"

    size = lambda p: f"{p.stat().st_size / 1048576:.1f} MB"  # noqa: E731
    plan = f"""# Test plan: the web app as an accounting firm

Everything here is invented: companies, CUIs, people and bank accounts. Expected numbers come from the same steps
run through the engine on the PC (`scripts/make_test_pack.py`); the browser must show exactly the same.

## The clients

| Client | Company | CUI (for the buyer filter) | Invoices | Period |
|---|---|---|---|---|
| A (main) | {FIRM_A} | **{a.buyer.cui}** | {len(a.docs)} | {a.docs[0].issue_date} – {a.docs[-1].issue_date} |
| B (another client) | {FIRM_B} | {b.buyer.cui} | {len(b.docs)} | {b.docs[0].issue_date} – {b.docs[-1].issue_date} |
| C (large client) | {FIRM_C} | {c.buyer.cui} | {len(c.docs)} | {c.docs[0].issue_date} – {c.docs[-1].issue_date} |

## The files

| File | What it is |
|---|---|
| `01_client_A_2025.zip` ({size(p1)}) | Client A, Jan–Dec 2025: one SPV download (`<id>.zip` with the XML and ANAF's signature) per invoice |
| `02_client_A_2025-11_to_2026-06.zip` ({size(p2)}) | Client A, Nov 2025–Jun 2026. Nov–Dec overlap with file 01 on purpose |
| `03_client_B_other_company.zip` | Client B: invoices addressed to another company |
| `04_problem_files.zip` | A cut-off ZIP, an ANAF error message, a cut-off XML, a ZIP with only a signature, a PDF, an invoice already imported, and one new invoice of client A whose VAT does not add up |
| `05_folder_client_A_june_2026/` | Client A's June 2026 invoices as single SPV downloads, for the folder picker |
| `06_stress_client_C_10x.zip` ({size(p6)}) | Client C at 10× the volume, for the stress test |
| `client_A_answer_key.csv` | The {len(ev.rows)} anomalies planted in client A, and whether the engine found them ({found} of {len(ev.rows)}) |

## Start the empty app

Each address keeps its own data in the browser, so a new port means an empty app:

```
cd "D:\\DS ML\\efactura-audit\\web\\app"
npm run dev -- --port 5190
```

Open **http://127.0.0.1:5190/#/overview** in Edge or Chrome (not VS Code's built-in browser). Use **5191**,
**5192**… for more empty copies, e.g. one per client. To empty an address again: F12 → Application → Storage →
Clear site data. The demo stays on 5180.

## Steps and expected results (client A)

1. **Import tab:** in "CUI companie auditată", enter **{a.buyer.cui}**. Drop `01_client_A_2025.zip` (or "alegeți
   fișiere"), click **Importă**.
   - Message: {summary(s1)} (native: {t1:.1f} s; the browser is about 2× slower)
   - Overview: {k1}
2. **Import** `02_client_A_2025-11_to_2026-06.zip` (same CUI).
   - Message: {summary(s2)}. The Nov–Dec overlap must count as "already stored", not twice.
   - Overview: {k2}
   - Flags: compare with `client_A_answer_key.csv` (its `flag_ids` are the IDs the web app must show too).
3. **Import the folder:** "alegeți un folder" → `05_folder_client_A_june_2026`.
   - Message: {summary(s3)} (all June invoices came with file 02).
4. **Import** `03_client_B_other_company.zip` **with client A's CUI still filled in.**
   - Message: {summary(s4)}. Nothing changes on the Overview.
5. **Import** `04_problem_files.zip` (same CUI).
   - Message: {summary(s5)}, with an error line for the cut-off ZIP (the failed file). "Not invoices" are
     the ANAF error message and the cut-off XML; the signature-only ZIP and the PDF are ignored.
   - Overview: {k5}
   - Flags → filter "Tipar TVA": the new invoice ending in **-990001** is flagged (VAT does not add up).
   - Data → Teste date: {tests5}
6. **Review flags:** confirm a few, dismiss a few with notes; check that the counts update, "Arată și
   semnalările respinse" brings them back, and Setări → feedback per rule counts them. Close the browser, open
   the same address again: imports and reviews must still be there.
7. **Reports:** Raport → Excel and PDF, in both languages. Open them and compare with the screens.
8. **Optional, mixing clients:** import `03_client_B_other_company.zip` again with the CUI field **empty**.
   - Message: {summary(s6)}
   - Overview: {k6}
   - Data → Teste date: {tests6}. This is what an accountant sees when two clients' invoices end up in one
     workspace; use one address (port) per client instead.

## Stress test (client C)

On a fresh address (`npm run dev -- --port 5191`): import `06_stress_client_C_10x.zip` with CUI **{c.buyer.cui}**.
- Message: {summary(s7)} (native: {t7:.1f} s for import + audit; expect a few times longer in the browser)
- Overview: {k7}
- Then: click through every screen, sort the big tables, search invoices, open Data → Grafice (heatmap with
  22 suppliers), run SQL over `fct_invoice_lines`, build both reports, reload the page.

## What to note

For anything that differs from the expected numbers, is slow, unclear or broken: the step, what you did, what
you saw (a screenshot helps), and the browser. Timings worth writing down: import time per file, how long the
app takes to start on a return visit, report build time.
"""
    (out / "TEST_PLAN.md").write_text(plan, encoding="utf-8")
    print(f"test pack in {out}")
    print(f"client A: {len(a.docs)} invoices, {found}/{len(ev.rows)} planted anomalies found; client C: {len(c.docs)} invoices")


if __name__ == "__main__":
    main()
