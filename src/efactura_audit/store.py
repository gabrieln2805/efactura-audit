"""Local DuckDB invoice store.

Connections are short-lived (opened per operation) so the Streamlit app, the CLI and the MCP
server can share one file: DuckDB allows one writer process at a time, and a brief retry covers
the moment another process holds the lock.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from typing import TYPE_CHECKING

import duckdb
import pandas as pd

if TYPE_CHECKING:
    from .importer.parser import ParsedInvoice

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_key VARCHAR PRIMARY KEY,
        anaf_id VARCHAR,
        number VARCHAR,
        type_code VARCHAR,
        is_credit_note BOOLEAN,
        issue_date DATE,
        due_date DATE,
        currency VARCHAR,
        supplier_cui VARCHAR,
        supplier_vat_id VARCHAR,
        supplier_name VARCHAR,
        supplier_reg_no VARCHAR,
        supplier_iban VARCHAR,
        supplier_city VARCHAR,
        buyer_cui VARCHAR,
        buyer_name VARCHAR,
        line_total DOUBLE,
        tax_exclusive DOUBLE,
        tax_total DOUBLE,
        tax_inclusive DOUBLE,
        payable DOUBLE,
        fx_to_ron DOUBLE,
        amount_ron DOUBLE,
        note VARCHAR,
        source_file VARCHAR,
        xml_sha256 VARCHAR,
        imported_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoice_lines (
        invoice_key VARCHAR,
        line_no VARCHAR,
        item_name VARCHAR,
        item_norm VARCHAR,
        seller_item_id VARCHAR,
        quantity DOUBLE,
        unit_code VARCHAR,
        unit_price DOUBLE,
        unit_price_ron DOUBLE,
        base_quantity DOUBLE,
        net_amount DOUBLE,
        net_amount_ron DOUBLE,
        vat_category VARCHAR,
        vat_rate DOUBLE,
        item_group VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vat_breakdown (
        invoice_key VARCHAR,
        category VARCHAR,
        rate DOUBLE,
        taxable DOUBLE,
        tax DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS flags (
        flag_id VARCHAR PRIMARY KEY,
        run_id VARCHAR,
        check_name VARCHAR,
        rule VARCHAR,
        severity VARCHAR,
        score DOUBLE,
        supplier_cui VARCHAR,
        supplier_name VARCHAR,
        invoice_keys VARCHAR,
        invoice_numbers VARCHAR,
        issue_date DATE,
        amount_at_risk_ron DOUBLE,
        title_en VARCHAR,
        title_ro VARCHAR,
        evidence VARCHAR,
        created_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS flag_feedback (
        flag_id VARCHAR PRIMARY KEY,
        check_name VARCHAR,
        rule VARCHAR,
        status VARCHAR,
        note VARCHAR,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR PRIMARY KEY,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        n_invoices INTEGER,
        n_flags INTEGER,
        params VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_log (
        logged_at TIMESTAMP,
        source VARCHAR,
        status VARCHAR,
        message VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoice_scores (
        invoice_key VARCHAR PRIMARY KEY,
        supplier_z DOUBLE,
        iforest DOUBLE,
        autoencoder DOUBLE,
        combined DOUBLE
    )
    """,
    """
    CREATE OR REPLACE VIEW flags_view AS
    SELECT f.*, COALESCE(fb.status, 'open') AS status, fb.note AS review_note
    FROM flags f LEFT JOIN flag_feedback fb USING (flag_id)
    """,
]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self, read_only: bool = False, retries: int = 20) -> Iterator[duckdb.DuckDBPyConnection]:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                con = duckdb.connect(str(self.path), read_only=read_only and self.path.exists())
                break
            except duckdb.IOException as exc:  # file locked by another process
                last = exc
                time.sleep(0.15 * (attempt + 1))
        else:
            raise RuntimeError(f"Database is busy: {last}")
        try:
            yield con
        finally:
            con.close()

    def init_schema(self) -> None:
        with self.connect() as con:
            for stmt in SCHEMA:
                con.execute(stmt)

    # ------------------------------------------------------------------ import
    INVOICE_COLS = [
        "invoice_key", "anaf_id", "number", "type_code", "is_credit_note", "issue_date", "due_date", "currency",
        "supplier_cui", "supplier_vat_id", "supplier_name", "supplier_reg_no", "supplier_iban", "supplier_city",
        "buyer_cui", "buyer_name", "line_total", "tax_exclusive", "tax_total", "tax_inclusive", "payable",
        "fx_to_ron", "amount_ron", "note", "source_file", "xml_sha256", "imported_at",
    ]
    LINE_COLS = [
        "invoice_key", "line_no", "item_name", "item_norm", "seller_item_id", "quantity", "unit_code", "unit_price",
        "unit_price_ron", "base_quantity", "net_amount", "net_amount_ron", "vat_category", "vat_rate", "item_group",
    ]
    VAT_COLS = ["invoice_key", "category", "rate", "taxable", "tax"]

    def existing_keys(self, con) -> tuple[set[str], set[str]]:
        rows = con.execute("SELECT invoice_key, xml_sha256 FROM invoices").fetchall()
        return {r[0] for r in rows}, {r[1] for r in rows}

    @staticmethod
    def invoice_rows(inv: "ParsedInvoice", source: str, anaf_id: str) -> tuple[list, list[list], list[list]]:
        fx = inv.fx_to_ron
        amount_ron = inv.payable_ron if fx is not None else (inv.payable if inv.currency == "RON" else None)
        head = [
            inv.invoice_key, anaf_id, inv.number, inv.type_code, inv.is_credit_note, inv.issue_date,
            inv.due_date, inv.currency, inv.supplier_cui, inv.supplier_vat_id, inv.supplier_name,
            inv.supplier_reg_no, inv.supplier_iban, inv.supplier_city, inv.buyer_cui, inv.buyer_name,
            inv.line_total, inv.tax_exclusive, inv.tax_total, inv.tax_inclusive, inv.payable, fx,
            amount_ron, inv.note, source, inv.xml_sha256, datetime.now(),
        ]
        lines = [
            [
                inv.invoice_key, ln.line_no, ln.item_name, ln.item_norm, ln.seller_item_id, ln.quantity,
                ln.unit_code, ln.unit_price, None if fx is None else ln.unit_price * fx, ln.base_quantity,
                ln.net_amount, None if fx is None else ln.net_amount * fx, ln.vat_category, ln.vat_rate, None,
            ]
            for ln in inv.lines
        ]
        vat = [[inv.invoice_key, v.category, v.rate, v.taxable, v.tax] for v in inv.vat]
        return head, lines, vat

    def bulk_insert(self, con, heads: list[list], lines: list[list], vat: list[list], logs: list[list]) -> None:
        for table, cols, rows in (
            ("invoices", self.INVOICE_COLS, heads),
            ("invoice_lines", self.LINE_COLS, lines),
            ("vat_breakdown", self.VAT_COLS, vat),
            ("import_log", ["logged_at", "source", "status", "message"], logs),
        ):
            if not rows:
                continue
            frame = pd.DataFrame(rows, columns=cols)
            if table == "invoices":
                for c in ("issue_date", "due_date"):
                    frame[c] = pd.to_datetime(frame[c]).dt.date
            con.register("_bulk", frame)
            con.execute(f"INSERT INTO {table} ({','.join(cols)}) SELECT {','.join(cols)} FROM _bulk")
            con.unregister("_bulk")

    # ------------------------------------------------------------------ reads
    def df(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self.connect(read_only=True) as con:
            return con.execute(sql, params or []).df()

    def scalar(self, sql: str, params: list | None = None) -> Any:
        with self.connect(read_only=True) as con:
            row = con.execute(sql, params or []).fetchone()
            return row[0] if row else None

    def invoices(self) -> pd.DataFrame:
        return self.df("SELECT * FROM invoices ORDER BY issue_date, invoice_key")

    def lines(self) -> pd.DataFrame:
        return self.df(
            """SELECT l.*, i.supplier_cui, i.supplier_name, i.issue_date, i.number, i.is_credit_note, i.currency
               FROM invoice_lines l JOIN invoices i USING (invoice_key)
               ORDER BY i.issue_date, l.invoice_key, l.line_no"""
        )

    def vat(self) -> pd.DataFrame:
        return self.df(
            """SELECT v.*, i.supplier_cui, i.supplier_name, i.issue_date, i.number
               FROM vat_breakdown v JOIN invoices i USING (invoice_key)"""
        )

    def count_invoices(self) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM invoices") or 0)

    # ------------------------------------------------------------------ flags
    def save_item_groups(self, mapping: pd.DataFrame) -> None:
        """mapping: columns invoice_key, line_no, item_group."""
        if mapping.empty:
            return
        with self.connect() as con:
            con.register("m", mapping)
            con.execute(
                """UPDATE invoice_lines SET item_group = m.item_group FROM m
                   WHERE invoice_lines.invoice_key = m.invoice_key AND invoice_lines.line_no = m.line_no"""
            )
            con.unregister("m")

    def replace_flags(self, run_id: str, flags: list[dict], started_at: datetime, n_invoices: int, params: dict) -> None:
        with self.connect() as con:
            con.execute("BEGIN")
            con.execute("DELETE FROM flags")
            if flags:
                cols = [
                    "flag_id", "run_id", "check_name", "rule", "severity", "score", "supplier_cui", "supplier_name",
                    "invoice_keys", "invoice_numbers", "issue_date", "amount_at_risk_ron", "title_en", "title_ro",
                    "evidence", "created_at",
                ]
                now = datetime.now()
                rows = []
                for f in flags:
                    rows.append([
                        f["flag_id"], run_id, f["check_name"], f["rule"], f["severity"], f["score"],
                        f.get("supplier_cui"), f.get("supplier_name"), json.dumps(f["invoice_keys"]),
                        json.dumps(f.get("invoice_numbers", [])), f.get("issue_date"), f.get("amount_at_risk_ron"),
                        f["title_en"], f["title_ro"], json.dumps(f["evidence"], ensure_ascii=False, default=str), now,
                    ])
                con.executemany(f"INSERT INTO flags ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
            con.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?)",
                [run_id, started_at, datetime.now(), n_invoices, len(flags), json.dumps(params, default=str)],
            )
            con.execute("COMMIT")

    def save_scores(self, scores: pd.DataFrame) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM invoice_scores")
            con.register("_s", scores)
            con.execute("INSERT INTO invoice_scores SELECT invoice_key, supplier_z, iforest, autoencoder, combined FROM _s")
            con.unregister("_s")

    def flags(self, include_dismissed: bool = False) -> pd.DataFrame:
        where = "" if include_dismissed else "WHERE status <> 'dismissed'"
        df = self.df(f"SELECT * FROM flags_view {where}")
        if df.empty:
            return df
        df["sev_rank"] = df["severity"].map(SEVERITY_ORDER).fillna(3)
        df = df.sort_values(["sev_rank", "score", "amount_at_risk_ron"], ascending=[True, False, False])
        return df.drop(columns="sev_rank").reset_index(drop=True)

    def set_feedback(self, flag_id: str, status: str, note: str = "") -> None:
        if status not in {"open", "confirmed", "dismissed"}:
            raise ValueError("status must be open, confirmed or dismissed")
        with self.connect() as con:
            row = con.execute("SELECT check_name, rule FROM flags WHERE flag_id = ?", [flag_id]).fetchone()
            check_name, rule = row if row else (None, None)
            con.execute(
                """INSERT INTO flag_feedback VALUES (?,?,?,?,?,?)
                   ON CONFLICT (flag_id) DO UPDATE SET status = excluded.status, note = excluded.note,
                   updated_at = excluded.updated_at""",
                [flag_id, check_name, rule, status, note, datetime.now()],
            )

    def feedback_stats(self) -> pd.DataFrame:
        """Confirmed vs dismissed per rule — the input for tuning thresholds."""
        return self.df(
            """SELECT check_name, rule,
                      SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
                      SUM(CASE WHEN status='dismissed' THEN 1 ELSE 0 END) AS dismissed
               FROM flag_feedback GROUP BY 1, 2 ORDER BY 1, 2"""
        )

    def reset(self) -> None:
        """Remove all invoices and flags (feedback is kept)."""
        with self.connect() as con:
            for t in ("invoices", "invoice_lines", "vat_breakdown", "flags", "runs", "import_log", "invoice_scores"):
                con.execute(f"DELETE FROM {t}")
