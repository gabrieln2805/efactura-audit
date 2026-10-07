"""Score audit flags against the synthetic ground truth (recall per check, unexplained flags)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .utils import normalize_item_name


@dataclass
class Evaluation:
    rows: list[dict] = field(default_factory=list)       # one per ground-truth anomaly
    unexplained: list[dict] = field(default_factory=list)  # flags matching no injected anomaly
    n_flags: int = 0

    @property
    def recall(self) -> float:
        rel = [r for r in self.rows if r["rule"] != "legit_reissue"]
        return sum(r["found"] for r in rel) / len(rel) if rel else 1.0

    def recall_by_check(self) -> dict[str, float]:
        out: dict[str, list[bool]] = {}
        for r in self.rows:
            if r["rule"] == "legit_reissue":
                continue
            out.setdefault(r["check"], []).append(r["found"])
        return {k: sum(v) / len(v) for k, v in out.items()}

    @property
    def explained_share(self) -> float:
        return 1 - len(self.unexplained) / self.n_flags if self.n_flags else 1.0

    def report(self) -> str:
        lines = [f"Recall: {self.recall:.0%} of {sum(r['rule'] != 'legit_reissue' for r in self.rows)} injected anomalies"]
        for k, v in self.recall_by_check().items():
            lines.append(f"  {k:<15} {v:.0%}")
        legit = [r for r in self.rows if r["rule"] == "legit_reissue"]
        for r in legit:
            lines.append(f"  legit reissue {r['number']}: {'handled (low/none)' if r['found'] else 'FLAGGED AS DUPLICATE'}")
        lines.append(f"Flags explained by an injected anomaly: {self.n_flags - len(self.unexplained)}/{self.n_flags}")
        for f in self.unexplained:
            lines.append(f"  unexplained [{f['severity']}] {f['check_name']}/{f['rule']}: {f['title_en']}")
        missed = [r for r in self.rows if not r["found"]]
        for r in missed:
            lines.append(f"  MISSED {r['check']}/{r['rule']}: {r.get('supplier')} {r.get('number') or r.get('item', '')}")
        return "\n".join(lines)


def _numbers(f) -> list[str]:
    v = f["invoice_numbers"]
    return json.loads(v) if isinstance(v, str) else list(v)


def _evidence(f) -> dict:
    v = f["evidence"]
    return json.loads(v) if isinstance(v, str) else v


def _matches(t: dict, f: dict) -> bool:
    check, rule = t["check"], t["rule"]
    nums = _numbers(f)
    if f["check_name"] != check:
        return False
    if check == "near_duplicate":
        return t["number"] in nums and t.get("original") in nums
    if check == "price_increase":
        if (f["supplier_cui"] or "") != t["supplier_cui"]:
            return False
        ev = _evidence(f)
        if rule == "cross_supplier":
            return f["rule"] == "cross_supplier"
        label = normalize_item_name(ev.get("item", ""))
        item_ok = any(label == normalize_item_name(v) for v in t.get("item_variants", [t["item"]]))
        first = ev.get("first_increase", {}).get("date", "")
        return f["rule"] != "cross_supplier" and item_ok and first >= t["from"]
    if check in ("outlier", "vat"):
        return t["number"] in nums
    if check == "supplier":
        if rule == "shared_iban":
            return f["rule"] == "shared_iban" and t["supplier_cui"] in (f["supplier_cui"] or "")
        if rule == "iban_one_off":
            return f["rule"] == "iban_one_off" and t["number"] in nums
        return f["rule"] == rule and f["supplier_cui"] == t["supplier_cui"]
    return False


def evaluate(flags: pd.DataFrame | list[dict], ground_truth_path: str | Path) -> Evaluation:
    truth = json.loads(Path(ground_truth_path).read_text(encoding="utf-8"))["anomalies"]
    flist = flags.to_dict("records") if isinstance(flags, pd.DataFrame) else list(flags)
    ev = Evaluation(n_flags=len(flist))
    used: set[int] = set()
    for t in truth:
        hits = [i for i, f in enumerate(flist) if _matches(t, f)]
        if t["rule"] == "legit_reissue":
            dup_hits = [i for i, f in enumerate(flist) if f["check_name"] == "near_duplicate" and t["number"] in _numbers(f)]
            found = all(flist[i]["severity"] == "low" for i in dup_hits)
            used.update(dup_hits)
        else:
            found = bool(hits)
        used.update(hits)
        ev.rows.append({**t, "found": found, "flags": [flist[i]["flag_id"] for i in hits]})
    ev.unexplained = [f for i, f in enumerate(flist) if i not in used]
    return ev
