"""Synthetic RO e-Factura data for demos and tests.

Generates 18 months of supplier invoices for a fictional distributor, spanning the 1 Aug 2025
VAT change, with realistic noise (recurring monthly invoices, fuel price swings, seasonal
construction volumes, credit notes, a EUR supplier) and a known set of injected anomalies.
Every company, person and bank account is invented. Output: one ANAF-style ZIP per invoice
(``<id>.zip`` with ``<id>.xml`` + ``semnatura_<id>.xml``) and ``ground_truth.json``.
"""
from __future__ import annotations

import copy
import json
import math
import random
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .ubl_writer import SIGNATURE_STUB, InvoiceDoc, Line, Party, render
from .utils import cui_control_digit, iban_check_digits

VAT_CHANGE = date(2025, 8, 1)


def vat_rate(kind: str, d: date) -> float:
    if kind == "std":
        return 19.0 if d < VAT_CHANGE else 21.0
    if kind == "red":
        return 9.0 if d < VAT_CHANGE else 11.0
    return 0.0


@dataclass
class Item:
    key: str
    names: list[str]            # description variants the supplier uses over time
    price: float
    unit: str = "H87"
    vat: str = "std"
    qty: tuple[float, float] = (1, 10)
    seller_id: str = ""
    integer_qty: bool = True


@dataclass
class Supplier:
    key: str
    name: str
    city: str
    prefix: str
    monthly: float
    lines: tuple[int, int]
    items: list[Item]
    currency: str = "RON"
    season: str = ""            # "summer" doubles volume May-Sep
    recurring: bool = False     # one fixed invoice per month on a fixed day
    annual_increase: float = 0.0
    jitter: float = 0.005
    volatile: float = 0.0       # monthly price swing amplitude (fuel)
    start: date | None = None
    end: date | None = None
    cui: str = ""
    iban: str = ""
    bank: str = "BTRL"
    invalid_cui: bool = False
    vat_payer: bool = True
    counter: int = 0


def _make_cui(rng: random.Random) -> str:
    body = str(rng.randint(10_000_000, 49_999_999))[:8]
    return body + str(cui_control_digit(body))


def _make_iban(rng: random.Random, bank: str) -> str:
    bban = bank + "".join(rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(16))
    return "RO" + iban_check_digits("RO", bban) + bban


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    l_, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l_:
            return k
        k += 1


def _business_day(rng: random.Random, year: int, month: int) -> date:
    for _ in range(20):
        day = rng.randint(1, 28)
        d = date(year, month, day)
        if d.weekday() < 5:
            return d
    return date(year, month, 5)


