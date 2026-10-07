"""Read-only query tools over the local audit database.

The same functions back the MCP server (for any MCP client) and the in-app assistant. Every figure
the assistant gives comes from one of these SQL-backed tools, never from the model, so each answer
can be traced to a tool call and its result.
"""
from __future__ import annotations

import inspect
import json
import re
import typing
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import pandas as pd

from ..checks.base import CHECK_LABELS
from ..store import Store
from ..transform import project
from ..utils import mask_iban

CHECK_NAMES = list(CHECK_LABELS)
_MIDNIGHT = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00(\.0+)?$")


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    param_docs: dict[str, str]

    def json_schema(self) -> dict:
        """Plain JSON schema (no anyOf) so small local models can follow it."""
        props, required = {}, []
        hints = typing.get_type_hints(self.fn)
        for pname, p in inspect.signature(self.fn).parameters.items():
            if pname == "self":
                continue
            t = hints.get(pname, str)
            origin_args = typing.get_args(t)
            base = next((a for a in origin_args if a is not type(None)), t) if origin_args else t
            js = {str: "string", int: "integer", float: "number", bool: "boolean"}.get(base, "string")
            prop = {"type": js, "description": self.param_docs.get(pname, "")}
            if pname == "check":
                prop["enum"] = CHECK_NAMES
            if pname == "severity":
                prop["enum"] = ["high", "medium", "low"]
            props[pname] = prop
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        return {"type": "object", "properties": props, "required": required}


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict]:
    if limit is not None:
        df = df.head(limit)
    out = json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))
    for row in out:
        for k, v in list(row.items()):
            if isinstance(v, str) and _MIDNIGHT.match(v):
                row[k] = v[:10]
            if isinstance(v, float):
                row[k] = round(v, 2)
    return out


def _supplier_filter(supplier: str | None, col_name: str = "supplier_name", col_cui: str = "supplier_cui") -> tuple[str, list]:
    if not supplier:
        return "", []
    s = supplier.strip()
    digits = re.sub(r"\D", "", s)
    if digits and len(digits) >= 4 and len(digits) >= len(s.replace("RO", "").replace("ro", "")) - 1:
        return f" AND {col_cui} LIKE ?", [f"%{digits}%"]
    return f" AND strip_accents(lower({col_name})) LIKE strip_accents(lower(?))", [f"%{s}%"]


_FORBIDDEN_SQL = re.compile(
    r"(?i)\b(attach|copy|export|install|load|pragma|set|read_\w+|\w+_scan|sniff_csv|glob|httpfs|query_table)\b")


def readonly_select(store: Store, query: str, limit: int = 200) -> pd.DataFrame:
    """One SELECT on a read-only connection with file and network access disabled.

    Raises ValueError for anything that is not a single plain SELECT; DuckDB errors propagate.
    """
    q = query.strip().rstrip(";")
    if ";" in q or not re.match(r"(?is)^\s*(select|with)\b", q):
        raise ValueError("Only a single SELECT (or WITH ... SELECT) statement is allowed.")
    if _FORBIDDEN_SQL.search(q):
        raise ValueError("That function is not allowed here.")
    with store.connect(read_only=True) as con:
        con.execute("SET enable_external_access = false")   # no file or network reads from SQL
        return con.execute(f"SELECT * FROM ({q}) LIMIT {int(limit)}").df()


def _mart_tables() -> str:
    """The marts and their documented columns (transform/models/marts/_marts.yml), for run_sql."""
    return ", ".join(f"{m.name}({', '.join(m.columns)})" for m in project().layer("marts"))


