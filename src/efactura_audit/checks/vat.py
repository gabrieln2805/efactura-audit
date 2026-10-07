"""VAT patterns: rules plus deviation from each item's own history.

Rules
- rate_not_valid_for_date: a standard-category rate outside the rates in force on the issue date
  (19/9/5 until 31 Jul 2025, 21/11 from 1 Aug 2025 — Law 141/2025). Transitional cases exist, so
  rates close to the change date are reported with low severity.
- arithmetic: stated VAT differs from taxable amount x rate, or totals do not add up.
- reverse_charge_with_tax: category AE (taxare inversă) carrying VAT.
- category_rate_mismatch: category S at 0%, or exempt/zero categories with a positive rate.
- rate_deviation: an item billed in a different VAT class than it usually is (e.g. 11% instead of 21%).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import pandas as pd

from .base import AuditContext, lei, make_flag

ZERO_CATS = {"Z", "E", "AE", "K", "G", "O"}   # also in transform/models/intermediate/int_vat_subtotals.sql
CLASS_RO = {"standard": "cotă standard", "reduced": "cotă redusă", "reduced_5": "cotă redusă 5%", "zero": "cotă zero",
            "unknown": "necunoscută"}


def _periods(ctx: AuditContext) -> list[tuple[date, date, set[float]]]:
    out = []
    for p in ctx.cfg("vat").get("periods", []):
        out.append((date.fromisoformat(str(p["start"])), date.fromisoformat(str(p["end"])), {float(r) for r in p["rates"]}))
    return out


def rate_class(rate: float | None, d: date) -> str:
    if rate is None or pd.isna(rate):
        return "unknown"
    r = round(float(rate), 2)
    if r == 0:
        return "zero"
    if r in (19.0, 21.0, 20.0, 24.0):
        return "standard"
    if r in (9.0, 11.0):
        return "reduced"
    if r == 5.0:
        return "reduced_5"
    return f"other_{r:g}"


def run(ctx: AuditContext) -> list[dict]:
    cfg = ctx.cfg("vat")
    tol = float(cfg.get("arithmetic_tolerance_ron", 1.0))
    min_hist = int(cfg.get("rate_deviation_min_history", 4))
    periods = _periods(ctx)
    change_dates = sorted({s for s, _, _ in periods})[1:]
    inv = ctx.invoices.set_index("invoice_key")
    findings: dict[tuple[str, str], list[dict]] = defaultdict(list)   # (invoice_key, rule) -> details

    # --- line-level rules ------------------------------------------------------------------
    ln = ctx.lines.copy()
    ln["d"] = ln["issue_date"].dt.date
    for row in ln.itertuples(index=False):
        cat = (row.vat_category or "").upper()
        rate = row.vat_rate
        if cat == "S" and rate is not None and not pd.isna(rate):
            valid = next((rates for s, e, rates in periods if s <= row.d <= e), None)
            if valid is not None and float(rate) not in valid:
                findings[(row.invoice_key, "rate_not_valid_for_date")].append(
                    {"line": row.item_name, "rate": float(rate), "valid_rates": sorted(valid)})
            if float(rate) == 0:
                findings[(row.invoice_key, "category_rate_mismatch")].append({"line": row.item_name, "category": cat, "rate": 0.0})
        if cat == "AE" and rate and float(rate) > 0:
            findings[(row.invoice_key, "reverse_charge_with_tax")].append({"line": row.item_name, "rate": float(rate)})
        elif cat in ZERO_CATS - {"AE"} and rate and float(rate) > 0:
            findings[(row.invoice_key, "category_rate_mismatch")].append({"line": row.item_name, "category": cat, "rate": float(rate)})

    # --- item history: usual VAT class ----------------------------------------------------------
    ln["vclass"] = [rate_class(r, d) for r, d in zip(ln["vat_rate"], ln["d"])]
    for group, g in ln[~ln["is_credit_note"]].groupby("item_group"):
        if len(g) < min_hist + 1:
            continue
        counts = g["vclass"].value_counts()
        usual, share = counts.index[0], counts.iloc[0] / len(g)
        if share < 0.8:
            continue
        for row in g[g["vclass"] != usual].itertuples(index=False):
            findings[(row.invoice_key, "rate_deviation")].append(
                {"line": row.item_name, "rate": float(row.vat_rate) if row.vat_rate is not None else None,
                 "usual_class": usual, "this_class": row.vclass, "history_lines": int(len(g)), "usual_share": round(float(share), 2)})

    # --- arithmetic: differences come from int_vat_subtotals / int_invoice_vat_totals ----------
    v = ctx.ref("int_vat_subtotals", order_by="invoice_key, category, rate")
    totals = ctx.ref("int_invoice_vat_totals").set_index("invoice_key")
    bad = ~v["not_checkable"] & (v["difference_ron"] > tol)
    total_bad = totals["subtotal_difference_ron"] > tol
    gross_bad = totals["gross_difference_ron"] > tol
    for key in set(v.loc[bad, "invoice_key"]) | set(totals.index[total_bad | gross_bad]):
        t = totals.loc[key]
        problems = [
            {"category": r.category, "rate": float(r.rate), "taxable": r.taxable, "stated_vat": r.tax,
             "expected_vat": r.expected_tax, "difference": round(r.tax - r.expected_tax, 2)}
            for r in v[(v["invoice_key"] == key) & bad].itertuples(index=False)
        ]
        if total_bad[key]:
            problems.append({"stated_total_vat": t["tax_total"], "sum_of_subtotals": round(float(t["subtotal_tax"]), 2),
                             "difference": round(float(t["tax_total"] - t["subtotal_tax"]), 2)})
        if gross_bad[key]:
            problems.append({"net": t["tax_exclusive"], "vat": t["tax_total"], "gross": t["tax_inclusive"],
                             "difference": round(float(t["tax_inclusive"] - t["tax_exclusive"] - t["tax_total"]), 2)})
        findings[(key, "arithmetic")].extend(problems)

    # --- build flags (one per invoice and rule) ---------------------------------------------------
    flags = []
    for (key, rule), details in findings.items():
        if key not in inv.index:
            continue
        head = inv.loc[key]
        d = head["issue_date"].date()
        fx = head["fx_to_ron"] if pd.notna(head["fx_to_ron"]) else 1.0
        at_risk = None
        notes_en, notes_ro = [], []
        if rule == "rate_not_valid_for_date":
            near_change = any(0 <= (d - c).days <= 60 for c in change_dates)
            rates = sorted({x["rate"] for x in details})
            if near_change or rates == [9.0]:
                sev = "low"
                notes_en.append("Close to a rate change or a rate with transitional rules (e.g. 9% for housing): may be legitimate.")
                notes_ro.append("Aproape de o schimbare de cotă sau cotă cu regim tranzitoriu (ex. 9% locuințe): poate fi legitim.")
            else:
                sev = "medium"
            title_en = f"Invoice {head['number']}: VAT rate {', '.join(f'{r:g}%' for r in rates)} not in force on {d}"
            title_ro = f"Factura {head['number']}: cota TVA {', '.join(f'{r:g}%' for r in rates)} nu era în vigoare la {d}"
            score = 0.6
        elif rule == "arithmetic":
            at_risk = max(abs(x.get("difference", 0)) for x in details) * fx
            sev = "high" if (at_risk or 0) >= 50 else "medium"
            title_en = f"Invoice {head['number']}: VAT does not add up ({lei(at_risk)} difference)"
            title_ro = f"Factura {head['number']}: TVA-ul nu se verifică (diferență {lei(at_risk, 'ro')})"
            score = 0.85
        elif rule == "reverse_charge_with_tax":
            sev, score = "high", 0.85
            at_risk = abs(float(head["tax_total"])) * fx
            title_en = f"Invoice {head['number']}: reverse charge (AE) lines carry VAT"
            title_ro = f"Factura {head['number']}: linii cu taxare inversă (AE) au TVA"
        elif rule == "category_rate_mismatch":
            sev, score = "medium", 0.6
            title_en = f"Invoice {head['number']}: VAT category and rate do not match"
            title_ro = f"Factura {head['number']}: categoria și cota TVA nu corespund"
        else:  # rate_deviation
            sev, score = "medium", 0.55
            x = details[0]
            title_en = f"Invoice {head['number']}: {x['line']} billed at {x['rate']:g}% ({x['this_class']}), usually {x['usual_class']}"
            title_ro = (f"Factura {head['number']}: {x['line']} facturat cu {x['rate']:g}% "
                        f"({CLASS_RO.get(x['this_class'], x['this_class'])}), de obicei {CLASS_RO.get(x['usual_class'], x['usual_class'])}")
        flags.append(make_flag(
            check="vat", rule=rule, severity=sev, score=score, supplier_cui=head["supplier_cui"],
            supplier_name=head["supplier_name"], invoice_keys=[key], invoice_numbers=[head["number"]],
            issue_date=head["issue_date"], amount_at_risk=at_risk, title_en=title_en, title_ro=title_ro,
            evidence={
                "details": details[:20],
                "invoice_vat_total": float(head["tax_total"]),
                "currency": head["currency"],
                "notes_en": notes_en,
                "notes_ro": notes_ro,
                "what_to_check_en": "Ask the supplier to confirm the VAT treatment; a corrected invoice may be needed for VAT deduction.",
                "what_to_check_ro": "Cereți furnizorului confirmarea tratamentului TVA; poate fi necesară o factură corectată pentru deducere.",
            },
        ))
    return flags
