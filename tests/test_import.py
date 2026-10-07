import io
import zipfile
from datetime import date

import pytest

from efactura_audit.importer import import_paths, import_sources, iter_uploaded
from efactura_audit.importer.parser import NotAnInvoice, parse_invoice_xml
from efactura_audit.store import Store
from efactura_audit.ubl_writer import SIGNATURE_STUB, InvoiceDoc, Line, Party, render
from efactura_audit.utils import (clean_cui, cui_control_digit, is_sole_trader, is_valid_cui, is_valid_iban,
                                  mask_iban, normalize_item_name)

SUP = Party("Test Furnizor SRL", "18547290", iban="RO49AAAA1B31007593840000", city="Cluj-Napoca")
BUY = Party("Test Client SRL", "14399840")


def doc(**kw):
    base = dict(number="TF-100", issue_date=date(2025, 9, 1), supplier=SUP, buyer=BUY,
                lines=[Line("Ciment 40kg", 10, 30.0, 21.0), Line("Paine 500g", 5, 4.0, 11.0)])
    base.update(kw)
    return InvoiceDoc(**base)


def test_cui_and_iban_validation():
    body = "1854729"
    assert is_valid_cui(body + str(cui_control_digit(body)))
    assert is_valid_cui("RO" + body + str(cui_control_digit(body)))
    assert not is_valid_cui(body + str((cui_control_digit(body) + 1) % 10))
    assert clean_cui(" ro 123 ") == "123"
    assert is_valid_iban("RO49AAAA1B31007593840000")
    assert not is_valid_iban("RO49AAAA1B31007593840001")
    assert mask_iban("RO49AAAA1B31007593840000") == "RO49****************0000"
    assert is_sole_trader("Popescu Ion PFA") and not is_sole_trader("Betonex SRL")


def test_normalize_item_name():
    assert normalize_item_name("Hârtie copiator A4, 80 g/mp") == "hartie copiator a4 80g mp"
    assert normalize_item_name("Adeziv 25 kg") == normalize_item_name("ADEZIV 25KG")


def test_parse_invoice_fields():
    inv = parse_invoice_xml(render(doc()))
    assert inv.number == "TF-100" and inv.issue_date == date(2025, 9, 1)
    assert inv.supplier_cui == "18547290" and inv.buyer_cui == "14399840"
    assert inv.supplier_iban == "RO49AAAA1B31007593840000"
    assert len(inv.lines) == 2 and inv.lines[0].unit_price == 30.0
    assert inv.line_total == 320.0
    assert inv.tax_total == pytest.approx(300 * 0.21 + 20 * 0.11)
    assert inv.payable == pytest.approx(320 + 63 + 2.2)
    assert {v.rate for v in inv.vat} == {21.0, 11.0}
    assert inv.fx_to_ron == 1.0


def test_credit_note_is_negative():
    inv = parse_invoice_xml(render(doc(credit_note=True, number="CN-1")))
    assert inv.is_credit_note and inv.payable < 0 and inv.lines[0].quantity < 0


def test_foreign_currency_rate_from_ron_vat():
    inv = parse_invoice_xml(render(doc(currency="EUR", fx_to_ron=5.0)))
    assert inv.currency == "EUR"
    assert inv.fx_to_ron == pytest.approx(5.0, rel=1e-3)
    assert inv.payable_ron == pytest.approx(inv.payable * 5.0, rel=1e-3)


def test_non_invoice_rejected():
    with pytest.raises(NotAnInvoice):
        parse_invoice_xml(SIGNATURE_STUB)
    with pytest.raises(NotAnInvoice):
        parse_invoice_xml(b"<not-xml")


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_anaf_zip_nested_and_signature_skipped(tmp_path):
    inner = _zip({"4001.xml": render(doc()), "semnatura_4001.xml": SIGNATURE_STUB})
    outer = _zip({"4001.zip": inner, "4002.xml": render(doc(number="TF-101"))})
    srcs = list(iter_uploaded("export.zip", outer))
    assert sorted(s.anaf_id for s in srcs) == ["4001", "4002"]
    store = Store(tmp_path / "a.duckdb")
    res = import_sources(store, iter(srcs))
    assert res.imported == 2 and res.skipped == 0
    # re-import: exact duplicates are skipped
    assert import_sources(store, iter_uploaded("export.zip", outer)).duplicates == 2


def test_buyer_filter_and_bad_files(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.xml").write_bytes(render(doc()))
    (tmp_path / "in" / "b.xml").write_bytes(render(doc(number="X", buyer=Party("Alt Client", "123"))))
    (tmp_path / "in" / "c.xml").write_bytes(b"<Error/>")
    (tmp_path / "in" / "d.zip").write_bytes(b"not a zip")
    store = Store(tmp_path / "a.duckdb")
    res = import_paths(store, [tmp_path / "in"], buyer_cui="RO14399840")
    assert (res.imported, res.other_buyer, res.skipped, res.failed) == (1, 1, 1, 1)


def test_synthetic_dataset_imports_cleanly(demo):
    assert demo["store"].count_invoices() == demo["summary"]["invoices"]
    eur = demo["store"].df("SELECT fx_to_ron FROM fct_invoices WHERE currency = 'EUR'")
    assert not eur.empty and eur["fx_to_ron"].between(4.8, 5.2).all()
