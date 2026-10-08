"""Prepare what the web app takes from the Python side (run by `npm run dev` and `npm run build`).

- public/py/: the engine wheel and manifest.json (wheel name, version, Pyodide packages to load)
- src/i18n/strings.json: the UI strings from efactura_audit/app/i18n.py, so RO/EN has one source
- tests/fixtures/demo_flags.json: the native engine's flags on the demo data, which the browser must match

The wheel and fixture are rebuilt only when the engine's source changes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
PKG = ROOT / "src" / "efactura_audit"
PY_OUT = APP / "public" / "py"
I18N_OUT = APP / "src" / "i18n" / "strings.json"
FIXTURE = APP / "tests" / "fixtures" / "demo_flags.json"

sys.path.insert(0, str(ROOT / "src"))


def source_hash() -> str:
    h = hashlib.sha256((ROOT / "pyproject.toml").read_bytes())
    for p in sorted(PKG.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(PKG).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


# loaded in the background after the engine is ready, and awaited only before an audit (the slowest to load)
AUDIT_ONLY = {"scikit-learn"}


def pyodide_packages() -> list[str]:
    """The engine's dependencies from pyproject.toml, by name (Pyodide ships them all)."""
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    return [re.split(r"[<>=!~ \[]", d, maxsplit=1)[0] for d in deps]


def export_i18n() -> None:
    from efactura_audit.app import i18n
    data = {"S": {k: list(v) for k, v in i18n.S.items()},
            "CHECKS": {k: list(v) for k, v in i18n.CHECKS.items()},
            "SEVERITY": {k: list(v) for k, v in i18n.SEVERITY.items()},
            "STATUS": {k: list(v) for k, v in i18n.STATUS.items()},
            "EXAMPLES": i18n.EXAMPLES}
    I18N_OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if not I18N_OUT.exists() or I18N_OUT.read_text(encoding="utf-8") != text:
        I18N_OUT.write_text(text, encoding="utf-8", newline="\n")


def build_wheel(digest: str) -> None:
    PY_OUT.mkdir(parents=True, exist_ok=True)
    for old in PY_OUT.glob("*.whl"):
        old.unlink()
    subprocess.run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-q", "-w", str(PY_OUT)], check=True)
    wheel = next(PY_OUT.glob("efactura_audit-*.whl"))
    version = wheel.name.split("-")[1]
    packages = pyodide_packages()
    manifest = {"wheel": wheel.name, "version": version, "hash": digest,
                "packages": [p for p in packages if p not in AUDIT_ONLY],
                "audit_packages": [p for p in packages if p in AUDIT_ONLY],
                "report_packages": {"pyodide": ["matplotlib"], "pypi": ["openpyxl", "reportlab"]}}
    (PY_OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")


def write_fixture() -> None:
    """The native engine's results on the demo, and what the Streamlit app shows for them (Romanian formatting)."""
    from efactura_audit.app.i18n import fmt_compact, fmt_lei, tr
    from efactura_audit.web import Api

    def res(api, method, **args):
        return json.loads(api.call(method, json.dumps(args)))["result"]

    with tempfile.TemporaryDirectory() as tmp:
        api = Api(tmp)
        api.call("load_demo")
        flags = res(api, "flags")
        ov = res(api, "overview", lang="ro")["overview"]
        inv = res(api, "search_invoices")
        betonex = res(api, "search_invoices", supplier="Betonex")
        sups = res(api, "suppliers")
        api.store = None   # release the DuckDB file before the folder is removed
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(({k: f[k] for k in ("flag_id", "check_name", "rule", "severity", "score", "amount_at_risk_ron")}
                   for f in flags), key=lambda f: f["flag_id"])
    FIXTURE.write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")

    def matching(n, amt):
        return tr("matching", "ro", n=n, amt=fmt_lei(amt, "ro"))

    price = [f for f in flags if f["check_name"] == "price_increase"]
    expect = {
        "kpi": {"invoices": f"{ov['invoices']:,}".replace(",", "."), "suppliers": str(ov["suppliers"]),
                "spend": fmt_compact(ov["total_spend_ron"], "ro"), "flags": str(ov["flags_total"]),
                "to_review": fmt_compact(ov["amount_to_review_ron"], "ro")},
        "flags_caption": matching(len(flags), sum(f["amount_at_risk_ron"] or 0 for f in flags)),
        "price_caption": matching(len(price), sum(f["amount_at_risk_ron"] or 0 for f in price)),
        "invoices_caption": matching(inv["total_matching"], inv["total_amount_ron"]) + " · max 100",
        "betonex_caption": matching(betonex["total_matching"], betonex["total_amount_ron"])
                           + (" · max 100" if betonex["total_matching"] > 100 else ""),
        "suppliers": len(sups), "top_supplier": sups[0]["supplier_name"],
    }
    (FIXTURE.parent / "demo_expect.json").write_text(json.dumps(expect, indent=1, ensure_ascii=False),
                                                     encoding="utf-8", newline="\n")
    write_broken_upload()


def write_broken_upload() -> None:
    """A ZIP of 4 invoice XMLs, one issued to a different buyer: the import works and the data tests warn."""
    import zipfile
    from datetime import date

    from efactura_audit.ubl_writer import InvoiceDoc, Line, Party, render
    sup = Party("Furnizor Test SRL", "18547290", iban="RO49AAAA1B31007593840000")
    buyer, other = Party("Client SRL", "14399840"), Party("Alt Client SRL", "40000004")
    docs = [InvoiceDoc(number=f"FT-{100 + m}", issue_date=date(2025, 1 + m, 10), supplier=sup, buyer=buyer,
                       lines=[Line("Hartie copiator A4 80g", 10 + m, 24.5, 21.0)]) for m in range(3)]
    docs.append(InvoiceDoc(number="FT-900", issue_date=date(2025, 5, 2), supplier=sup, buyer=other,
                           lines=[Line("Toner HP 85A", 1, 210.0, 21.0)]))
    with zipfile.ZipFile(FIXTURE.parent / "broken_upload.zip", "w") as z:
        for i, d in enumerate(docs):
            z.writestr(f"{5000000000 + i}.xml", render(d))


def main() -> None:
    export_i18n()
    digest = source_hash()
    manifest = PY_OUT / "manifest.json"
    current = json.loads(manifest.read_text(encoding="utf-8")).get("hash") if manifest.exists() else None
    if current == digest and (FIXTURE.parent / "broken_upload.zip").exists() and any(PY_OUT.glob("*.whl")):
        print(f"engine unchanged ({digest}), wheel and fixture kept")
        return
    build_wheel(digest)
    write_fixture()
    print(f"engine wheel, i18n and demo fixture ready ({digest})")


if __name__ == "__main__":
    main()