class AuditTools:
    """Tool implementations. `lang` picks the language of flag titles (ro/en)."""

    def __init__(self, store: Store, lang: str = "ro"):
        self.store = store
        self.lang = lang if lang in ("ro", "en") else "ro"

    # ------------------------------------------------------------------ tools
    def audit_overview(self) -> dict:
        s = self.store
        head = s.df("""SELECT COUNT(*) AS invoices, COUNT(DISTINCT supplier_cui) AS suppliers,
                              MIN(issue_date) AS first_date, MAX(issue_date) AS last_date,
                              ROUND(SUM(spend_ron), 2) AS total_spend_ron,
                              CAST(SUM(CASE WHEN is_credit_note THEN 1 ELSE 0 END) AS INTEGER) AS credit_notes,
                              ANY_VALUE(buyer_name) AS company
                       FROM fct_invoices""")
        flags = s.df("""SELECT check_name, severity, COUNT(*) AS n, ROUND(SUM(COALESCE(amount_at_risk_ron,0)),2) AS amount
                        FROM fct_flags WHERE status <> 'dismissed' GROUP BY 1, 2""")
        run = s.df("SELECT run_id, finished_at FROM runs ORDER BY finished_at DESC LIMIT 1")
        rec = _records(head)[0]
        rec["flags_total"] = int(flags["n"].sum()) if not flags.empty else 0
        rec["amount_to_review_ron"] = round(float(flags["amount"].sum()), 2) if not flags.empty else 0.0
        rec["flags_by_check"] = {k: int(v) for k, v in flags.groupby("check_name")["n"].sum().items()} if not flags.empty else {}
        rec["flags_by_severity"] = {k: int(v) for k, v in flags.groupby("severity")["n"].sum().items()} if not flags.empty else {}
        rec["last_audit"] = str(run["finished_at"].iloc[0])[:16] if not run.empty else None
        return rec

    def list_flags(self, check: Optional[str] = None, severity: Optional[str] = None, supplier: Optional[str] = None,
                   min_amount: Optional[float] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                   include_dismissed: bool = False, limit: int = 20) -> dict:
        where, params = ["1=1"], []
        if check:
            where.append("check_name = ?")
            params.append(check)
        if severity:
            where.append("severity = ?")
            params.append(severity)
        if min_amount is not None:
            where.append("amount_at_risk_ron >= ?")
            params.append(float(min_amount))
        if date_from:
            where.append("issue_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("issue_date <= ?")
            params.append(date_to)
        if not include_dismissed:
            where.append("status <> 'dismissed'")
        sf, sp = _supplier_filter(supplier)
        sql = f"""SELECT flag_id, severity, check_name, rule, supplier_name, invoice_numbers, issue_date,
                         amount_at_risk_ron, title_{self.lang} AS title, status
                  FROM fct_flags WHERE {' AND '.join(where)}{sf}
                  ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, score DESC,
                           amount_at_risk_ron DESC NULLS LAST"""
        df = self.store.df(sql, params + sp)
        df["invoice_numbers"] = df["invoice_numbers"].map(lambda v: json.loads(v)[:6])
        limit = max(1, min(int(limit or 20), 100))
        return {"total_matching": int(len(df)),
                "amount_to_review_ron": round(float(df["amount_at_risk_ron"].fillna(0).sum()), 2),
                "flags": _records(df, limit)}

    def get_flag(self, flag_id: str) -> dict:
        df = self.store.df("SELECT * FROM fct_flags WHERE flag_id = ?", [flag_id.strip()])
        if df.empty:
            return {"error": f"No flag with id {flag_id}"}
        r = _records(df)[0]
        ev = json.loads(r.pop("evidence"))
        for k in list(ev):
            if k.endswith("_full"):
                ev.pop(k)
        other = "en" if self.lang == "ro" else "ro"
        for k in (f"title_{other}", f"what_to_check_{other}", f"notes_{other}"):
            r.pop(k, None)
            ev.pop(k, None)
        r["title"] = r.pop(f"title_{self.lang}")
        r["invoice_numbers"] = json.loads(r["invoice_numbers"])
        r.pop("invoice_keys", None)
        r["evidence"] = ev
        return r

    def search_invoices(self, supplier: Optional[str] = None, number: Optional[str] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                        min_amount: Optional[float] = None, max_amount: Optional[float] = None,
                        flagged_only: bool = False, order_by: str = "date", limit: int = 20) -> dict:
        where, params = ["1=1"], []
        if number:
            where.append("upper(i.number) LIKE upper(?)")
            params.append(f"%{number.strip()}%")
        if date_from:
            where.append("i.issue_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("i.issue_date <= ?")
            params.append(date_to)
        if min_amount is not None:
            where.append("i.spend_ron >= ?")
            params.append(float(min_amount))
        if max_amount is not None:
            where.append("i.spend_ron <= ?")
            params.append(float(max_amount))
        sf, sp = _supplier_filter(supplier, "i.supplier_name", "i.supplier_cui")
        flag_join = """LEFT JOIN (SELECT invoice_key, COUNT(*) AS n_flags FROM fct_flag_invoices
                                  WHERE status <> 'dismissed' GROUP BY 1) fl
                       ON fl.invoice_key = i.invoice_key"""
        if flagged_only:
            where.append("fl.n_flags > 0")
        order = "amount_ron DESC" if order_by == "amount" else "i.issue_date DESC"
        sql = f"""SELECT i.number, i.issue_date, i.supplier_name, i.supplier_cui, i.currency, i.payable,
                         ROUND(i.spend_ron, 2) AS amount_ron, i.is_credit_note,
                         COALESCE(fl.n_flags, 0) AS n_flags
                  FROM fct_invoices i {flag_join}
                  WHERE {' AND '.join(where)}{sf} ORDER BY {order}"""
        df = self.store.df(sql, params + sp)
        limit = max(1, min(int(limit or 20), 100))
        return {"total_matching": int(len(df)), "total_amount_ron": round(float(df["amount_ron"].sum()), 2),
                "invoices": _records(df, limit)}

    def get_invoice(self, number: str, supplier: Optional[str] = None) -> dict:
        sf, sp = _supplier_filter(supplier)
        heads = self.store.df(
            f"""SELECT invoice_key, number, issue_date, due_date, type_code, is_credit_note, currency, supplier_name,
                       supplier_cui, supplier_iban, payable, tax_total, tax_exclusive, fx_to_ron,
                       ROUND(spend_ron, 2) AS amount_ron, anaf_id, note
                FROM fct_invoices WHERE upper(number) = upper(?){sf} ORDER BY issue_date""", [number.strip()] + sp)
        if heads.empty:
            return {"error": f"No invoice numbered {number}"}
        out = []
        for h in _records(heads, 5):
            key = h.pop("invoice_key")
            h["supplier_iban"] = mask_iban(h["supplier_iban"])
            lines = self.store.df(
                """SELECT line_no, item_name, quantity, unit_code, unit_price, net_amount, vat_category, vat_rate
                   FROM fct_invoice_lines WHERE invoice_key = ? ORDER BY TRY_CAST(line_no AS INTEGER), line_no""", [key])
            flags = self.store.df(
                f"""SELECT f.flag_id, f.severity, f.check_name, f.title_{self.lang} AS title
                    FROM fct_flag_invoices fi JOIN fct_flags f USING (flag_id)
                    WHERE fi.invoice_key = ? AND f.status <> 'dismissed' ORDER BY f.flag_id""", [key])
            h["lines"] = _records(lines, 50)
            h["flags"] = _records(flags)
            out.append(h)
        return {"invoices": out}

    def supplier_summary(self, supplier: str) -> dict:
        sf, sp = _supplier_filter(supplier)
        # match any name the supplier has used, not only the latest
        sups = self.store.df(f"""SELECT supplier_cui, supplier_name, invoices, ROUND(total_spend_ron, 2) AS total_spend_ron,
                                        ROUND(average_invoice_ron, 2) AS average_invoice_ron, first_invoice, last_invoice
                                 FROM dim_suppliers
                                 WHERE supplier_cui IN (SELECT supplier_cui FROM fct_invoices WHERE 1=1{sf})
                                 ORDER BY total_spend_ron DESC""", sp)
        if sups.empty:
            return {"error": f"No supplier matching {supplier!r}"}
        out = []
        for s in _records(sups, 3):
            cui = s["supplier_cui"]
            monthly = self.store.df(
                """SELECT month, invoices, ROUND(spend_ron, 2) AS spend_ron
                   FROM mart_supplier_monthly_spend WHERE supplier_cui = ? ORDER BY month""", [cui])
            ibans = self.store.df(
                """SELECT supplier_iban, invoices, first_used, last_used
                   FROM dim_supplier_bank_accounts WHERE supplier_cui = ? ORDER BY first_used""", [cui])
            ibans["supplier_iban"] = ibans["supplier_iban"].map(mask_iban)
            flags = self.store.df(
                f"""SELECT flag_id, severity, check_name, amount_at_risk_ron, title_{self.lang} AS title FROM fct_flags
                    WHERE supplier_cui LIKE ? AND status <> 'dismissed'
                    ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END""", [f"%{cui}%"])
            s["monthly_spend"] = _records(monthly)
            s["bank_accounts"] = _records(ibans)
            s["flags"] = _records(flags, 15)
            out.append(s)
        return {"suppliers": out}

    def top_suppliers(self, date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = 10) -> dict:
        where, params = ["1=1"], []
        if date_from:
            where.append("issue_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("issue_date <= ?")
            params.append(date_to)
        df = self.store.df(f"""SELECT d.supplier_name, i.supplier_cui, COUNT(*) AS invoices,
                                      ROUND(SUM(i.spend_ron), 2) AS spend_ron
                               FROM fct_invoices i JOIN dim_suppliers d USING (supplier_cui)
                               WHERE {' AND '.join(where)} GROUP BY 1, 2 ORDER BY spend_ron DESC""", params)
        total = float(df["spend_ron"].sum()) if not df.empty else 0.0
        df["share_pct"] = (df["spend_ron"] / total * 100).round(1) if total else 0.0
        return {"total_spend_ron": round(total, 2), "suppliers": _records(df, max(1, min(int(limit or 10), 50)))}

    def price_changes(self, date_from: Optional[str] = None, date_to: Optional[str] = None,
                      supplier: Optional[str] = None, limit: int = 10) -> dict:
        where, params = ["check_name = 'price_increase'", "status <> 'dismissed'"], []
        if date_from:
            where.append("issue_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("issue_date <= ?")
            params.append(date_to)
        sf, sp = _supplier_filter(supplier)
        df = self.store.df(f"""SELECT flag_id, rule, supplier_name, issue_date, amount_at_risk_ron, evidence
                               FROM fct_flags WHERE {' AND '.join(where)}{sf}""", params + sp)
        items = []
        for r in df.itertuples(index=False):
            ev = json.loads(r.evidence)
            if r.rule == "cross_supplier":
                inc = (ev["this_supplier_median_ron"] / ev["cheapest_median_ron"] - 1) * 100
                items.append({"flag_id": r.flag_id, "supplier": r.supplier_name, "item": ev.get("item"),
                              "type": "more expensive than another supplier", "increase_pct": round(inc, 1),
                              "extra_cost_ron": ev.get("extra_cost_ron"), "compared_with": ev.get("cheapest_supplier")})
            else:
                items.append({"flag_id": r.flag_id, "supplier": r.supplier_name, "item": ev.get("item"),
                              "type": f"increase ({ev.get('pattern')})",
                              "since": ev.get("first_increase", {}).get("date"),
                              "old_price_ron": ev.get("baseline_median_price_ron"),
                              "new_price_ron": ev.get("first_increase", {}).get("price_ron"),
                              "increase_pct": max(ev.get("first_increase", {}).get("increase_pct", 0), ev.get("latest_increase_pct", 0)),
                              "extra_cost_ron": ev.get("extra_cost_ron")})
        items.sort(key=lambda x: -(x.get("increase_pct") or 0))
        by_sup: dict[str, dict] = {}
        for it in items:
            if it["type"].startswith("increase"):
                s = by_sup.setdefault(it["supplier"], {"supplier": it["supplier"], "items_increased": 0,
                                                       "max_increase_pct": 0.0, "extra_cost_ron": 0.0})
                s["items_increased"] += 1
                s["max_increase_pct"] = max(s["max_increase_pct"], it["increase_pct"] or 0)
                s["extra_cost_ron"] = round(s["extra_cost_ron"] + (it["extra_cost_ron"] or 0), 2)
        ranking = sorted(by_sup.values(), key=lambda x: -x["max_increase_pct"])
        n = max(1, min(int(limit or 10), 50))
        return {"suppliers_ranked_by_increase": ranking[:n], "items": items[:n]}

    def spend_over_time(self, supplier: Optional[str] = None, date_from: Optional[str] = None,
                        date_to: Optional[str] = None, granularity: str = "month") -> dict:
        fmt = {"month": "%Y-%m", "quarter": "quarter", "year": "%Y"}.get(granularity, "%Y-%m")
        period = ("CAST(year(issue_date) AS VARCHAR) || '-Q' || CAST(quarter(issue_date) AS VARCHAR)"
                  if fmt == "quarter" else f"strftime(issue_date, '{fmt}')")
        where, params = ["1=1"], []
        if date_from:
            where.append("issue_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("issue_date <= ?")
            params.append(date_to)
        sf, sp = _supplier_filter(supplier)
        df = self.store.df(f"""SELECT {period} AS period, COUNT(*) AS invoices,
                                      ROUND(SUM(spend_ron), 2) AS spend_ron
                               FROM fct_invoices WHERE {' AND '.join(where)}{sf} GROUP BY 1 ORDER BY 1""", params + sp)
        return {"granularity": granularity, "series": _records(df)}

    def run_sql(self, query: str) -> dict:
        try:
            df = readonly_select(self.store, query, limit=200)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:300]}
        for col in df.columns:
            if "iban" in col.lower():
                df[col] = df[col].map(lambda v: mask_iban(v) if isinstance(v, str) else v)
        return {"rows": _records(df), "row_count": int(len(df))}

    # ------------------------------------------------------------------ registry
    def specs(self) -> list[ToolSpec]:
        date_doc = "ISO date YYYY-MM-DD"
        sup_doc = "Supplier name (partial, accents optional) or CUI"
        return [
            ToolSpec("audit_overview", "Headline numbers: invoice count, period covered, total supplier spend, number of "
                     "suppliers, and flags by check and severity with the total amount to review. Call first for general questions.",
                     self.audit_overview, {}),
            ToolSpec("list_flags", "List audit flags (possible problems to check), most important first. Filter by check type "
                     "(near_duplicate, price_increase, outlier = unusual amount, vat, supplier = bank account/new supplier/CUI), "
                     "severity, supplier, minimum amount to review in lei, or date range.",
                     self.list_flags, {"check": "Check type", "severity": "high, medium or low", "supplier": sup_doc,
                                       "min_amount": "Minimum amount to review, in lei", "date_from": date_doc,
                                       "date_to": date_doc, "include_dismissed": "Include flags the user dismissed",
                                       "limit": "Max rows (default 20)"}),
            ToolSpec("get_flag", "Full details and evidence for one flag, by its flag_id (e.g. NEA-1a2b3c4d5e).",
                     self.get_flag, {"flag_id": "Flag ID"}),
            ToolSpec("search_invoices", "Search invoices by supplier, number, date range or amount (lei, incl. VAT). "
                     "flagged_only=true returns only invoices with open flags.",
                     self.search_invoices, {"supplier": sup_doc, "number": "Invoice number (partial)", "date_from": date_doc,
                                            "date_to": date_doc, "min_amount": "Minimum amount in lei",
                                            "max_amount": "Maximum amount in lei", "flagged_only": "Only invoices with flags",
                                            "order_by": "'date' (newest first) or 'amount' (largest first)",
                                            "limit": "Max rows (default 20)"}),
            ToolSpec("get_invoice", "One invoice with its lines and any flags, by invoice number.",
                     self.get_invoice, {"number": "Invoice number, exactly as printed", "supplier": sup_doc}),
            ToolSpec("supplier_summary", "A supplier's total spend, invoice count, monthly spend, bank accounts used over time, and flags.",
                     self.supplier_summary, {"supplier": sup_doc}),
            ToolSpec("top_suppliers", "Suppliers ranked by spend (lei, incl. VAT) with share of total, optionally within a date range.",
                     self.top_suppliers, {"date_from": date_doc, "date_to": date_doc, "limit": "Max rows (default 10)"}),
            ToolSpec("price_changes", "Price increases found by the audit: suppliers ranked by their largest increase, and "
                     "per-item old/new price, % increase and extra cost. Filter by date range (when the increase started) or supplier.",
                     self.price_changes, {"date_from": date_doc, "date_to": date_doc, "supplier": sup_doc,
                                          "limit": "Max rows (default 10)"}),
            ToolSpec("spend_over_time", "Supplier spend per month, quarter or year, optionally for one supplier.",
                     self.spend_over_time, {"supplier": sup_doc, "date_from": date_doc, "date_to": date_doc,
                                            "granularity": "month, quarter or year"}),
            ToolSpec("run_sql", "Read-only DuckDB SELECT for questions the other tools cannot answer (max 200 rows). Tables: "
                     f"{_mart_tables()}. Column descriptions: duckdb_columns().comment.",
                     self.run_sql, {"query": "A single SELECT statement"}),
        ]

    def call(self, name: str, arguments: dict | None) -> Any:
        spec = next((s for s in self.specs() if s.name == name), None)
        if spec is None:
            return {"error": f"Unknown tool {name}"}
        args = {k: v for k, v in (arguments or {}).items() if v is not None and v != ""}
        allowed = set(inspect.signature(spec.fn).parameters)
        args = {k: v for k, v in args.items() if k in allowed}
        try:
            return spec.fn(**args)
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}


def today_iso() -> str:
    return date.today().isoformat()
