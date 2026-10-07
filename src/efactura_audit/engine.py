"""Run the five checks over the store and save ranked flags with evidence."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .checks import duplicates, outliers, prices, suppliers, vat
from .checks.base import AuditContext
from .itemmatch import assign_item_groups, link_across_suppliers
from .store import Store

CHECKS = ("near_duplicate", "price_increase", "outlier", "vat", "supplier")


@dataclass
class AuditResult:
    run_id: str
    n_invoices: int
    flags: list[dict] = field(default_factory=list)
    by_check: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0

    def summary(self) -> str:
        parts = ", ".join(f"{k}: {v}" for k, v in self.by_check.items())
        sev = ", ".join(f"{k}: {v}" for k, v in self.by_severity.items())
        return f"{self.n_invoices} invoices audited, {len(self.flags)} flags ({parts}) — severity {sev}"


def build_context(store: Store, settings: dict) -> AuditContext:
    inv = store.invoices()
    lines = store.lines()
    vat_df = store.vat()
    for df in (inv, lines, vat_df):
        if not df.empty:
            df["issue_date"] = pd.to_datetime(df["issue_date"])
    if not inv.empty:
        inv["amt"] = inv["amount_ron"].fillna(inv["payable"])
        inv["anaf_id"] = inv["anaf_id"].fillna("")
    if not lines.empty:
        lines["price"] = lines["unit_price_ron"].where(lines["unit_price_ron"].notna(),
                                                       lines["unit_price"].where(lines["currency"] == "RON"))
        thr = float(settings.get("prices", {}).get("name_match_score", 88))
        lines = assign_item_groups(lines, thr)
        xmap = link_across_suppliers(lines[~lines["is_credit_note"]], thr + 2)
        lines = lines.merge(xmap, on="item_group", how="left")
    return AuditContext(invoices=inv, lines=lines, vat=vat_df, settings=settings)


def consolidate(flags: list[dict]) -> list[dict]:
    """Drop a flag when a more specific check already explains the same invoice.

    A unit price keyed 10x too high shows up both as an "extreme" price increase and as a misplaced
    decimal; the controller should see it once.
    """
    decimal = {k: f for f in flags if f["check_name"] == "outlier" and f["rule"] == "decimal_shift"
               for k in f["invoice_keys"]}
    out = []
    for f in flags:
        if f["check_name"] == "price_increase" and f["rule"] == "extreme" and all(k in decimal for k in f["invoice_keys"]):
            decimal[f["invoice_keys"][0]]["evidence"].setdefault("also_detected_by", []).append(
                {"check": "price_increase", "title_en": f["title_en"]})
            continue
        out.append(f)
    return out


def run_audit(store: Store, settings: dict, checks: tuple[str, ...] = CHECKS) -> AuditResult:
    started = datetime.now()
    run_id = f"run-{started:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    ctx = build_context(store, settings)
    result = AuditResult(run_id=run_id, n_invoices=len(ctx.invoices))
    if ctx.invoices.empty:
        store.replace_flags(run_id, [], started, 0, {})
        return result

    store.save_item_groups(ctx.lines[["invoice_key", "line_no", "item_group"]])
    flags: list[dict] = []
    scores = pd.DataFrame()
    if "near_duplicate" in checks:
        flags += duplicates.run(ctx)
    if "price_increase" in checks:
        flags += prices.run(ctx)
    if "outlier" in checks:
        f, scores = outliers.run(ctx)
        flags += f
    if "vat" in checks:
        flags += vat.run(ctx)
    if "supplier" in checks:
        flags += suppliers.run(ctx)

    unique: dict[str, dict] = {}
    for f in flags:
        unique.setdefault(f["flag_id"], f)
    flags = consolidate(list(unique.values()))
    store.replace_flags(run_id, flags, started, len(ctx.invoices), {"checks": list(checks), "settings": settings})
    if not scores.empty:
        store.save_scores(scores)

    result.flags = flags
    for f in flags:
        result.by_check[f["check_name"]] = result.by_check.get(f["check_name"], 0) + 1
        result.by_severity[f["severity"]] = result.by_severity.get(f["severity"], 0) + 1
    result.seconds = (datetime.now() - started).total_seconds()
    return result
