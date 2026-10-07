from datetime import date, timedelta

import pytest

from efactura_audit.checks.duplicates import number_relation
from efactura_audit.config import default_settings
from efactura_audit.engine import run_audit
from efactura_audit.evaluate import evaluate
from efactura_audit.importer import import_sources
from efactura_audit.importer.anaf_zip import XmlSource
from efactura_audit.itemmatch import names_match
from efactura_audit.store import Store
from efactura_audit.ubl_writer import InvoiceDoc, Line, Party, render
from efactura_audit.utils import normalize_item_name as n

SUP = Party("Furnizor Test SRL", "18547290", iban="RO49AAAA1B31007593840000")
BUY = Party("Client SRL", "14399840")


def test_recall_on_injected_anomalies(demo):
    ev = evaluate(demo["store"].flags(include_dismissed=True), demo["root"] / "ground_truth.json")
    assert ev.recall >= 0.95, ev.report()
    for check, r in ev.recall_by_check().items():
        assert r >= 0.8, (check, ev.report())
    # the legitimate cancel-and-reissue must not be a medium/high duplicate
    assert all(r["found"] for r in ev.rows if r["rule"] == "legit_reissue"), ev.report()
    # most flags point at a real injected problem
    assert ev.explained_share >= 0.85, ev.report()


def test_every_flag_has_evidence_and_both_languages(demo):
    flags = demo["store"].flags()
    assert len(flags) > 10
    assert flags["title_ro"].str.len().gt(0).all() and flags["title_en"].str.len().gt(0).all()
    assert flags["evidence"].str.len().gt(2).all()
    assert set(flags["severity"]) <= {"high", "medium", "low"}


@pytest.mark.parametrize("a,b,rel", [
    ("FV-1023", "FV-1023", "same"), ("FV-1023", "FV 1023", "same"), ("FV-1023", "FV-1023A", "suffix"),
    ("FV-1023", "FV-1032", "transposed"), ("FV-1023", "FV-1024", "adjacent"), ("FV-1023", "FV-1250", "different"),
])
def test_number_relation(a, b, rel):
    assert number_relation(a, b) == rel


@pytest.mark.parametrize("a,b,same", [
    ("Transport marfa Bucuresti - Cluj-Napoca", "Transport marfa Bucuresti - Iasi", False),
    ("Hartie copiator A4 80g/mp, top 500 coli", "HARTIE A4 80G 500 COLI/TOP", True),
    ("Hartie copiator A4 80g", "Hartie xerox A4 80g", True),
    ("Anvelopa 315/70 R22.5", "Anvelopa 295/80 R22.5", False),
    ("Energie electrica activa", "Energie electrica reactiva", False),
    ("Pix gel albastru set 12", "Set 12 pixuri gel albastre", True),
])
def test_item_name_matching(a, b, same):
    assert names_match(n(a), n(b)) is same


def _store_with(tmp_path, docs):
    store = Store(tmp_path / "t.duckdb")
    import_sources(store, (XmlSource(f"{i}.xml", render(d), str(i)) for i, d in enumerate(docs)))
    return store


def test_recurring_invoices_are_not_duplicates(tmp_path):
    """Identical monthly subscriptions must not be flagged as near-duplicates."""
    docs = [InvoiceDoc(number=f"SUB-{100 + 17 * m}", issue_date=date(2025, 1 + m, 3), supplier=SUP, buyer=BUY,
                       lines=[Line("Abonament suport IT lunar", 1, 4200.0, 21.0)]) for m in range(10)]
    store = _store_with(tmp_path, docs)
    run_audit(store, default_settings())
    assert store.flags().query("check_name == 'near_duplicate'").empty


def test_vat_rules_on_handcrafted_invoices(tmp_path):
    docs = [
        InvoiceDoc(number="A-1", issue_date=date(2026, 3, 2), supplier=SUP, buyer=BUY,
                   lines=[Line("Ciment", 10, 30.0, 19.0)]),                            # 19% after Aug 2025
        InvoiceDoc(number="A-2", issue_date=date(2026, 3, 3), supplier=SUP, buyer=BUY,
                   lines=[Line("Ciment", 10, 30.0, 21.0)], tax_error=40.0),            # VAT does not add up
        InvoiceDoc(number="A-3", issue_date=date(2026, 3, 4), supplier=SUP, buyer=BUY,
                   lines=[Line("Profil", 10, 30.0, 21.0, vat_category="AE")]),       # reverse charge with VAT
    ]
    store = _store_with(tmp_path, docs)
    run_audit(store, default_settings())
    rules = {(r.rule, r.invoice_numbers) for r in store.flags().query("check_name == 'vat'").itertuples()}
    assert ("rate_not_valid_for_date", '["A-1"]') in rules
    assert ("arithmetic", '["A-2"]') in rules
    assert ("reverse_charge_with_tax", '["A-3"]') in rules


def test_iban_one_off_and_price_step(tmp_path):
    start = date(2025, 1, 6)
    docs = []
    for i in range(12):
        price = 50.0 if i < 8 else 62.0
        iban = "RO09BCYP0000001234567890" if i == 5 else None
        docs.append(InvoiceDoc(number=f"P-{i + 1}", issue_date=start + timedelta(days=21 * i), supplier=SUP, buyer=BUY,
                               lines=[Line("Folie stretch 23 microni", 20 + i, price, 21.0)], iban=iban))
    store = _store_with(tmp_path, docs)
    run_audit(store, default_settings())
    flags = store.flags()
    one_off = flags.query("rule == 'iban_one_off'")
    assert len(one_off) == 1 and "P-6" in one_off.iloc[0]["invoice_numbers"]
    price = flags.query("check_name == 'price_increase'")
    assert len(price) == 1 and "P-9" in price.iloc[0]["invoice_numbers"] and price.iloc[0]["rule"] == "step"


def test_feedback_survives_rerun(demo, tmp_path):
    store = demo["store"]
    fid = store.flags().iloc[0]["flag_id"]
    store.set_feedback(fid, "dismissed", "known, agreed with supplier")
    run_audit(store, default_settings())
    assert fid not in set(store.flags()["flag_id"])
    assert fid in set(store.flags(include_dismissed=True)["flag_id"])
    stats = store.feedback_stats()
    assert stats["dismissed"].sum() >= 1
    store.set_feedback(fid, "open")
