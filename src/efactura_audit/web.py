"""JSON API for the web app: the engine behind Clarifact (clarifact.ro), running in the browser (Pyodide).

The web worker calls ``Api.call(method, args_json)`` and gets JSON back (or ``bytes`` for reports).
Each public method returns what one screen needs, with the same queries as the Streamlit app, so
both show the same numbers. Uploaded files arrive as paths in the worker's file system.

    api = Api("/data")                        # workspace folder: audit.duckdb and config.toml
    api.call("load_demo", "{}")
    api.call("overview", '{"lang": "ro"}')
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import time
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import __version__
from .config import load_workspace
from .engine import CHECKS, run_audit
from .importer import import_paths, import_sources, iter_uploaded
from .store import Store
from .transform import project

_MIDNIGHT = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00(\.0+)?$")
LAYER_ORDER = ("sources", "staging", "intermediate", "marts", "other")
SQL_LIMIT = 5000
PRICE_FLAGS = """SELECT fi.invoice_key, f.severity, json_extract_string(f.evidence, '$.item_group') AS item_group
                 FROM fct_flags f JOIN fct_flag_invoices fi USING (flag_id)
                 WHERE f.check_name = 'price_increase' AND f.rule <> 'cross_supplier' AND f.status <> 'dismissed'"""


def _clean(v: Any) -> Any:
    """Make one value JSON-safe: NaN/NaT to null, numpy scalars to Python, dates to ISO strings."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        s = v.isoformat()
        return s[:10] if _MIDNIGHT.match(s) else s[:19]
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, np.ndarray):
        return [_clean(x) for x in v.tolist()]
    return v


def records(df: pd.DataFrame) -> list[dict]:
    """Rows as JSON-safe dicts. Values are not rounded: formatting is the UI's job."""
    cols = list(df.columns)
    return [{c: _clean(v) for c, v in zip(cols, row)} for row in df.itertuples(index=False, name=None)]


def table(df: pd.DataFrame) -> dict:
    """Columns plus rows as lists, for result grids (SQL box, table preview) where column order matters."""
    return {"columns": [str(c) for c in df.columns],
            "types": [str(t) for t in df.dtypes],
            "rows": [[_clean(v) for v in row] for row in df.itertuples(index=False, name=None)]}


