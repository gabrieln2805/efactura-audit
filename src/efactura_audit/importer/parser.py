"""Parser for RO e-Factura invoices (UBL 2.1 Invoice / CreditNote, CIUS-RO profile).

Only the fields the audit needs are extracted. Credit notes (CreditNote root, or Invoice with
type code 381) are stored with negative amounts so that sums net out naturally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from ..utils import clean_cui, clean_iban, normalize_invoice_number, normalize_item_name, sha256_bytes, short_hash

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}
INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDIT_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CREDIT_TYPE_CODES = {"381", "396", "532"}


class NotAnInvoice(ValueError):
    """Raised for XML that is not a UBL invoice (signatures, ANAF error messages...)."""


@dataclass
class ParsedLine:
    line_no: str
    item_name: str
    item_norm: str
    seller_item_id: str
    quantity: float
    unit_code: str
    unit_price: float
    base_quantity: float
    net_amount: float
    vat_category: str
    vat_rate: float | None


@dataclass
class ParsedVat:
    category: str
    rate: float | None
    taxable: float
    tax: float


@dataclass
class ParsedInvoice:
    invoice_key: str
    number: str
    type_code: str
    is_credit_note: bool
    issue_date: date
    due_date: date | None
    currency: str
    supplier_cui: str
    supplier_vat_id: str
    supplier_name: str
    supplier_reg_no: str
    supplier_iban: str
    supplier_city: str
    buyer_cui: str
    buyer_name: str
    line_total: float
    tax_exclusive: float
    tax_total: float
    tax_inclusive: float
    payable: float
    fx_to_ron: float | None
    note: str
    xml_sha256: str
    lines: list[ParsedLine] = field(default_factory=list)
    vat: list[ParsedVat] = field(default_factory=list)

    @property
    def payable_ron(self) -> float | None:
        return None if self.fx_to_ron is None else round(self.payable * self.fx_to_ron, 2)


def _text(node, path: str, default: str = "") -> str:
    found = node.find(path, NS)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _num(node, path: str, default: float = 0.0) -> float:
    raw = _text(node, path)
    if not raw:
        return default
    try:
        return float(Decimal(raw.replace(",", ".")))
    except InvalidOperation:
        return default


def _date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _rate(raw: str) -> float | None:
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_invoice_xml(data: bytes) -> ParsedInvoice:
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    except etree.XMLSyntaxError as exc:
        raise NotAnInvoice(f"XML invalid: {exc}") from exc

    ns = etree.QName(root).namespace
    local = etree.QName(root).localname
    if ns == INVOICE_NS and local == "Invoice":
        is_credit_root = False
        type_code = _text(root, "cbc:InvoiceTypeCode", "380")
        line_tag, qty_tag = "cac:InvoiceLine", "cbc:InvoicedQuantity"
    elif ns == CREDIT_NS and local == "CreditNote":
        is_credit_root = True
        type_code = _text(root, "cbc:CreditNoteTypeCode", "381")
        line_tag, qty_tag = "cac:CreditNoteLine", "cbc:CreditedQuantity"
    else:
        raise NotAnInvoice(f"Root element {local!r} is not a UBL Invoice/CreditNote")

    is_credit = is_credit_root or type_code in CREDIT_TYPE_CODES
    sign = -1.0 if is_credit else 1.0

    sup = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    buy = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    if sup is None:
        raise NotAnInvoice("Missing supplier party")

    supplier_vat_id = _text(sup, "cac:PartyTaxScheme/cbc:CompanyID")
    supplier_cui = clean_cui(supplier_vat_id or _text(sup, "cac:PartyLegalEntity/cbc:CompanyID") or _text(sup, "cac:PartyIdentification/cbc:ID"))
    supplier_name = _text(sup, "cac:PartyLegalEntity/cbc:RegistrationName") or _text(sup, "cac:PartyName/cbc:Name")
    supplier_reg = _text(sup, "cac:PartyLegalEntity/cbc:CompanyID")
    if clean_cui(supplier_reg) == supplier_cui:
        supplier_reg = ""
    buyer_cui = ""
    buyer_name = ""
    if buy is not None:
        buyer_cui = clean_cui(_text(buy, "cac:PartyTaxScheme/cbc:CompanyID") or _text(buy, "cac:PartyLegalEntity/cbc:CompanyID") or _text(buy, "cac:PartyIdentification/cbc:ID"))
        buyer_name = _text(buy, "cac:PartyLegalEntity/cbc:RegistrationName") or _text(buy, "cac:PartyName/cbc:Name")

    iban = ""
    for pm in root.findall("cac:PaymentMeans", NS):
        iban = clean_iban(_text(pm, "cac:PayeeFinancialAccount/cbc:ID"))
        if iban:
            break

    currency = _text(root, "cbc:DocumentCurrencyCode", "RON").upper()

    # Tax totals: the one in document currency carries the subtotals; with a foreign currency,
    # CIUS-RO requires a second TaxTotal in RON (BT-111) which gives us the exchange rate.
    tax_doc = 0.0
    tax_ron = None
    vat: list[ParsedVat] = []
    for tt in root.findall("cac:TaxTotal", NS):
        amt_node = tt.find("cbc:TaxAmount", NS)
        if amt_node is None:
            continue
        cur = (amt_node.get("currencyID") or currency).upper()
        amt = _num(tt, "cbc:TaxAmount")
        if cur == currency:
            tax_doc = amt
            for st in tt.findall("cac:TaxSubtotal", NS):
                vat.append(ParsedVat(
                    category=_text(st, "cac:TaxCategory/cbc:ID"),
                    rate=_rate(_text(st, "cac:TaxCategory/cbc:Percent")),
                    taxable=sign * _num(st, "cbc:TaxableAmount"),
                    tax=sign * _num(st, "cbc:TaxAmount"),
                ))
        elif cur == "RON":
            tax_ron = amt

    if currency == "RON":
        fx = 1.0
    elif tax_ron is not None and tax_doc:
        fx = round(tax_ron / tax_doc, 6)
    else:
        fx = None  # cannot derive a rate (e.g. zero VAT); amount stays in document currency

    mt = root.find("cac:LegalMonetaryTotal", NS)
    line_total = _num(mt, "cbc:LineExtensionAmount") if mt is not None else 0.0
    tax_excl = _num(mt, "cbc:TaxExclusiveAmount") if mt is not None else 0.0
    tax_incl = _num(mt, "cbc:TaxInclusiveAmount") if mt is not None else 0.0
    payable = _num(mt, "cbc:PayableAmount", tax_incl) if mt is not None else tax_incl

    lines: list[ParsedLine] = []
    for ln in root.findall(line_tag, NS):
        qty = _num(ln, qty_tag)
        qnode = ln.find(qty_tag, NS)
        unit = (qnode.get("unitCode") if qnode is not None else "") or ""
        name = _text(ln, "cac:Item/cbc:Name") or _text(ln, "cac:Item/cbc:Description")
        price = _num(ln, "cac:Price/cbc:PriceAmount")
        base_q = _num(ln, "cac:Price/cbc:BaseQuantity", 1.0) or 1.0
        lines.append(ParsedLine(
            line_no=_text(ln, "cbc:ID"),
            item_name=name,
            item_norm=normalize_item_name(name),
            seller_item_id=_text(ln, "cac:Item/cac:SellersItemIdentification/cbc:ID"),
            quantity=sign * qty,
            unit_code=unit,
            unit_price=price / base_q,
            base_quantity=base_q,
            net_amount=sign * _num(ln, "cbc:LineExtensionAmount"),
            vat_category=_text(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"),
            vat_rate=_rate(_text(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")),
        ))

    number = _text(root, "cbc:ID")
    issue = _date(_text(root, "cbc:IssueDate"))
    if issue is None:
        raise NotAnInvoice("Missing IssueDate")
    notes = [n.text.strip() for n in root.findall("cbc:Note", NS) if n.text]

    return ParsedInvoice(
        invoice_key=short_hash(supplier_cui, normalize_invoice_number(number), issue.isoformat(), "C" if is_credit else "I"),
        number=number,
        type_code=type_code,
        is_credit_note=is_credit,
        issue_date=issue,
        due_date=_date(_text(root, "cbc:DueDate")) or _date(_text(root, "cac:PaymentTerms/cbc:PaymentDueDate")),
        currency=currency,
        supplier_cui=supplier_cui,
        supplier_vat_id=supplier_vat_id,
        supplier_name=supplier_name,
        supplier_reg_no=supplier_reg,
        supplier_iban=iban,
        supplier_city=_text(sup, "cac:PostalAddress/cbc:CityName"),
        buyer_cui=buyer_cui,
        buyer_name=buyer_name,
        line_total=sign * line_total,
        tax_exclusive=sign * tax_excl,
        tax_total=sign * tax_doc,
        tax_inclusive=sign * tax_incl,
        payable=sign * payable,
        fx_to_ron=fx,
        note=" | ".join(notes)[:1000],
        xml_sha256=sha256_bytes(data),
        lines=lines,
        vat=vat,
    )
