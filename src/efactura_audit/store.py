"""Local DuckDB invoice store.

Tables here are written by Python: ``raw_*`` by the importer, ``item_groups``, ``flags`` and the
run tables by the audit engine, ``flag_feedback`` by reviewers. Everything that reads data goes
through the dbt-style SQL models in ``transform/`` (staging -> intermediate -> marts), views built
on top of these tables.

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

from .transform import TestResult, project

if TYPE_CHECKING:
    from .importer.parser import ParsedInvoice

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS raw_invoices (
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
        imported_at TIMESTAMP,
        import_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS imports (
        import_id VARCHAR PRIMARY KEY,
        imported_at TIMESTAMP,
        sources VARCHAR,
        buyer_filter VARCHAR,
        imported INTEGER,
        duplicates INTEGER,
        skipped INTEGER,
        other_buyer INTEGER,
        failed INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_invoice_lines (
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
        vat_rate DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_vat_breakdown (
        invoice_key VARCHAR,
        category VARCHAR,
        rate DOUBLE,
        taxable DOUBLE,
        tax DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_groups (
        invoice_key VARCHAR,
        line_no VARCHAR,
        item_group VARCHAR,
        item_label VARCHAR,
        xgroup VARCHAR
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
    CREATE TABLE IF NOT EXISTS data_test_results (
        run_at TIMESTAMP,
        test_name VARCHAR,
        model VARCHAR,
        severity VARCHAR,
        status VARCHAR,
        failures INTEGER,
        message VARCHAR
    )
    """,
]

RESET_TABLES = ("raw_invoices", "raw_invoice_lines", "raw_vat_breakdown", "item_groups", "flags", "runs", "import_log",
                "invoice_scores", "data_test_results", "imports")


