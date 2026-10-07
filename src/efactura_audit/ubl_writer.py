"""Write CIUS-RO style UBL invoices (used by the synthetic generator and tests)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from xml.sax.saxutils import escape

CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1"


@dataclass
class Party:
    name: str
    cui: str               # without RO
    vat_payer: bool = True
    reg_no: str = ""
    city: str = "București"
    county: str = "RO-B"
    street: str = "Str. Exemplu nr. 1"
    iban: str = ""


@dataclass
class Line:
    name: str
    quantity: float
    unit_price: float
    vat_rate: float
    unit_code: str = "H87"
    vat_category: str = "S"
    seller_item_id: str = ""

    @property
    def net(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class InvoiceDoc:
    number: str
    issue_date: date
    supplier: Party
    buyer: Party
    lines: list[Line]
    due_date: date | None = None
    currency: str = "RON"
    fx_to_ron: float = 1.0
    credit_note: bool = False
    iban: str | None = None          # override supplier IBAN on this invoice
    tax_error: float = 0.0           # add to the stated VAT (to simulate an arithmetic mismatch)
    note: str = ""
    meta: dict = field(default_factory=dict)

    def vat_groups(self) -> list[tuple[str, float, float, float]]:
        groups: dict[tuple[str, float], float] = {}
        for ln in self.lines:
            key = (ln.vat_category, ln.vat_rate)
            groups[key] = round(groups.get(key, 0.0) + ln.net, 2)
        out = []
        for (cat, rate), taxable in sorted(groups.items()):
            tax = 0.0 if cat in {"AE", "E", "Z", "O", "K", "G"} and rate == 0 else round(taxable * rate / 100, 2)
            out.append((cat, rate, taxable, tax))
        if self.tax_error and out:
            cat, rate, taxable, tax = out[0]
            out[0] = (cat, rate, taxable, round(tax + self.tax_error, 2))
        return out

    @property
    def net_total(self) -> float:
        return round(sum(ln.net for ln in self.lines), 2)

    @property
    def tax_total(self) -> float:
        return round(sum(g[3] for g in self.vat_groups()), 2)

    @property
    def gross_total(self) -> float:
        return round(self.net_total + self.tax_total, 2)


def _amt(v: float) -> str:
    return f"{v:.2f}"


def _party_xml(p: Party, with_bank: bool = False) -> str:
    vat_id = f"RO{p.cui}" if p.vat_payer else p.cui
    reg = f"<cbc:CompanyID>{escape(p.reg_no)}</cbc:CompanyID>" if p.reg_no else f"<cbc:CompanyID>{p.cui}</cbc:CompanyID>"
    return f"""<cac:Party>
      <cac:PostalAddress>
        <cbc:StreetName>{escape(p.street)}</cbc:StreetName>
        <cbc:CityName>{escape(p.city)}</cbc:CityName>
        <cbc:CountrySubentity>{p.county}</cbc:CountrySubentity>
        <cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{vat_id}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{escape(p.name)}</cbc:RegistrationName>
        {reg}
      </cac:PartyLegalEntity>
    </cac:Party>"""


def render(doc: InvoiceDoc) -> bytes:
    root = "CreditNote" if doc.credit_note else "Invoice"
    ns = f"urn:oasis:names:specification:ubl:schema:xsd:{root}-2"
    type_tag = "cbc:CreditNoteTypeCode" if doc.credit_note else "cbc:InvoiceTypeCode"
    type_code = "381" if doc.credit_note else "380"
    line_tag = "cac:CreditNoteLine" if doc.credit_note else "cac:InvoiceLine"
    qty_tag = "cbc:CreditedQuantity" if doc.credit_note else "cbc:InvoicedQuantity"
    cur = doc.currency
    iban = doc.iban if doc.iban is not None else doc.supplier.iban

    groups = doc.vat_groups()
    subtotals = "\n".join(
        f"""<cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{cur}">{_amt(t)}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{cur}">{_amt(x)}</cbc:TaxAmount>
        <cac:TaxCategory><cbc:ID>{c}</cbc:ID><cbc:Percent>{r:.2f}</cbc:Percent>
          {'<cbc:TaxExemptionReasonCode>VATEX-EU-AE</cbc:TaxExemptionReasonCode>' if c == 'AE' else ''}
          <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
      </cac:TaxSubtotal>"""
        for c, r, t, x in groups
    )
    ron_tax = ""
    tax_cur = ""
    if cur != "RON":
        tax_cur = "<cbc:TaxCurrencyCode>RON</cbc:TaxCurrencyCode>"
        ron_tax = f"""<cac:TaxTotal><cbc:TaxAmount currencyID="RON">{_amt(doc.tax_total * doc.fx_to_ron)}</cbc:TaxAmount></cac:TaxTotal>"""

    lines_xml = "\n".join(
        f"""<{line_tag}>
    <cbc:ID>{i}</cbc:ID>
    <{qty_tag} unitCode="{ln.unit_code}">{ln.quantity:.3f}</{qty_tag}>
    <cbc:LineExtensionAmount currencyID="{cur}">{_amt(ln.net)}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{escape(ln.name)}</cbc:Name>
      {f'<cac:SellersItemIdentification><cbc:ID>{escape(ln.seller_item_id)}</cbc:ID></cac:SellersItemIdentification>' if ln.seller_item_id else ''}
      <cac:ClassifiedTaxCategory><cbc:ID>{ln.vat_category}</cbc:ID><cbc:Percent>{ln.vat_rate:.2f}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="{cur}">{ln.unit_price:.4f}</cbc:PriceAmount></cac:Price>
  </{line_tag}>"""
        for i, ln in enumerate(doc.lines, 1)
    )
    due = f"<cbc:DueDate>{doc.due_date.isoformat()}</cbc:DueDate>" if doc.due_date and not doc.credit_note else ""
    note = f"<cbc:Note>{escape(doc.note)}</cbc:Note>" if doc.note else ""
    payment = ""
    if iban:
        payment = f"""<cac:PaymentMeans><cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
    <cac:PayeeFinancialAccount><cbc:ID>{iban}</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>"""
    if doc.credit_note:
        due_block = ""
    else:
        due_block = due

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<{root} xmlns="{ns}"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>{CUSTOMIZATION}</cbc:CustomizationID>
  <cbc:ID>{escape(doc.number)}</cbc:ID>
  <cbc:IssueDate>{doc.issue_date.isoformat()}</cbc:IssueDate>
  {due_block}
  <{type_tag}>{type_code}</{type_tag}>
  {note}
  <cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>
  {tax_cur}
  <cac:AccountingSupplierParty>{_party_xml(doc.supplier)}</cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>{_party_xml(doc.buyer)}</cac:AccountingCustomerParty>
  {payment}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{cur}">{_amt(doc.tax_total)}</cbc:TaxAmount>
    {subtotals}
  </cac:TaxTotal>
  {ron_tax}
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{cur}">{_amt(doc.net_total)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{cur}">{_amt(doc.net_total)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{cur}">{_amt(doc.gross_total)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{cur}">{_amt(doc.gross_total)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  {lines_xml}
</{root}>
"""
    return xml.encode("utf-8")


SIGNATURE_STUB = b"""<?xml version="1.0" encoding="UTF-8"?>
<DetachedSignature xmlns="http://www.w3.org/2000/09/xmldsig#"><!-- synthetic: not a real ANAF signature --></DetachedSignature>
"""