def build_suppliers() -> list[Supplier]:
    S = Supplier
    I = Item
    return [
        S("betonex", "Betonex Materiale SRL", "Ploiești", "BTX", 7, (2, 6), [
            I("ciment", ["Ciment Portland CEM II/A-LL 42,5R sac 40kg"], 32.5, "H87", qty=(20, 200), seller_id="BTX-C425"),
            I("bca", ["BCA 600x250x200 mm"], 13.8, "H87", qty=(100, 800), seller_id="BTX-BCA20"),
            I("fier", ["Fier beton PC52 fi 12"], 4.95, "KGM", qty=(200, 2000), seller_id="BTX-PC12"),
            I("adeziv", ["Adeziv gresie faianta C1 25kg"], 38.0, "H87", qty=(10, 80), seller_id="BTX-AD25"),
            I("polistiren", ["Polistiren expandat EPS80 10cm"], 21.5, "MTK", qty=(50, 400), seller_id="BTX-EPS10"),
        ], season="summer", annual_increase=0.04, bank="RNCB"),
        S("granit", "Granit Trans Logistic SRL", "Cluj-Napoca", "GTL", 9, (1, 2), [
            I("tr_cluj", ["Transport marfa Bucuresti - Cluj-Napoca, camion 24t"], 3450.0, "C62", qty=(1, 2)),
            I("tr_iasi", ["Transport marfa Bucuresti - Iasi, camion 24t"], 3890.0, "C62", qty=(1, 2)),
            I("tr_local", ["Transport local Bucuresti, duba 3,5t"], 620.0, "C62", qty=(1, 4)),
            I("asteptare", ["Taxa asteptare descarcare (ora)"], 95.0, "HUR", qty=(1, 5)),
        ], annual_increase=0.03, bank="BTRL"),
        S("hartia", "Hârtia Veche Office SRL", "București", "HVO", 3, (2, 6), [
            I("a4", ["Hartie copiator A4 80g/mp, top 500 coli", "Hârtie copiator A4 80 g/mp 500 coli", "HARTIE A4 80G 500 COLI/TOP"], 24.9, qty=(10, 60)),
            I("biblioraft", ["Biblioraft plastifiat 7,5 cm", "Biblioraft 75mm plastifiat"], 9.8, qty=(10, 50)),
            I("toner", ["Toner compatibil HP 85A", "Cartus toner compatibil 85A negru"], 145.0, qty=(1, 6)),
            I("pixuri", ["Pix cu gel albastru, set 12 buc", "Set 12 pixuri gel albastre"], 36.0, qty=(1, 10)),
        ], annual_increase=0.03, bank="BRDE"),
        S("delta", "Papetăria Delta Nord SRL", "Brașov", "PDN", 1.5, (1, 3), [
            I("a4", ["Hartie xerox A4 80 g/mp top 500 coli"], 19.4, qty=(10, 80)),
            I("dosare", ["Dosar plic cu buton A4, set 10"], 18.0, qty=(1, 20)),
        ], bank="BACX"),
        S("petro", "PetroDrum Carburanți SRL", "Pitești", "PDC", 5, (1, 2), [
            I("motorina", ["Motorina standard"], 6.35, "LTR", qty=(300, 2500), integer_qty=False),
            I("benzina", ["Benzina 95"], 6.55, "LTR", qty=(50, 400), integer_qty=False),
            I("adblue", ["AdBlue vrac"], 3.1, "LTR", qty=(40, 200), integer_qty=False),
        ], volatile=0.035, jitter=0.008, bank="INGB"),
        S("ambalaje", "Ambalaje Carpați SRL", "Sibiu", "AMC", 4, (2, 5), [
            I("folie", ["Folie stretch manuala 23 microni 2,4kg"], 29.0, "H87", qty=(20, 150), seller_id="FS23"),
            I("cutie", ["Cutie carton 5 straturi 600x400x400"], 7.6, "H87", qty=(100, 1500), seller_id="CC5-640"),
            I("palet", ["Palet EUR EPAL reconditionat"], 58.0, "H87", qty=(10, 80), seller_id="PAL-EUR"),
            I("banda", ["Banda adeziva 48mm x 66m transparenta"], 4.1, "H87", qty=(36, 360), seller_id="BA48"),
        ], annual_increase=0.05, bank="RZBR"),
        S("softlink", "Softlink Servicii IT SRL", "București", "SLK", 1, (2, 2), [
            I("suport", ["Abonament suport IT lunar - pachet Business"], 4200.0, "C62", qty=(1, 1)),
            I("m365", ["Licente Microsoft 365 Business Standard (utilizator/luna)"], 61.0, "C62", qty=(38, 38)),
        ], recurring=True, bank="BTRL"),
        S("voltaris", "Voltaris Energie SRL", "București", "VOL", 1, (2, 2), [
            I("energie", ["Energie electrica activa"], 0.92, "KWH", qty=(18000, 32000)),
            I("transport_en", ["Tarif transport si distributie energie"], 0.21, "KWH", qty=(18000, 32000)),
        ], recurring=True, jitter=0.0, bank="RNCB"),
        S("curatenie", "Curățenie Profi Services SRL", "București", "CPS", 1, (1, 1), [
            I("curatenie", ["Servicii curatenie depozit si birouri - luna"], 7800.0, "C62", qty=(1, 1)),
        ], recurring=True, annual_increase=0.05, bank="BRDE"),
        S("agro", "Agro Fresh Distribuție SRL", "Buzău", "AFD", 4, (3, 7), [
            I("paine", ["Paine alba feliata 500g"], 5.2, vat="red", qty=(20, 120)),
            I("lapte", ["Lapte 1,5% grasime 1L"], 6.9, vat="red", qty=(20, 100)),
            I("fructe", ["Mere Golden kg"], 4.8, "KGM", vat="red", qty=(10, 60)),
            I("cafea", ["Cafea boabe 1kg"], 78.0, vat="std", qty=(2, 10)),
            I("apa", ["Apa plata 0,5L bax 12"], 21.0, vat="std", qty=(5, 40)),
        ], annual_increase=0.04, bank="CECE"),
        S("eurosteel", "Eurosteel Trading SRL", "Galați", "EST", 2, (1, 3), [
            I("profil", ["Profil metalic UD 30 3m"], 2.35, "H87", qty=(200, 1200), seller_id="UD30", integer_qty=True),
            I("tabla", ["Tabla zincata 0,5mm"], 5.9, "MTK", qty=(100, 900), seller_id="TZ05"),
        ], currency="EUR", bank="BTRL"),
        S("vigilent", "Pază Vigilent Grup SRL", "București", "PVG", 1, (1, 1), [
            I("paza", ["Servicii paza si monitorizare - luna"], 12600.0, "C62", qty=(1, 1)),
        ], recurring=True, annual_increase=0.06, bank="INGB"),
        S("anvelope", "Anvelope Rapid SRL", "Ilfov", "ANR", 0.5, (1, 2), [
            I("anv_camion", ["Anvelopa camion 315/70 R22.5"], 1650.0, qty=(2, 8)),
            I("montaj", ["Montaj si echilibrare roata camion"], 120.0, "C62", qty=(2, 8)),
        ], bank="BTRL"),
        S("motorex", "Service Auto Motorex SRL", "Chitila", "SAM", 2, (2, 5), [
            I("revizie", ["Revizie periodica autoutilitara"], 980.0, "C62", qty=(1, 2)),
            I("ulei", ["Ulei motor 5W30 5L"], 185.0, qty=(1, 4)),
            I("filtre", ["Set filtre (ulei, aer, combustibil)"], 340.0, qty=(1, 2)),
            I("manopera", ["Manopera mecanica (ora)"], 160.0, "HUR", qty=(1, 8)),
            I("placute", ["Placute frana punte fata"], 420.0, qty=(1, 2)),
        ], annual_increase=0.04, bank="BACX"),
        S("netcom", "Netcom Fibră SRL", "București", "NCF", 1, (2, 2), [
            I("internet", ["Abonament internet fibra 1Gbps - luna"], 450.0, "C62", qty=(1, 1)),
            I("mobil", ["Abonamente telefonie mobila (25 linii) - luna"], 1375.0, "C62", qty=(1, 1)),
        ], recurring=True, bank="RZBR"),
        S("litera", "Tipografia Litera SRL", "Craiova", "TLT", 0.7, (1, 3), [
            I("flyere", ["Flyere A5 color fata-verso 135g"], 0.32, qty=(2000, 10000)),
            I("etichete", ["Etichete autoadezive 100x50 mm, rola 1000"], 42.0, qty=(10, 60)),
        ], bank="BRDE"),
        S("ionescu", "Ionescu Mihai Andrei PFA", "București", "IMA", 1, (1, 1), [
            I("consultanta", ["Servicii consultanta fiscala si contabila - luna"], 3500.0, "C62", qty=(1, 1)),
        ], recurring=True, vat_payer=False, bank="BTRL"),
        S("pipera", "Imobiliara Pipera Park SRL", "Voluntari", "IPP", 1, (1, 1), [
            I("chirie", ["Chirie spatiu depozitare hala B2 - luna"], 38500.0, "C62", qty=(1, 1)),
        ], recurring=True, jitter=0.0, bank="INGB"),
        S("tehno", "Echipamente Industriale Tehno SRL", "Timișoara", "EIT", 1.5, (1, 4), [
            I("rulment", ["Rulment 6205-2RS"], 28.0, qty=(4, 40), seller_id="R6205"),
            I("curea", ["Curea transmisie SPA 1250"], 64.0, qty=(2, 10), seller_id="SPA1250"),
            I("baterie", ["Baterie tractiune stivuitor 48V"], 14200.0, qty=(1, 1), seller_id="BT48"),
            I("roata", ["Roata transpalet poliuretan 200mm"], 185.0, qty=(2, 8), seller_id="RT200"),
        ], bank="BTRL"),
        S("aquaserv", "Aquaserv Pure SRL", "Ploiești", "AQP", 2, (1, 2), [
            I("bidon", ["Apa plata bidon 19L"], 24.0, qty=(10, 40)),
            I("dozator", ["Chirie dozator apa - luna"], 35.0, "C62", qty=(4, 4)),
        ], annual_increase=0.03, bank="RNCB"),
        # --- suppliers that exist to carry anomalies -------------------------------------------
        S("rapid", "Materiale Rapid Construct SRL", "Giurgiu", "MRC", 0.6, (1, 3), [
            I("gresie", ["Gresie portelanata 60x60 mp"], 64.0, "MTK", qty=(20, 150)),
            I("mortar", ["Mortar zidarie M5 sac 40kg"], 17.5, qty=(20, 100)),
        ], start=date(2025, 10, 1), invalid_cui=True, bank="BTRL"),
        S("global", "Consulting Global Partners SRL", "București", "CGP", 0, (1, 1), [
            I("consult", ["Servicii consultanta management si optimizare procese"], 48000.0, "C62", qty=(1, 1)),
        ], start=date(2026, 5, 1), bank="BTRL"),
    ]


