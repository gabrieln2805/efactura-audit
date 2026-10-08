"""Unusual amounts.

Three layers, from most to least explainable:
1. per-supplier robust z-score (median/MAD) of log(amount) — "far above this supplier's usual size";
2. line-level misplaced decimals — quantity or price ~10x/100x the item's usual level;
3. global models (Isolation Forest + a small autoencoder) over invoice features, reported only
   when both agree and the simpler rules have not already explained the invoice.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .base import AuditContext, lei, make_flag

FEATURES = ["log_amt", "n_lines", "log_mean_line", "supplier_z", "log_gap_days", "day_of_month", "vat_ratio"]


def _robust_z(x: pd.Series) -> tuple[pd.Series, float, float]:
    med = float(x.median())
    mad = float((x - med).abs().median())
    if mad == 0:
        return pd.Series(np.zeros(len(x)), index=x.index), med, 0.0
    return 0.6745 * (x - med) / mad, med, mad


def invoice_features(ctx: AuditContext) -> pd.DataFrame:
    """int_invoice_features plus the transforms the models need (logs, per-supplier robust z)."""
    inv = ctx.ref("int_invoice_features", order_by="supplier_cui, issue_date, invoice_key").copy()
    if inv.empty:
        return inv
    inv["log_amt"] = np.log1p(inv["spend_ron"])
    inv["log_mean_line"] = np.log1p(inv["spend_ron"] / inv["n_lines"])
    inv["supplier_z"] = 0.0
    inv["supplier_median"] = np.nan
    for cui, idx in inv.groupby("supplier_cui").groups.items():
        z, med, _ = _robust_z(inv.loc[idx, "log_amt"])
        inv.loc[idx, "supplier_z"] = z.clip(-10, 10)
        inv.loc[idx, "supplier_median"] = np.expm1(med)
    inv["log_gap_days"] = np.log1p(inv["gap_days"])
    return inv


def model_scores(feat: pd.DataFrame, contamination: float = 0.01, seed: int = 0) -> pd.DataFrame:
    """Isolation Forest and autoencoder scores (0-1, higher = more unusual) per invoice."""
    # imported here: scikit-learn (and scipy) are the slowest packages to load, and the web app fetches them
    # in the background, only once an audit runs
    from sklearn.ensemble import IsolationForest
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    X = StandardScaler().fit_transform(feat[FEATURES].to_numpy(dtype=float))
    iso = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed).fit(X)
    iso_raw = -iso.score_samples(X)
    ae = MLPRegressor(hidden_layer_sizes=(8, 3, 8), activation="tanh", max_iter=800, random_state=seed,
                      alpha=1e-3, learning_rate_init=0.005)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        ae.fit(X, X)
    err = (ae.predict(X) - X) ** 2
    recon = err.mean(axis=1)
    out = pd.DataFrame(index=feat.index)
    out["iforest"] = pd.Series(iso_raw, index=feat.index).rank(pct=True)
    out["autoencoder"] = pd.Series(recon, index=feat.index).rank(pct=True)
    out["combined"] = (out["iforest"] + out["autoencoder"]) / 2
    top = np.argsort(-err, axis=1)[:, :2]
    out["top_features"] = [", ".join(FEATURES[j] for j in row) for row in top]
    return out


def run(ctx: AuditContext) -> tuple[list[dict], pd.DataFrame]:
    cfg = ctx.cfg("outliers")
    min_hist = int(cfg.get("min_history", 6))
    z_thr = float(cfg.get("robust_z", 4.0))
    contamination = float(cfg.get("model_contamination", 0.01))
    shift = float(cfg.get("decimal_shift_ratio", 8.0))
    flags: list[dict] = []
    explained: set[str] = set()

    feat = invoice_features(ctx)
    if feat.empty:
        return flags, pd.DataFrame()

    # 1) per-supplier size -------------------------------------------------------------------
    for cui, part in feat.groupby("supplier_cui"):
        if len(part) < min_hist:
            continue
        z, med_log, mad = _robust_z(part["log_amt"])
        med = float(np.expm1(med_log))
        amts = part["spend_ron"].to_numpy()
        for pos, (idx, row) in enumerate(part.iterrows()):
            ratio = row["spend_ron"] / med if med else 0
            others = np.delete(amts, pos)
            p95 = float(np.quantile(others, 0.95)) if len(others) else 0.0
            if mad == 0:
                hit = ratio > 1.25   # a fixed monthly amount that suddenly changes
                zval = float("inf") if hit else 0.0
            else:
                zval = float(z[idx])
                # wide, multi-modal suppliers (short and long routes) hide big invoices from z-scores,
                # so also flag amounts far above the supplier's usual upper range
                hit = (zval >= z_thr and ratio >= 2) or (p95 > 0 and row["spend_ron"] >= 2 * p95 and ratio >= 3)
            if not hit:
                continue
            sev = "high" if ratio >= 5 or row["spend_ron"] - med >= 50_000 else "medium"
            explained.add(row["invoice_key"])
            flags.append(make_flag(
                check="outlier", rule="supplier_amount", severity=sev, score=min(1.0, 0.5 + ratio / 20),
                supplier_cui=cui, supplier_name=row["supplier_name"], invoice_keys=[row["invoice_key"]],
                invoice_numbers=[row["number"]], issue_date=row["issue_date"], amount_at_risk=row["spend_ron"] - med,
                title_en=f"Invoice {row['number']} is {ratio:.1f}x this supplier's usual amount ({lei(row['spend_ron'])} vs {lei(med)})",
                title_ro=f"Factura {row['number']} este de {f'{ratio:.1f}'.replace('.', ',')} ori valoarea obișnuită a furnizorului ({lei(row['spend_ron'], 'ro')} față de {lei(med, 'ro')})",
                evidence={
                    "amount_ron": round(float(row["spend_ron"]), 2),
                    "supplier_median_ron": round(med, 2),
                    "ratio_to_median": round(float(ratio), 2),
                    "robust_z": None if zval == float("inf") else round(zval, 2),
                    "supplier_p95_ron": round(p95, 2),
                    "supplier_invoices": int(len(part)),
                    "what_to_check_en": "Check the delivery note or order behind this invoice; confirm quantities received.",
                    "what_to_check_ro": "Verificați avizul sau comanda aferentă facturii; confirmați cantitățile recepționate.",
                },
            ))

    # 2) misplaced decimals on lines (one flag per invoice) ----------------------------------------
    ln = ctx.lines[(~ctx.lines["is_credit_note"]) & (ctx.lines["quantity"] > 0)]
    hits: dict[str, list[dict]] = {}
    heads: dict[str, pd.Series] = {}
    for group, g in ln.groupby("item_group"):
        if len(g) < 5:
            continue
        mq, mp = g["quantity"].median(), g["price_ron"].median()
        mn = (g["quantity"] * g["price_ron"]).median()
        for _, row in g.iterrows():
            q_ratio = row["quantity"] / mq if mq else 0
            p_ratio = row["price_ron"] / mp if mp else 0
            n_ratio = row["quantity"] * row["price_ron"] / mn if mn else 0
            if q_ratio >= shift and n_ratio >= shift / 2:
                what, ratio = "quantity", q_ratio
            elif p_ratio >= shift:  # unit prices of one item rarely vary 8x, whatever the quantity
                what, ratio = "unit price", p_ratio
            else:
                continue
            line_net = float(row["quantity"] * row["price_ron"])
            hits.setdefault(row["invoice_key"], []).append({
                "line": row["item_name"], "label": row["item_label"], "field": what,
                "quantity": float(row["quantity"]), "usual_quantity": float(mq),
                "unit_price_ron": round(float(row["price_ron"]), 4), "usual_unit_price_ron": round(float(mp), 4),
                "line_amount_ron": round(line_net, 2), "usual_line_amount_ron": round(float(mn), 2),
                "ratio": round(float(ratio), 1),
            })
            heads[row["invoice_key"]] = row
    for key, items in hits.items():
        row = heads[key]
        top = max(items, key=lambda x: x["line_amount_ron"] - x["usual_line_amount_ron"])
        extra = sum(x["line_amount_ron"] - x["usual_line_amount_ron"] for x in items)
        what_ro = "cantitatea" if top["field"] == "quantity" else "prețul unitar"
        more = f" (+{len(items) - 1} more lines)" if len(items) > 1 else ""
        more_ro = f" (+{len(items) - 1} alte linii)" if len(items) > 1 else ""
        explained.add(key)
        flags.append(make_flag(
            check="outlier", rule="decimal_shift", severity="high", score=0.9,
            supplier_cui=row["supplier_cui"], supplier_name=row["supplier_name"],
            invoice_keys=[key], invoice_numbers=[row["number"]], issue_date=row["issue_date"],
            amount_at_risk=extra,
            title_en=f"Invoice {row['number']}: {top['label']} {top['field']} is ≈{top['ratio']:.0f}x usual — misplaced decimal?{more}",
            title_ro=f"Factura {row['number']}: {what_ro} pentru {top['label']} este de ≈{top['ratio']:.0f} ori cea obișnuită — virgulă greșită?{more_ro}",
            evidence={
                "lines": items,
                "extra_vs_usual_ron": round(extra, 2),
                "what_to_check_en": "Compare with the goods received note; a factor of 10 or 100 usually means a keying error.",
                "what_to_check_ro": "Comparați cu nota de recepție; un factor de 10 sau 100 indică de obicei o greșeală de introducere.",
            },
        ))

    # 3) global models ------------------------------------------------------------------------
    scores = pd.DataFrame()
    if len(feat) >= 50:
        scores = model_scores(feat, contamination)
        feat = feat.join(scores)
        cutoff = 1 - contamination
        cand = feat[(feat["iforest"] >= cutoff) & (feat["autoencoder"] >= cutoff)
                    & ~feat["invoice_key"].isin(explained)]
        for _, row in cand.iterrows():
            flags.append(make_flag(
                check="outlier", rule="model", severity="low", score=float(row["combined"]) * 0.6,
                supplier_cui=row["supplier_cui"], supplier_name=row["supplier_name"],
                invoice_keys=[row["invoice_key"]], invoice_numbers=[row["number"]], issue_date=row["issue_date"],
                amount_at_risk=None,
                title_en=f"Invoice {row['number']} looks unusual overall ({row['top_features']})",
                title_ro=f"Factura {row['number']} pare neobișnuită în ansamblu ({row['top_features']})",
                evidence={
                    "amount_ron": round(float(row["spend_ron"]), 2),
                    "supplier_median_ron": round(float(row["supplier_median"]), 2),
                    "isolation_forest_percentile": round(float(row["iforest"]), 3),
                    "autoencoder_percentile": round(float(row["autoencoder"]), 3),
                    "most_unusual_features": row["top_features"],
                    "features": {f: round(float(row[f]), 3) for f in FEATURES},
                    "what_to_check_en": "Statistical signal only: look at the invoice and decide whether anything is off.",
                    "what_to_check_ro": "Doar un semnal statistic: consultați factura și decideți dacă ceva nu e în regulă.",
                },
            ))
    score_table = pd.DataFrame()
    if not scores.empty:
        score_table = feat[["invoice_key", "supplier_z", "iforest", "autoencoder", "combined"]].copy()
    return flags, score_table