def _migrate_legacy(con) -> None:
    """0.1.x workspaces stored invoices in ``invoices``/``invoice_lines``/``vat_breakdown`` and wrote
    item groups into the lines table: rename them to the raw sources and move item groups out."""
    tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    if "invoices" not in tables or "raw_invoices" in tables:
        return
    con.execute("BEGIN")
    con.execute("DROP VIEW IF EXISTS flags_view")
    for old in ("invoices", "invoice_lines", "vat_breakdown"):
        con.execute(f"ALTER TABLE {old} RENAME TO raw_{old}")
    con.execute(next(s for s in SCHEMA if "item_groups" in s))
    con.execute("""INSERT INTO item_groups SELECT invoice_key, line_no, item_group, NULL, NULL
                   FROM raw_invoice_lines WHERE item_group IS NOT NULL""")
    con.execute("COMMIT")
    con.execute("ALTER TABLE raw_invoice_lines DROP COLUMN item_group")

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
            _migrate_legacy(con)
            for stmt in SCHEMA:
                con.execute(stmt)
            # workspaces from before import tracking: their invoices get no import id ("earlier imports")
            con.execute("ALTER TABLE raw_invoices ADD COLUMN IF NOT EXISTS import_id VARCHAR")
            project().build(con)

    # ------------------------------------------------------------------ models ("dbt build")
    def build_models(self, force: bool = False) -> bool:
        with self.connect() as con:
            return project().build(con, force=force)

    def run_data_tests(self) -> list[TestResult]:
        """Run the data tests, keep the results in ``data_test_results`` and return them."""
        with self.connect() as con:
            results = project().run_tests(con)
            now = datetime.now()
            con.execute("BEGIN")
            con.execute("DELETE FROM data_test_results")
            if results:
                con.executemany("INSERT INTO data_test_results VALUES (?,?,?,?,?,?,?)",
                                [[now, r.name, r.model, r.severity, r.status, r.failures, r.message] for r in results])
            con.execute("COMMIT")
        return results

    # ------------------------------------------------------------------ import
    INVOICE_COLS = [
        "invoice_key", "anaf_id", "number", "type_code", "is_credit_note", "issue_date", "due_date", "currency",
        "supplier_cui", "supplier_vat_id", "supplier_name", "supplier_reg_no", "supplier_iban", "supplier_city",
        "buyer_cui", "buyer_name", "line_total", "tax_exclusive", "tax_total", "tax_inclusive", "payable",
        "fx_to_ron", "amount_ron", "note", "source_file", "xml_sha256", "imported_at", "import_id",
    ]
    LINE_COLS = [
        "invoice_key", "line_no", "item_name", "item_norm", "seller_item_id", "quantity", "unit_code", "unit_price",
        "unit_price_ron", "base_quantity", "net_amount", "net_amount_ron", "vat_category", "vat_rate",
    ]
    VAT_COLS = ["invoice_key", "category", "rate", "taxable", "tax"]

    def existing_keys(self, con) -> tuple[set[str], set[str]]:
        rows = con.execute("SELECT invoice_key, xml_sha256 FROM raw_invoices").fetchall()
        return {r[0] for r in rows}, {r[1] for r in rows}

    @staticmethod
    def invoice_rows(inv: "ParsedInvoice", source: str, anaf_id: str, import_id: str = "") -> tuple[list, list[list], list[list]]:
        fx = inv.fx_to_ron
        amount_ron = inv.payable_ron if fx is not None else (inv.payable if inv.currency == "RON" else None)
        head = [
            inv.invoice_key, anaf_id, inv.number, inv.type_code, inv.is_credit_note, inv.issue_date,
            inv.due_date, inv.currency, inv.supplier_cui, inv.supplier_vat_id, inv.supplier_name,
            inv.supplier_reg_no, inv.supplier_iban, inv.supplier_city, inv.buyer_cui, inv.buyer_name,
            inv.line_total, inv.tax_exclusive, inv.tax_total, inv.tax_inclusive, inv.payable, fx,
            amount_ron, inv.note, source, inv.xml_sha256, datetime.now(), import_id or None,
        ]
        lines = [
            [
                inv.invoice_key, ln.line_no, ln.item_name, ln.item_norm, ln.seller_item_id, ln.quantity,
                ln.unit_code, ln.unit_price, None if fx is None else ln.unit_price * fx, ln.base_quantity,
                ln.net_amount, None if fx is None else ln.net_amount * fx, ln.vat_category, ln.vat_rate,
            ]
            for ln in inv.lines
        ]
        vat = [[inv.invoice_key, v.category, v.rate, v.taxable, v.tax] for v in inv.vat]
        return head, lines, vat

    def bulk_insert(self, con, heads: list[list], lines: list[list], vat: list[list], logs: list[list]) -> None:
        for table, cols, rows in (
            ("raw_invoices", self.INVOICE_COLS, heads),
            ("raw_invoice_lines", self.LINE_COLS, lines),
            ("raw_vat_breakdown", self.VAT_COLS, vat),
            ("import_log", ["logged_at", "source", "status", "message"], logs),
        ):
            if not rows:
                continue
            frame = pd.DataFrame(rows, columns=cols)
            if table == "raw_invoices":
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

    def count_invoices(self) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM raw_invoices") or 0)

    # ------------------------------------------------------------------ flags
    def save_item_groups(self, groups: pd.DataFrame) -> None:
        """Replace the item-matching output. Columns: invoice_key, line_no, item_group, item_label, xgroup."""
        with self.connect() as con:
            con.execute("BEGIN")
            con.execute("DELETE FROM item_groups")
            if not groups.empty:
                con.register("_g", groups)
                con.execute("INSERT INTO item_groups SELECT invoice_key, line_no, item_group, item_label, xgroup FROM _g")
                con.unregister("_g")
            con.execute("COMMIT")

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
        df = self.df(f"SELECT * FROM fct_flags {where}")
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

    def reset(self, include_feedback: bool = False) -> None:
        """Remove all invoices, flags and import history. Review feedback is kept unless asked: flag IDs are
        stable, so kept reviews apply again when the same invoices are imported."""
        with self.connect() as con:
            for t in RESET_TABLES + (("flag_feedback",) if include_feedback else ()):
                con.execute(f"DELETE FROM {t}")

    # ------------------------------------------------------------------ import history
    def record_import(self, con, row: list) -> None:
        con.execute("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?)", row)

    def imports(self) -> pd.DataFrame:
        """One row per import, newest first, with the invoices it still holds. Invoices imported before
        imports were tracked form one row with an empty import_id."""
        return self.df("""
            WITH kept AS (SELECT import_id, COUNT(*) AS invoices FROM raw_invoices GROUP BY 1)
            SELECT i.import_id, i.imported_at, i.sources, i.buyer_filter, i.imported, i.duplicates, i.skipped,
                   i.other_buyer, i.failed, COALESCE(k.invoices, 0) AS invoices_kept
            FROM imports i LEFT JOIN kept k USING (import_id)
            UNION ALL
            SELECT NULL, MIN(imported_at), NULL, NULL, COUNT(*), NULL, NULL, NULL, NULL, COUNT(*)
            FROM raw_invoices WHERE import_id IS NULL HAVING COUNT(*) > 0
            ORDER BY imported_at DESC""")

    def _delete_invoices(self, con, where: str, params: list) -> int:
        keys = f"SELECT invoice_key FROM raw_invoices WHERE {where}"
        n = con.execute(f"SELECT COUNT(*) FROM raw_invoices WHERE {where}", params).fetchone()[0]
        con.execute(f"DELETE FROM raw_invoice_lines WHERE invoice_key IN ({keys})", params)
        con.execute(f"DELETE FROM raw_vat_breakdown WHERE invoice_key IN ({keys})", params)
        con.execute(f"DELETE FROM raw_invoices WHERE {where}", params)
        return int(n)

    def delete_import(self, import_id: str | None) -> int:
        """Remove one import's invoices (None: the untracked earlier imports). Run the audit afterwards."""
        with self.connect() as con:
            con.execute("BEGIN")
            if import_id:
                n = self._delete_invoices(con, "import_id = ?", [import_id])
                con.execute("DELETE FROM imports WHERE import_id = ?", [import_id])
            else:
                n = self._delete_invoices(con, "import_id IS NULL", [])
            con.execute("COMMIT")
        return n

    def buyers(self) -> pd.DataFrame:
        return self.df("""SELECT buyer_cui, ANY_VALUE(buyer_name) AS buyer_name, COUNT(*) AS invoices
                          FROM raw_invoices GROUP BY 1 ORDER BY invoices DESC""")

    def keep_buyer(self, buyer_cui: str) -> int:
        """Delete every invoice addressed to another buyer. Run the audit afterwards."""
        with self.connect() as con:
            con.execute("BEGIN")
            n = self._delete_invoices(con, "buyer_cui IS DISTINCT FROM ?", [buyer_cui])
            con.execute("COMMIT")
        return n