BUYER = Party(name="Nordica Distribuție SRL", cui="", city="București", street="Bd. Industriilor nr. 12",
              reg_no="J40/1234/2012", county="RO-B")


@dataclass
class Generated:
    docs: list[InvoiceDoc] = field(default_factory=list)
    truth: list[dict] = field(default_factory=list)
    buyer: Party | None = None


class Generator:
    def __init__(self, seed: int = 7, start: date = date(2025, 1, 1), months: int = 18, scale: float = 1.0):
        self.scale = scale
        self.rng = random.Random(seed)
        self.start = start
        self.months = months
        self.suppliers = {s.key: s for s in build_suppliers()}
        self.price_events: list[tuple[str, str, date, str, float]] = [
            # (supplier, item, from, kind, size) — the injected price anomalies
            ("ambalaje", "folie", date(2025, 11, 1), "jump", 0.22),
            ("betonex", "adeziv", date(2026, 2, 1), "jump", 0.18),
            ("motorex", "manopera", date(2025, 9, 1), "creep", 0.025),   # +2.5% per month
            ("hartia", "toner", date(2026, 1, 15), "jump", 0.30),
            ("tehno", "rulment", date(2026, 3, 1), "jump", 0.25),
        ]
        rng = self.rng
        self.buyer = copy.deepcopy(BUYER)
        self.buyer.cui = _make_cui(rng)
        for s in self.suppliers.values():
            s.cui = _make_cui(rng)
            if s.invalid_cui:
                s.cui = s.cui[:-1] + str((int(s.cui[-1]) + 3) % 10)
            s.iban = _make_iban(rng, s.bank)
            s.counter = rng.randint(1000, 9000)
        # one shared bank account between two unrelated suppliers
        self.suppliers["global"].iban = self.suppliers["rapid"].iban

    # ------------------------------------------------------------------ pricing
    def price(self, s: Supplier, it: Item, d: date) -> float:
        p = it.price
        if s.annual_increase and d >= date(2026, 1, 1):
            p *= 1 + s.annual_increase
        if s.volatile:
            months = (d.year - 2025) * 12 + d.month
            p *= 1 + s.volatile * math.sin(months / 2.2) + self.rng.uniform(-0.01, 0.01)
        for sk, ik, frm, kind, size in self.price_events:
            if sk == s.key and ik == it.key and d >= frm:
                if kind == "jump":
                    p *= 1 + size
                else:
                    months = (d.year - frm.year) * 12 + d.month - frm.month + 1
                    p *= (1 + size) ** months
        if s.jitter:
            p *= 1 + self.rng.uniform(-s.jitter, s.jitter)
        return round(p, 4 if p < 10 else 2)

    def _fx(self, d: date) -> float:
        return round(4.97 + 0.08 * math.sin(d.toordinal() / 40) + self.rng.uniform(-0.01, 0.01), 4)

    def _party(self, s: Supplier) -> Party:
        return Party(name=s.name, cui=s.cui, city=s.city, vat_payer=s.vat_payer, iban=s.iban,
                     street=f"Str. {s.city.split('-')[0]} nr. {sum(map(ord, s.key)) % 90 + 1}")

    def _number(self, s: Supplier) -> str:
        s.counter += self.rng.randint(3, 40)   # the supplier invoices other clients too
        return f"{s.prefix}-{s.counter}"

    def _doc(self, s: Supplier, d: date, n_lines: int | None = None, items: list[Item] | None = None) -> InvoiceDoc:
        rng = self.rng
        if items is None:
            k = n_lines or rng.randint(*s.lines)
            items = s.items if s.recurring else rng.sample(s.items, min(k, len(s.items)))
        lines = []
        for it in items:
            lo, hi = it.qty
            q = rng.randint(int(lo), int(hi)) if it.integer_qty else round(rng.uniform(lo, hi), 2)
            name = it.names[0] if len(it.names) == 1 else rng.choice(it.names)
            rate = vat_rate(it.vat, d) if s.vat_payer else 0.0
            cat = "S" if s.vat_payer else "O"
            lines.append(Line(name=name, quantity=q, unit_price=self.price(s, it, d), vat_rate=rate,
                              unit_code=it.unit, vat_category=cat, seller_item_id=it.seller_id))
        fx = self._fx(d) if s.currency != "RON" else 1.0
        return InvoiceDoc(number=self._number(s), issue_date=d, due_date=d + timedelta(days=30),
                          supplier=self._party(s), buyer=self.buyer, lines=lines, currency=s.currency, fx_to_ron=fx,
                          meta={"supplier": s.key})

    # ------------------------------------------------------------------ baseline
    def baseline(self) -> list[InvoiceDoc]:
        rng = self.rng
        docs: list[InvoiceDoc] = []
        for m in range(self.months):
            y = self.start.year + (self.start.month - 1 + m) // 12
            mo = (self.start.month - 1 + m) % 12 + 1
            first = date(y, mo, 1)
            for s in self.suppliers.values():
                if (s.start and first < s.start) or (s.end and first > s.end):
                    continue
                if s.recurring:
                    day = 3 if s.key != "voltaris" else 10
                    d = date(y, mo, day)
                    docs.append(self._doc(s, d))
                    continue
                lam = s.monthly * self.scale * (1.8 if s.season == "summer" and 5 <= mo <= 9 else 1.0)
                for _ in range(_poisson(rng, lam)):
                    docs.append(self._doc(s, _business_day(rng, y, mo)))
        # returns: ~2% of goods invoices get a partial credit note
        for d in list(docs):
            if d.supplier.name.startswith(("Betonex", "Ambalaje", "Agro", "Hârtia")) and rng.random() < 0.02:
                ln = copy.deepcopy(d.lines[0])
                ln.quantity = max(1, round(ln.quantity * 0.2))
                cn = InvoiceDoc(number=self._number(self.suppliers[d.meta["supplier"]]),
                                issue_date=d.issue_date + timedelta(days=rng.randint(3, 20)),
                                supplier=d.supplier, buyer=self.buyer, lines=[ln], credit_note=True,
                                note=f"Retur marfa aferent facturii {d.number}", meta=dict(d.meta))
                docs.append(cn)
        return docs

    # ------------------------------------------------------------------ anomalies
    def inject(self, docs: list[InvoiceDoc]) -> list[dict]:
        rng = self.rng
        truth: list[dict] = []

        def pick(sup: str, after: date | None = None, before: date | None = None, min_lines: int = 1) -> InvoiceDoc:
            cands = [d for d in docs if d.meta.get("supplier") == sup and not d.credit_note
                     and len(d.lines) >= min_lines and not d.meta.get("anomaly")
                     and (after is None or d.issue_date >= after) and (before is None or d.issue_date <= before)]
            if not cands:  # sparse supplier: create an invoice in the window
                lo = after or self.start
                doc = self._doc(self.suppliers[sup], lo + timedelta(days=rng.randint(1, 20)), n_lines=min_lines + 1)
                docs.append(doc)
                return doc
            return rng.choice(cands)

        def add_truth(check: str, rule: str, doc: InvoiceDoc, **extra):
            truth.append({"check": check, "rule": rule, "supplier": doc.supplier.name, "supplier_cui": doc.supplier.cui,
                          "number": doc.number, "issue_date": doc.issue_date.isoformat(), **extra})

        # 1) near-duplicates -------------------------------------------------------------------
        def dup(sup: str, number_fn, days: int, reorder: bool = False, after: date = date(2025, 2, 1)):
            orig = pick(sup, after=after, before=date(2026, 5, 31))
            copy_ = copy.deepcopy(orig)
            copy_.number = number_fn(orig.number)
            copy_.issue_date = orig.issue_date + timedelta(days=days)
            copy_.due_date = copy_.issue_date + timedelta(days=30)
            if reorder:
                copy_.lines = list(reversed(copy_.lines))
            copy_.meta["anomaly"] = orig.meta["anomaly"] = "near_duplicate"
            docs.append(copy_)
            add_truth("near_duplicate", "near_duplicate", copy_, original=orig.number,
                      original_date=orig.issue_date.isoformat(), amount=copy_.gross_total)

        def transpose(n: str) -> str:
            p, num = n.split("-")
            return f"{p}-{num[:-2]}{num[-1]}{num[-2]}" if num[-1] != num[-2] else f"{p}-{num}1"

        dup("betonex", transpose, 0)
        dup("granit", lambda n: n, 3)
        dup("ambalaje", lambda n: f"{n.split('-')[0]}-{int(n.split('-')[1]) + 1}", 5)
        dup("agro", lambda n: f"AF{rng.randint(100000, 999999)}", 2)
        dup("motorex", lambda n: n + "/1", 0)
        dup("eurosteel", lambda n: n.replace("-", "/"), 9)
        dup("tehno", lambda n: f"{n.split('-')[0]}-{int(n.split('-')[1]) + 7}", 1, reorder=True)
        dup("hartia", lambda n: n + "A", 4)

        # legitimate reissue: original, full credit note, corrected invoice with a new number
        orig = pick("litera", after=date(2025, 3, 1))
        cn = copy.deepcopy(orig)
        cn.credit_note, cn.number = True, self._number(self.suppliers["litera"])
        cn.issue_date = orig.issue_date + timedelta(days=2)
        cn.note = f"Stornare integrala factura {orig.number} - date client eronate"
        re_ = copy.deepcopy(orig)
        re_.number, re_.issue_date = self._number(self.suppliers["litera"]), orig.issue_date + timedelta(days=2)
        re_.meta["anomaly"] = orig.meta["anomaly"] = "legit_reissue"
        docs.extend([cn, re_])
        truth.append({"check": "near_duplicate", "rule": "legit_reissue", "supplier": orig.supplier.name,
                      "supplier_cui": orig.supplier.cui, "number": re_.number, "original": orig.number,
                      "issue_date": re_.issue_date.isoformat(), "expected": "low severity or not flagged"})

        # 2) price increases (generated through price_events) ------------------------------------
        for sk, ik, frm, kind, size in self.price_events:
            s = self.suppliers[sk]
            item = next(i for i in s.items if i.key == ik)
            truth.append({"check": "price_increase", "rule": kind, "supplier": s.name, "supplier_cui": s.cui,
                          "item": item.names[0], "item_variants": item.names, "from": frm.isoformat(),
                          "size_pct": round(size * 100, 1)})
        # cross-supplier gap: Hârtia Veche charges ~28% more than Papetăria Delta for A4 paper
        truth.append({"check": "price_increase", "rule": "cross_supplier", "supplier": self.suppliers["hartia"].name,
                      "supplier_cui": self.suppliers["hartia"].cui, "item": "Hartie copiator A4 80g/mp, top 500 coli",
                      "cheaper_supplier": self.suppliers["delta"].name})

        # 3) outliers ----------------------------------------------------------------------------
        d = pick("betonex", after=date(2025, 4, 1), min_lines=2)       # misplaced decimal in quantity
        big = max(d.lines, key=lambda ln: ln.net)
        big.quantity *= 10
        d.meta["anomaly"] = "outlier"
        add_truth("outlier", "decimal_shift", d, line=big.name)
        d = pick("ambalaje", after=date(2025, 6, 1), before=date(2025, 10, 15))  # misplaced decimal in price
        d.lines[0].unit_price = round(d.lines[0].unit_price * 10, 2)
        d.meta["anomaly"] = "outlier"
        add_truth("outlier", "decimal_shift", d, line=d.lines[0].name)
        s = self.suppliers["motorex"]                                     # one very large invoice
        d = self._doc(s, date(2026, 4, 14), items=s.items)
        for ln in d.lines:
            ln.quantity *= 6
        d.meta["anomaly"] = "outlier"
        docs.append(d)
        add_truth("outlier", "amount", d)
        s = self.suppliers["granit"]
        d = self._doc(s, date(2025, 12, 9), items=[s.items[0]])
        d.lines[0].quantity = 11
        d.meta["anomaly"] = "outlier"
        docs.append(d)
        add_truth("outlier", "amount", d)

        # 4) VAT -------------------------------------------------------------------------------
        for sup, when in (("hartia", date(2025, 10, 1)), ("litera", date(2026, 1, 1)), ("anvelope", date(2026, 2, 1))):
            d = pick(sup, after=when)
            for ln in d.lines:
                ln.vat_rate = 19.0
            d.meta["anomaly"] = "vat"
            add_truth("vat", "rate_not_valid_for_date", d)
        for sup in ("agro", "betonex"):
            d = pick(sup, after=date(2025, 3, 1))
            d.tax_error = rng.choice([118.40, -236.00, 90.15])
            d.meta["anomaly"] = "vat"
            add_truth("vat", "arithmetic", d, error=d.tax_error)
        d = pick("motorex", after=date(2025, 9, 1))
        d.lines[0].vat_rate = 11.0
        d.meta["anomaly"] = "vat"
        add_truth("vat", "rate_deviation", d, line=d.lines[0].name)
        d = pick("agro", after=date(2025, 9, 1), min_lines=3)
        red = [ln for ln in d.lines if ln.vat_rate == 11.0]
        if red:
            red[0].vat_rate = 21.0
            d.meta["anomaly"] = "vat"
            add_truth("vat", "rate_deviation", d, line=red[0].name)
        d = pick("eurosteel", after=date(2025, 9, 1))
        for ln in d.lines:
            ln.vat_category = "AE"
        d.meta["anomaly"] = "vat"
        add_truth("vat", "reverse_charge_with_tax", d)

        # 5) supplier master data ----------------------------------------------------------------
        new_iban = _make_iban(rng, "BACX")
        petro = self.suppliers["petro"]
        first_new = None
        for d in sorted((x for x in docs if x.meta.get("supplier") == "petro"), key=lambda x: x.issue_date):
            if d.issue_date >= date(2026, 3, 1):
                d.iban = new_iban
                first_new = first_new or d
        truth.append({"check": "supplier", "rule": "iban_changed", "supplier": petro.name, "supplier_cui": petro.cui,
                      "number": first_new.number, "issue_date": first_new.issue_date.isoformat(), "new_iban": new_iban})
        d = pick("betonex", after=date(2026, 2, 1), before=date(2026, 2, 28))
        d.iban = _make_iban(rng, "PIRB")
        d.meta["anomaly"] = "supplier"
        add_truth("supplier", "iban_one_off", d, iban=d.iban)
        g = self.suppliers["global"]
        d = self._doc(g, date(2026, 5, 20))
        docs.append(d)
        add_truth("supplier", "new_supplier", d, amount=d.gross_total)
        add_truth("supplier", "shared_iban", d, other_supplier=self.suppliers["rapid"].name)
        r = self.suppliers["rapid"]
        truth.append({"check": "supplier", "rule": "invalid_cui", "supplier": r.name, "supplier_cui": r.cui})
        truth.append({"check": "supplier", "rule": "new_supplier", "supplier": r.name, "supplier_cui": r.cui,
                      "note": "first invoices from Oct 2025"})
        return truth

    def generate(self) -> Generated:
        docs = self.baseline()
        truth = self.inject(docs)
        docs.sort(key=lambda d: (d.issue_date, d.number))
        return Generated(docs=docs, truth=truth, buyer=self.buyer)