class Api:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if sys.platform == "emscripten":   # in the browser the tested-model list lives with the data (OPFS)
            os.environ.setdefault("EFACTURA_MODELS", str(self.root / "approved_models.json"))
        self._progress: Callable[[str], None] | None = None   # set by the web worker for long calls
        self.hosted_url = ""   # the site's /api/assistant address, set by the web worker
        self.ws = load_workspace(self.root)
        self.store = Store(self.ws.db_path)

    # ------------------------------------------------------------------ dispatch
    def call(self, method: str, args_json: str = "{}") -> str | bytes:
        """Run one method. Returns JSON ``{"ok": true, "result": ...}`` or ``{"ok": false, "error": ...}``;
        report methods return the file's bytes instead."""
        fn = getattr(self, method, None) if not method.startswith("_") and method != "call" else None
        if fn is None or not callable(fn):
            return json.dumps({"ok": False, "error": f"Unknown method {method}"})
        try:
            result = fn(**json.loads(args_json or "{}"))
        except Exception as exc:  # noqa: BLE001 - every error goes back to the UI
            return json.dumps({"ok": False, "error": str(exc) or type(exc).__name__,
                               "trace": traceback.format_exc()[-2000:]})
        if isinstance(result, bytes):
            return result
        return json.dumps({"ok": True, "result": _clean(result)}, ensure_ascii=False, default=str)

    def _q(self, sql: str, params: list | tuple = ()) -> pd.DataFrame:
        return self.store.df(sql, list(params))

    def _n_invoices(self) -> int:
        return int(self._q("SELECT COUNT(*) AS n FROM fct_invoices")["n"].iloc[0])

    # ------------------------------------------------------------------ app state
    def status(self) -> dict:
        last = self._q("SELECT finished_at, n_flags FROM runs ORDER BY finished_at DESC LIMIT 1")
        open_flags = int(self._q("SELECT COUNT(*) AS n FROM fct_flags WHERE status <> 'dismissed'")["n"].iloc[0])
        return {"version": __version__, "invoices": self._n_invoices(), "open_flags": open_flags,
                "last_audit": str(last["finished_at"].iloc[0])[:16] if not last.empty else None,
                "buyer_cui": self.ws.section("company").get("buyer_cui", "")}

    def run_audit(self) -> dict:
        res = run_audit(self.store, self.ws.settings)
        return {"flags": len(res.flags), "seconds": res.seconds, "summary": res.summary()}

    def load_demo(self, seed: int = 7) -> dict:
        """Synthetic data (the same as the Streamlit app's demo): replaces everything except review feedback."""
        from .synthetic import write_dataset
        t0 = time.perf_counter()
        self.store.reset()
        with tempfile.TemporaryDirectory() as tmp:
            write_dataset(Path(tmp), seed=seed)
            imp = import_paths(self.store, [Path(tmp) / "spv_downloads"])
        res = run_audit(self.store, self.ws.settings)
        return {"imported": imp.imported, "flags": len(res.flags), "seconds": time.perf_counter() - t0}

    def import_files(self, paths: list[str], buyer_cui: str = "") -> dict:
        """Import uploaded ZIP/XML files (paths in the worker's file system), then re-run the audit."""
        def sources():
            for p in paths:
                path = Path(p)
                yield from iter_uploaded(path.name, path.read_bytes())
        # the worker stores uploads as "<n>-<original name>"; the import history shows the original names
        label = ", ".join(re.sub(r"^\d+-", "", Path(p).name) for p in paths)
        imp = import_sources(self.store, sources(), buyer_cui, label=label)
        res = run_audit(self.store, self.ws.settings)
        return {"summary": imp.summary(), "import_id": imp.import_id, "imported": imp.imported, "duplicates": imp.duplicates,
                "skipped": imp.skipped, "other_buyer": imp.other_buyer, "failed": imp.failed,
                "errors": imp.errors[:10], "flags": len(res.flags)}

    def reset(self, include_feedback: bool = False) -> dict:
        """Start fresh: delete all invoices, flags and import history (and the reviews, if asked)."""
        self.store.reset(include_feedback=include_feedback)
        return {"invoices": 0}

    def imports(self) -> list[dict]:
        return records(self.store.imports())

    def delete_import(self, import_id: str | None = None) -> dict:
        """Remove one import's invoices (None: invoices imported before imports were tracked), then re-audit."""
        removed = self.store.delete_import(import_id)
        res = run_audit(self.store, self.ws.settings)
        return {"removed": removed, "flags": len(res.flags)}

    def buyers(self) -> list[dict]:
        return records(self.store.buyers())

    def keep_buyer(self, buyer_cui: str | None) -> dict:
        """Keep only the invoices addressed to one company, then re-audit."""
        removed = self.store.keep_buyer(buyer_cui)
        res = run_audit(self.store, self.ws.settings)
        return {"removed": removed, "flags": len(res.flags)}

    # ------------------------------------------------------------------ overview
    def overview(self, lang: str = "ro") -> dict:
        from .assistant.tools import AuditTools
        if self._n_invoices() == 0:
            return {"empty": True}
        ov = AuditTools(self.store, lang).audit_overview()
        flags = self.store.flags(include_dismissed=False)
        by_check = {k: int((flags["check_name"] == k).sum()) if not flags.empty else 0 for k in CHECKS}
        monthly = self._q("""SELECT month, SUM(spend_ron) AS spend, SUM(invoices) AS n
                             FROM mart_supplier_monthly_spend GROUP BY 1 ORDER BY 1""")
        top = flags.head(10)
        return {"empty": False, "overview": ov, "flags_by_check": by_check, "monthly": records(monthly),
                "top_flags": records(top[["flag_id", "severity", "check_name", "supplier_name",
                                          "amount_at_risk_ron", "title_ro", "title_en"]]) if not top.empty else []}

    # ------------------------------------------------------------------ flags
    def flags(self, include_dismissed: bool = False) -> list[dict]:
        """Every flag, most important first, with evidence parsed; the UI filters."""
        df = self.store.flags(include_dismissed=include_dismissed)
        if df.empty:
            return []
        out = records(df)
        for r in out:
            for k in ("evidence", "invoice_keys", "invoice_numbers"):
                r[k] = json.loads(r[k]) if r.get(k) else ([] if k != "evidence" else {})
        return out

    def flag_invoices(self, flag_id: str) -> list[dict]:
        """The invoices involved in a flag (first 6), each with its lines."""
        row = self._q("SELECT invoice_keys FROM fct_flags WHERE flag_id = ?", [flag_id])
        if row.empty:
            return []
        out = []
        for key in json.loads(row["invoice_keys"].iloc[0])[:6]:
            h = self._q("""SELECT invoice_key, number, issue_date, supplier_name, amount_ron, currency, payable, anaf_id
                           FROM fct_invoices WHERE invoice_key = ?""", [key])
            if h.empty:
                continue
            lines = self._q("""SELECT item_name, quantity, unit_code, unit_price, net_amount, vat_rate FROM fct_invoice_lines
                               WHERE invoice_key = ? ORDER BY TRY_CAST(line_no AS INTEGER)""", [key])
            inv = records(h)[0]
            inv["lines"] = table(lines)
            out.append(inv)
        return out

    def set_feedback(self, flag_id: str, status: str, note: str = "") -> dict:
        self.store.set_feedback(flag_id, status, note)
        return {"flag_id": flag_id, "status": status}

    # ------------------------------------------------------------------ invoices
    def search_invoices(self, supplier: str | None = None, number: str | None = None, date_from: str | None = None,
                        date_to: str | None = None, flagged_only: bool = False, lang: str = "ro") -> dict:
        from .assistant.tools import AuditTools
        res = AuditTools(self.store, lang).search_invoices(
            supplier=supplier or None, number=number or None, date_from=date_from or None, date_to=date_to or None,
            flagged_only=flagged_only, limit=100)
        return res

    def get_invoice(self, number: str, supplier_cui: str | None = None, lang: str = "ro") -> dict:
        from .assistant.tools import AuditTools
        return AuditTools(self.store, lang).get_invoice(number, supplier_cui)

    # ------------------------------------------------------------------ suppliers
    def suppliers(self) -> list[dict]:
        return records(self._q("""SELECT supplier_name, supplier_cui, invoices, ROUND(total_spend_ron, 2) AS spend_ron,
                                         first_invoice, last_invoice, flags
                                  FROM dim_suppliers ORDER BY spend_ron DESC"""))

    def supplier(self, cui: str, lang: str = "ro") -> dict:
        from .assistant.tools import AuditTools
        res = AuditTools(self.store, lang).supplier_summary(cui)
        return res["suppliers"][0] if res.get("suppliers") else res

    # ------------------------------------------------------------------ import tab
    def import_info(self) -> dict:
        tests = self._q("""SELECT status, test_name, model, failures, message FROM data_test_results
                           ORDER BY status = 'pass', test_name""")
        log = self._q("SELECT logged_at, status, source, message FROM import_log ORDER BY logged_at DESC LIMIT 200")
        return {"tests": records(tests), "log": records(log)}

    # ------------------------------------------------------------------ data tab
    def catalog(self) -> list[dict]:
        """Every table and view: layer, rows, columns, description."""
        p = project()
        objs = self._q("""SELECT t.table_name AS name, COUNT(c.column_name) AS n_columns
                          FROM information_schema.tables t JOIN information_schema.columns c USING (table_schema, table_name)
                          WHERE t.table_schema = 'main' GROUP BY 1""")
        rows = []
        for name, n_cols in zip(objs["name"], objs["n_columns"]):
            if name in p.models:
                layer, desc = p.models[name].layer, p.models[name].description
            elif name in p.source_docs:
                layer, desc = "sources", p.source_docs[name]
            else:
                layer, desc = "other", ""
            n = int(self._q(f'SELECT COUNT(*) AS n FROM "{name}"')["n"].iloc[0])
            rows.append({"layer": layer, "name": name, "rows": n, "columns": int(n_cols), "description": desc})
        rows.sort(key=lambda r: (LAYER_ORDER.index(r["layer"]), r["name"]))
        return rows

    def lineage(self) -> dict:
        """The model graph: layer groups (sources, staging, intermediate, marts) and edges upstream -> model."""
        p = project()
        groups = {"sources": sorted({t for m in p.models.values() for t in m.source_tables})}
        groups.update({layer: sorted(m.name for m in p.layer(layer)) for layer in ("staging", "intermediate", "marts")})
        edges = [[up, m.name] for m in p.models.values() for up in sorted(m.source_tables | m.refs)]
        return {"groups": groups, "edges": edges}

    def table_detail(self, name: str) -> dict:
        p = project()
        known = set(self._q("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")["table_name"])
        if name not in known:
            raise ValueError(f"Unknown table {name}")
        model = p.models.get(name)
        cols = self._q("""SELECT column_name, data_type, comment FROM duckdb_columns()
                          WHERE schema_name = 'main' AND table_name = ? ORDER BY column_index""", [name])
        specs = model.columns if model else {}
        cols["tests"] = cols["column_name"].map(
            lambda c: ", ".join(t if isinstance(t, str) else next(iter(t)) for t in specs.get(c, {}).get("tests", [])))
        cols["comment"] = cols["comment"].fillna("")
        return {"name": name, "layer": model.layer if model else ("sources" if name in p.source_docs else "other"),
                "description": model.description if model else p.source_docs.get(name, ""),
                "columns": records(cols), "preview": table(self._q(f'SELECT * FROM "{name}" LIMIT 500')),
                "sql": model.raw_sql.strip() if model else None}

    def spend_heatmap(self) -> dict:
        m = self._q("""SELECT d.supplier_name, m.month, m.spend_ron, d.total_spend_ron
                       FROM mart_supplier_monthly_spend m JOIN dim_suppliers d USING (supplier_cui)""")
        if m.empty:
            return {"suppliers": [], "months": [], "z": [], "zmax": None}
        order = m.groupby("supplier_name")["total_spend_ron"].max().sort_values().index   # largest on top
        pv = m.pivot_table(index="supplier_name", columns="month", values="spend_ron", aggfunc="sum").reindex(order)
        z = pv.to_numpy()
        positive = z[np.isfinite(z) & (z > 0)]
        # one extreme month would wash out every other cell: saturate above the 95th percentile
        zmax = float(np.percentile(positive, 95)) if positive.size else None
        return {"suppliers": list(pv.index), "months": [str(c) for c in pv.columns], "z": _clean(z), "zmax": zmax}

    def chart_suppliers(self) -> dict:
        """Suppliers for the Data charts picker, and the default: the one with the most high flags."""
        sups = self._q("""SELECT supplier_cui, supplier_name, flags, high_flags
                          FROM dim_suppliers ORDER BY total_spend_ron DESC""")
        if sups.empty:
            return {"suppliers": [], "default": None}
        busiest = sups.sort_values(["high_flags", "flags"], ascending=False).iloc[0]["supplier_cui"]
        return {"suppliers": records(sups), "default": busiest}

    def supplier_invoices(self, cui: str) -> dict:
        inv = self._q("""SELECT i.number, i.issue_date, i.spend_ron, i.is_credit_note, f.sev_rank, f.checks
                         FROM fct_invoices i
                         LEFT JOIN (SELECT invoice_key,
                                           MIN(CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END) AS sev_rank,
                                           string_agg(DISTINCT check_name, ', ') AS checks
                                    FROM fct_flag_invoices WHERE status <> 'dismissed' GROUP BY 1) f USING (invoice_key)
                         WHERE i.supplier_cui = ? ORDER BY i.issue_date""", [cui])
        inv["severity"] = inv["sev_rank"].map({0: "high", 1: "medium", 2: "low"})
        normal = inv.loc[~inv["is_credit_note"].astype(bool), "spend_ron"]
        return {"invoices": records(inv.drop(columns="sev_rank")),
                "median": float(normal.median()) if not normal.empty else None}

    def supplier_items(self, cui: str) -> list[dict]:
        """Items bought at least 3 times from the supplier; ones with price flags first."""
        items = self._q("""SELECT item_group, ANY_VALUE(item_label) AS label, COUNT(*) AS n
                           FROM fct_invoice_lines
                           WHERE supplier_cui = ? AND NOT is_credit_note AND price_ron IS NOT NULL AND item_group IS NOT NULL
                           GROUP BY 1 HAVING COUNT(*) >= 3""", [cui])
        if items.empty:
            return []
        flags = self._q(PRICE_FLAGS)
        items["flagged"] = items["item_group"].isin(set(flags["item_group"]))
        return records(items.sort_values(["flagged", "n"], ascending=False))

    def item_prices(self, item_group: str) -> list[dict]:
        pts = self._q("""SELECT invoice_key, number, issue_date, price_ron, quantity FROM fct_invoice_lines
                         WHERE item_group = ? AND NOT is_credit_note AND price_ron IS NOT NULL
                         ORDER BY issue_date, invoice_key""", [item_group])
        flags = self._q(PRICE_FLAGS)
        sev = flags[flags["item_group"] == item_group].groupby("invoice_key")["severity"].agg(
            lambda s: min(s, key=["high", "medium", "low"].index))
        pts["severity"] = pts["invoice_key"].map(sev)
        return records(pts)

    def data_tests(self) -> dict:
        res = self._q("""SELECT status, test_name, model, severity, failures, message, run_at FROM data_test_results
                         ORDER BY CASE status WHEN 'error' THEN 0 WHEN 'fail' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END, test_name""")
        sql = {t.name: t.sql for t in project().tests()}
        out = records(res)
        for r in out:
            r["sql"] = sql.get(r["test_name"])
        return {"tests": out, "run_at": out[0]["run_at"][:16] if out else None}

    def rerun_tests(self) -> dict:
        self.store.run_data_tests()
        return self.data_tests()

    def failing_rows(self, test_name: str) -> dict:
        tests = {t.name: t for t in project().tests()}
        if test_name not in tests:
            raise ValueError(f"Unknown test {test_name}")
        return table(self._q(f"SELECT * FROM ({tests[test_name].sql}) LIMIT 100"))

    def sql(self, query: str) -> dict:
        from .assistant.tools import readonly_select
        return table(readonly_select(self.store, query, limit=SQL_LIMIT))

    def marts(self) -> list[str]:
        return [m.name for m in project().layer("marts")]

    # ------------------------------------------------------------------ report
    def report(self, kind: str, lang: str = "ro") -> bytes:
        from .report import excel_report, pdf_report
        if kind == "xlsx":
            return excel_report(self.store, lang)
        if kind == "pdf":
            return pdf_report(self.store, lang)
        raise ValueError("kind must be xlsx or pdf")

    # ------------------------------------------------------------------ assistant
    def _assistant_cfg(self) -> dict:
        return self.ws.section("assistant")

    def _ollama_url(self) -> str:
        return self._assistant_cfg().get("ollama_url", "http://localhost:11434")

    def assistant_options(self, provider: str | None = None, cloud_enabled: bool = False, allow_untested: bool = False,
                          dev_mode: bool = False, hosted_model: str | None = None, hosted_approved: bool = False) -> dict:
        """Providers on offer and the models of the chosen one (Romanian-tested first, untested only when allowed).

        Users see only the site's own assistant (``hosted_model``, reported by /api/assistant/info). Ollama and
        cloud models with the user's own key are developer options."""
        from .assistant.evaluation import approved_models
        from .assistant.providers import CLOUD_PROVIDERS, HOSTED, SUGGESTED_MODELS, ollama_models
        providers = ([HOSTED] if hosted_model else []) + (
            ["ollama"] + (sorted(CLOUD_PROVIDERS) if cloud_enabled else []) if dev_mode else [])
        if provider not in providers:
            provider = providers[0] if providers else None
        untested = allow_untested and dev_mode
        approved = [m["model"] for m in approved_models(self.ws) if m["provider"] == provider]
        if provider == HOSTED:
            ok = hosted_approved or hosted_model in approved
            models = [{"model": hosted_model, "approved": ok}] if ok or untested else []
        else:
            options = list(approved)
            if untested and provider:
                extra = ollama_models(self._ollama_url()) if provider == "ollama" else []
                options += [m for m in extra + SUGGESTED_MODELS.get(provider, []) if m not in options]
            models = [{"model": m, "approved": m in approved} for m in options]
        return {"providers": providers, "provider": provider, "cloud": sorted(CLOUD_PROVIDERS), "models": models,
                "hosted_untested": provider == HOSTED and not models}

    def ask(self, provider: str, model: str, question: str, history: list[dict] | None = None,
            api_key: str = "", lang: str = "ro") -> dict:
        """One assistant answer with the tool calls it was built from. The key is used for this call only."""
        from .assistant.agent import Assistant
        from .assistant.backends import LocalBackend
        from .assistant.providers import make_provider
        from .assistant.tools import AuditTools
        tools = AuditTools(self.store, lang)
        prov = make_provider(provider, model, api_key, self._base_url(provider))
        ans = Assistant(prov, LocalBackend(tools), tools.audit_overview(),
                        int(self._assistant_cfg().get("max_tool_rounds", 6))).ask(question, history or [])
        return {"text": ans.text, "error": ans.error,
                "trace": [{"name": t.name, "arguments": t.arguments, "result": t.result} for t in ans.trace]}

    def _base_url(self, provider: str) -> str:
        from .assistant.providers import HOSTED
        return self._ollama_url() if provider == "ollama" else self.hosted_url if provider == HOSTED else ""

    def ollama_status(self) -> dict:
        from .assistant.providers import ollama_models
        return {"url": self._ollama_url(), "models": ollama_models(self._ollama_url())}

    def model_suggestions(self, provider: str) -> list[str]:
        from .assistant.providers import SUGGESTED_MODELS, ollama_models
        installed = ollama_models(self._ollama_url()) if provider == "ollama" else []
        return list(dict.fromkeys(installed + SUGGESTED_MODELS.get(provider, [])))

    def model_test(self, provider: str, model: str, api_key: str = "") -> dict:
        """Run the Romanian task set on synthetic data; passing models are offered in the assistant."""
        from .assistant.evaluation import run_model_test, save_result
        from .assistant.providers import make_provider
        prov = make_provider(provider, model, api_key, self._base_url(provider))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_model_test(prov, Path(tmp), progress=self._progress)
        save_result(self.ws, result)
        return {"passed": result.passed, "summary": result.summary()}

    def tested_models(self) -> list[dict]:
        from .assistant.evaluation import load_approved
        keys = ("provider", "model", "score", "structured_ok", "passed", "tested_at")
        return [{k: m.get(k) for k in keys} for m in load_approved(self.ws)]

    # ------------------------------------------------------------------ settings
    def settings(self) -> dict:
        fb = self.store.feedback_stats()
        cfg = self._assistant_cfg()
        return {"settings": self.ws.settings, "feedback": records(fb), "config_path": str(self.ws.config_path),
                "cloud_enabled": bool(cfg.get("cloud_enabled", False)),
                "allow_untested": bool(cfg.get("allow_untested_models", False))}

