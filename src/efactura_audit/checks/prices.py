"""Supplier price increases.

Per supplier and item group, each line's unit price (in RON) is compared with that item's own
history over the lookback window. A line is flagged when it is well above the historical median
*and* above the historical (outlier-trimmed) maximum, so ordinary noise and one-off list-price
updates stay quiet. Consecutive increases on the same item are folded into one flag whose
evidence lists every affected invoice and the extra cost versus the old price.

A second rule benchmarks the same product across suppliers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import AuditContext, lei, make_flag, pct


def _severity(inc_pct: float, extra: float) -> str:
    if inc_pct >= 20 or extra >= 5000:
        return "high"
    if inc_pct >= 10 or extra >= 1000:
        return "medium"
    return "low"


def run(ctx: AuditContext) -> list[dict]:
    cfg = ctx.cfg("prices")
    min_hist = int(cfg.get("min_history", 3))
    thr = float(cfg.get("increase_threshold_pct", 8.0)) / 100
    tol = float(cfg.get("above_max_tolerance_pct", 2.0)) / 100
    lookback = pd.Timedelta(days=int(cfg.get("lookback_days", 365)))

    ln = ctx.lines
    ln = ln[(~ln["is_credit_note"]) & (ln["quantity"] > 0) & ln["price"].notna() & (ln["price"] > 0)]
    flags: list[dict] = []

    for group, g in ln.groupby("item_group"):
        if len(g) <= min_hist:
            continue
        g = g.sort_values(["issue_date", "invoice_key"])
        dates = g["issue_date"].to_numpy()
        prices = g["price"].to_numpy()
        episodes: list[tuple[float, list[int]]] = []
        triggered: list[int] = []
        baseline = None
        for i in range(len(g)):
            if baseline is not None:
                if prices[i] > baseline * (1 + thr / 2):
                    triggered.append(i)   # still above the old price level (hysteresis: thr/2)
                    continue
                episodes.append((baseline, triggered))   # price back to normal: episode over
                baseline, triggered = None, []
            prior_mask = (dates < dates[i]) & (dates >= dates[i] - lookback.to_timedelta64())
            prior = prices[prior_mask]
            if len(prior) < min_hist:
                continue
            med = float(np.median(prior))
            trimmed = prior[prior <= 3 * med]
            if len(trimmed) < min_hist:
                continue
            med = float(np.median(trimmed))
            if prices[i] > med * (1 + thr) and prices[i] > float(trimmed.max()) * (1 + tol):
                baseline, triggered = med, [i]
        if baseline is not None:
            episodes.append((baseline, triggered))
        for baseline, triggered in episodes:
            flags.append(_price_flag(g, group, prices, baseline, triggered, thr))

    flags.extend(_cross_supplier(ctx, ln))
    return flags


def _price_flag(g: pd.DataFrame, group: str, prices: np.ndarray, baseline: float, triggered: list[int],
                thr: float) -> dict:
    first = g.iloc[triggered[0]]
    affected = g.iloc[triggered]
    prev_price = float(prices[triggered[0] - 1]) if triggered[0] > 0 else baseline
    first_inc = (float(first["price"]) / baseline - 1) * 100
    latest_inc = (float(affected.iloc[-1]["price"]) / baseline - 1) * 100
    extra = float(((affected["price"] - baseline) * affected["quantity"]).sum())
    step = (float(first["price"]) / prev_price - 1) >= thr if prev_price else True
    if first_inc >= 300:
        rule = "extreme"   # 4x or more: likely a keying error rather than a price change
    elif step:
        rule = "step"
    else:
        rule = "creep"
    sev = "high" if rule == "extreme" else _severity(max(first_inc, latest_inc), extra)
    label = first["item_label"]
    hist = g[g["issue_date"] < first["issue_date"]].tail(8)
    return make_flag(
        check="price_increase", rule=rule, severity=sev,
        score=min(1.0, 0.4 + max(first_inc, latest_inc) / 100),
        supplier_cui=first["supplier_cui"], supplier_name=first["supplier_name"],
        invoice_keys=list(dict.fromkeys(affected["invoice_key"])),
        invoice_numbers=list(dict.fromkeys(affected["number"])),
        issue_date=first["issue_date"], amount_at_risk=extra, id_extra=f"{group}:{first['invoice_key']}",
        title_en=f"{label}: price {pct(first_inc)} vs usual ({lei(baseline)} → {lei(float(first['price']))})",
        title_ro=f"{label}: preț {pct(first_inc, 'ro')} față de nivelul obișnuit ({lei(baseline, 'ro')} → {lei(float(first['price']), 'ro')})",
        evidence={
            "item": label,
            "item_group": group,
            "unit": first["unit_code"],
            "baseline_median_price_ron": round(baseline, 4),
            "first_increase": {"number": first["number"], "date": str(first["issue_date"].date()),
                               "price_ron": round(float(first["price"]), 4), "increase_pct": round(first_inc, 1)},
            "latest_increase_pct": round(latest_inc, 1),
            "affected_lines": int(len(affected)),
            "extra_cost_ron": round(extra, 2),
            "pattern": rule,
            "history": [{"date": str(d.date()), "number": n, "price_ron": round(float(p), 4)}
                        for d, n, p in zip(hist["issue_date"], hist["number"], hist["price"])],
            "affected": [{"date": str(d.date()), "number": n, "price_ron": round(float(p), 4), "qty": float(q)}
                         for d, n, p, q in zip(affected["issue_date"], affected["number"], affected["price"], affected["quantity"])][:25],
            "what_to_check_en": "Compare with the agreed price list or contract; ask the supplier for the reason and effective date.",
            "what_to_check_ro": "Comparați cu lista de prețuri sau contractul agreat; cereți furnizorului motivul și data de la care se aplică.",
        },
    )


def _cross_supplier(ctx: AuditContext, ln: pd.DataFrame) -> list[dict]:
    cfg = ctx.cfg("prices")
    gap_thr = float(cfg.get("cross_supplier_gap_pct", 25.0)) / 100
    if "xgroup" not in ln or ln.empty:
        return []
    recent = ln[ln["issue_date"] >= ctx.data_end - pd.Timedelta(days=365)]
    flags = []
    for xg, part in recent.groupby("xgroup"):
        per = (part.groupby(["supplier_cui"])
               .agg(name=("supplier_name", "last"), median=("price", "median"), qty=("quantity", "sum"),
                    n=("price", "size"), label=("item_label", "first"), last_key=("invoice_key", "last"),
                    last_number=("number", "last"), last_date=("issue_date", "max"))
               .reset_index())
        per = per[per["n"] >= 2]
        if len(per) < 2:
            continue
        cheap = per.loc[per["median"].idxmin()]
        for _, row in per.iterrows():
            if row["supplier_cui"] == cheap["supplier_cui"]:
                continue
            gap = row["median"] / cheap["median"] - 1
            if gap < gap_thr:
                continue
            extra = float((row["median"] - cheap["median"]) * row["qty"])
            sev = "medium" if extra >= 1000 else "low"
            flags.append(make_flag(
                check="price_increase", rule="cross_supplier", severity=sev, score=min(1.0, 0.3 + gap),
                supplier_cui=row["supplier_cui"], supplier_name=row["name"],
                invoice_keys=[row["last_key"]], invoice_numbers=[row["last_number"]], issue_date=row["last_date"],
                amount_at_risk=extra, id_extra=xg,
                title_en=f"{row['label']}: {row['name']} charges {pct(gap * 100)} more than {cheap['name']}",
                title_ro=f"{row['label']}: {row['name']} percepe cu {pct(gap * 100, 'ro')} mai mult decât {cheap['name']}",
                evidence={
                    "item": row["label"],
                    "window": "last 12 months",
                    "this_supplier_median_ron": round(float(row["median"]), 4),
                    "cheapest_supplier": cheap["name"],
                    "cheapest_median_ron": round(float(cheap["median"]), 4),
                    "quantity_bought": float(row["qty"]),
                    "extra_cost_ron": round(extra, 2),
                    "what_to_check_en": "Check that the products are really equivalent (brand, grade, pack size) before negotiating.",
                    "what_to_check_ro": "Verificați că produsele sunt cu adevărat echivalente (marcă, calitate, ambalare) înainte de negociere.",
                },
            ))
    return flags