def write_dataset(out_dir: str | Path, seed: int = 7, months: int = 18, scale: float = 1.0) -> dict:
    """Generate the dataset and write ANAF-style ZIPs plus ground_truth.json. Returns a summary."""
    out = Path(out_dir)
    zips = out / "spv_downloads"
    zips.mkdir(parents=True, exist_ok=True)
    gen = Generator(seed=seed, months=months, scale=scale).generate()
    base_id = 4_100_000_000 + seed * 1_000_000
    for i, doc in enumerate(gen.docs):
        anaf_id = str(base_id + i * 7)
        with zipfile.ZipFile(zips / f"{anaf_id}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{anaf_id}.xml", render(doc))
            zf.writestr(f"semnatura_{anaf_id}.xml", SIGNATURE_STUB)
    summary = {
        "buyer": gen.buyer.name,
        "buyer_cui": gen.buyer.cui,
        "invoices": len(gen.docs),
        "credit_notes": sum(1 for d in gen.docs if d.credit_note),
        "suppliers": len({d.supplier.cui for d in gen.docs}),
        "from": gen.docs[0].issue_date.isoformat(),
        "to": gen.docs[-1].issue_date.isoformat(),
        "anomalies": len(gen.truth),
        "note": "Synthetic data: all companies, people and bank accounts are invented.",
    }
    (out / "ground_truth.json").write_text(
        json.dumps({"summary": summary, "anomalies": gen.truth}, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
