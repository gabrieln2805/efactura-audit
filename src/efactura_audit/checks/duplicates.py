"""Near-duplicate invoices: same supplier, same total and same lines, with a changed number or date.

ANAF rejects exact duplicates since 2024, so what gets through is the same invoice re-sent with
a new number (``FV-1023`` -> ``FV-1023A``, ``FV-1032``) or a new date. Legitimate look-alikes are
common too — monthly subscriptions, repeat transport routes, an invoice cancelled by a credit note
and reissued — so those patterns lower the severity instead of being flagged as duplicates.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from ..utils import normalize_invoice_number
from .base import AuditContext, lei, make_flag


def number_relation(a: str, b: str) -> str:
    na, nb = normalize_invoice_number(a), normalize_invoice_number(b)
    if na == nb:
        return "same"
    if na and nb and (na.startswith(nb) or nb.startswith(na) or na.endswith(nb) or nb.endswith(na)):
        return "suffix"
    if len(na) == len(nb):
        diff = [i for i in range(len(na)) if na[i] != nb[i]]
        if len(diff) == 2 and diff[1] == diff[0] + 1 and na[diff[0]] == nb[diff[1]] and na[diff[1]] == nb[diff[0]]:
            return "transposed"
    da, db = "".join(filter(str.isdigit, na)), "".join(filter(str.isdigit, nb))
    pa, pb = "".join(filter(str.isalpha, na)), "".join(filter(str.isalpha, nb))
    if da and db and pa == pb and abs(int(da[-12:]) - int(db[-12:])) <= 1:
        return "adjacent"
    return "different"


def _fingerprint(lines: pd.DataFrame) -> Counter:
    return Counter(
        (str(g), round(abs(float(q)), 3), round(abs(float(p)), 2))
        for g, q, p in zip(lines["item_group"], lines["quantity"], lines["unit_price"])
    )


def _similarity(a: Counter, b: Counter) -> float:
    if not a and not b:
        return 1.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


def run(ctx: AuditContext) -> list[dict]:
    cfg = ctx.cfg("duplicates")
    window = int(cfg.get("window_days", 120))
    tol_ron = float(cfg.get("amount_tolerance_ron", 0.05))
    tol_pct = float(cfg.get("amount_tolerance_pct", 0.0)) / 100
    min_sim = float(cfg.get("min_line_similarity", 0.85))
    min_amt = float(cfg.get("min_amount_ron", 50))
    small_amt = float(cfg.get("small_amount_ron", 250))

    inv = ctx.invoices
    fps = {k: _fingerprint(g) for k, g in ctx.lines.groupby("invoice_key")}
    credits = inv[inv["is_credit_note"]]
    flags: list[dict] = []

    for cui, part in inv[~inv["is_credit_note"] & (inv["spend_ron"].abs() >= min_amt)].groupby("supplier_cui"):
        part = part.sort_values("spend_ron").reset_index(drop=True)
        # how often each exact (amount, lines) pattern recurs for this supplier — routine billing
        pattern_counts = Counter((round(a, 2), frozenset(fps.get(k, Counter()).items()))
                                 for a, k in zip(part["spend_ron"], part["invoice_key"]))
        amts = part["spend_ron"].to_numpy()
        n = len(part)
        for i in range(n):
            j = i + 1
            limit = amts[i] + max(tol_ron, abs(amts[i]) * tol_pct)
            while j < n and amts[j] <= limit:
                a, b = part.iloc[i], part.iloc[j]
                j += 1
                if a["currency"] != b["currency"]:
                    continue
                gap = abs((b["issue_date"] - a["issue_date"]).days)
                if gap > window:
                    continue
                sim = _similarity(fps.get(a["invoice_key"], Counter()), fps.get(b["invoice_key"], Counter()))
                if sim < min_sim:
                    continue
                rel = number_relation(a["number"], b["number"])
                if abs(a["spend_ron"]) < small_amt and rel == "different":
                    continue   # small repeat purchases: only flag when the numbers also look related
                first, second = (a, b) if (a["issue_date"], a["number"]) <= (b["issue_date"], b["number"]) else (b, a)
                if rel == "same":
                    rule, sev, score = "same_number_new_date", "high", 0.95
                elif gap == 0:
                    rule, sev, score = "same_date_new_number", "high", 0.9
                elif gap <= 14:
                    rule = "close_dates"
                    sev, score = ("high", 0.85) if rel in {"suffix", "transposed", "adjacent"} else ("medium", 0.7)
                elif rel in {"suffix", "transposed"}:
                    rule, sev, score = "similar_number", "medium", 0.65
                else:
                    continue
                notes_en, notes_ro = [], []
                pattern = (round(a["spend_ron"], 2), frozenset(fps.get(a["invoice_key"], Counter()).items()))
                if pattern_counts[pattern] >= 3 and rel != "same":
                    if gap > 14:
                        continue   # routine billing, weeks apart: not worth a flag
                    sev, score = "low", score * 0.5
                    notes_en.append(f"This supplier billed the same amount and lines {pattern_counts[pattern]} times; may be routine.")
                    notes_ro.append(f"Furnizorul a facturat aceeași sumă și aceleași linii de {pattern_counts[pattern]} ori; poate fi o facturare recurentă.")
                cn = credits[(credits["supplier_cui"] == cui)
                             & ((credits["spend_ron"].abs() - abs(first["spend_ron"])).abs() <= max(tol_ron, abs(first["spend_ron"]) * 0.001))
                             & (credits["issue_date"] >= first["issue_date"] - pd.Timedelta(days=5))
                             & (credits["issue_date"] <= second["issue_date"] + pd.Timedelta(days=60))]
                if not cn.empty:
                    sev, score = "low", score * 0.4
                    rule += "_after_credit_note"
                    notes_en.append(f"Credit note {cn.iloc[0]['number']} cancels the same amount: likely a cancelled and reissued invoice.")
                    notes_ro.append(f"Nota de credit {cn.iloc[0]['number']} stornează aceeași sumă: probabil o factură anulată și reemisă.")
                amount = float(second["spend_ron"])
                name = second["supplier_name"]
                flags.append(make_flag(
                    check="near_duplicate", rule=rule, severity=sev, score=score * (0.8 + 0.2 * sim),
                    supplier_cui=cui, supplier_name=name,
                    invoice_keys=[first["invoice_key"], second["invoice_key"]],
                    invoice_numbers=[first["number"], second["number"]],
                    issue_date=second["issue_date"], amount_at_risk=amount if sev != "low" else 0.0,
                    title_en=f"Invoice {second['number']} matches {first['number']} ({lei(amount)}, {gap} days apart)",
                    title_ro=f"Factura {second['number']} seamănă cu {first['number']} ({lei(amount, 'ro')}, la {gap} zile distanță)",
                    evidence={
                        "first": {"number": first["number"], "date": str(first["issue_date"].date()), "amount_ron": round(float(first["spend_ron"]), 2), "anaf_id": first["anaf_id"]},
                        "second": {"number": second["number"], "date": str(second["issue_date"].date()), "amount_ron": round(float(second["spend_ron"]), 2), "anaf_id": second["anaf_id"]},
                        "days_apart": gap,
                        "number_relation": rel,
                        "line_similarity": round(sim, 3),
                        "notes_en": notes_en,
                        "notes_ro": notes_ro,
                        "what_to_check_en": "Confirm with the supplier whether both invoices are for separate deliveries before paying the second.",
                        "what_to_check_ro": "Confirmați cu furnizorul dacă ambele facturi corespund unor livrări distincte înainte de a o plăti pe a doua.",
                    },
                ))
    return flags
