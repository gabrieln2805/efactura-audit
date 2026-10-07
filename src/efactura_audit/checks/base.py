"""Shared types for the anomaly checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ..utils import short_hash

SEVERITIES = ("high", "medium", "low")

CHECK_LABELS = {
    "near_duplicate": ("Near-duplicate", "Posibil duplicat"),
    "price_increase": ("Price increase", "Creștere de preț"),
    "outlier": ("Unusual amount", "Sumă neobișnuită"),
    "vat": ("VAT pattern", "Tipar TVA"),
    "supplier": ("Supplier change", "Modificare furnizor"),
}


@dataclass
class AuditContext:
    invoices: pd.DataFrame   # fct_invoices; `spend_ron` = amount in RON
    lines: pd.DataFrame      # fct_invoice_lines; `price_ron` = unit price in RON, `item_group`, `item_label`, `xgroup`
    settings: dict[str, Any]
    store: Any = None        # Store, for ref()
    _refs: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    def cfg(self, section: str) -> dict[str, Any]:
        return self.settings.get(section, {})

    def ref(self, model: str, order_by: str = "") -> pd.DataFrame:
        """Read a SQL model (see transform/models), like dbt's ref() from a Python model."""
        key = f"{model}|{order_by}"
        if key not in self._refs:
            sql = f"SELECT * FROM {model}" + (f" ORDER BY {order_by}" if order_by else "")
            df = self.store.df(sql)
            if "issue_date" in df:
                df["issue_date"] = pd.to_datetime(df["issue_date"])
            self._refs[key] = df
        return self._refs[key]

    @property
    def data_start(self) -> pd.Timestamp:
        return self.invoices["issue_date"].min()

    @property
    def data_end(self) -> pd.Timestamp:
        return self.invoices["issue_date"].max()


def lei(x: float | None, lang: str = "en") -> str:
    if x is None or pd.isna(x):
        return "n/a"
    s = f"{x:,.2f}"
    if lang == "ro":
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} lei"


def pct(x: float, lang: str = "en") -> str:
    s = f"{x:+.1f}%"
    return s.replace(".", ",") if lang == "ro" else s


def as_date(v) -> date | None:
    if v is None or (not isinstance(v, date) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    return v


def make_flag(*, check: str, rule: str, severity: str, score: float, supplier_cui: str | None,
              supplier_name: str | None, invoice_keys: list[str], invoice_numbers: list[str],
              issue_date, amount_at_risk: float | None, title_en: str, title_ro: str,
              evidence: dict[str, Any], id_extra: str = "") -> dict[str, Any]:
    assert severity in SEVERITIES, severity
    return {
        "flag_id": f"{check[:3].upper()}-{short_hash(check, rule, supplier_cui, sorted(invoice_keys), id_extra, n=10)}",
        "check_name": check,
        "rule": rule,
        "severity": severity,
        "score": round(float(min(max(score, 0.0), 1.0)), 3),
        "supplier_cui": supplier_cui,
        "supplier_name": supplier_name,
        "invoice_keys": list(invoice_keys),
        "invoice_numbers": list(invoice_numbers),
        "issue_date": as_date(issue_date),
        "amount_at_risk_ron": None if amount_at_risk is None or pd.isna(amount_at_risk) else round(float(amount_at_risk), 2),
        "title_en": title_en,
        "title_ro": title_ro,
        "evidence": evidence,
    }
