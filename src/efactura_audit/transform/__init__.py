"""dbt-style SQL models over the invoice store, built in DuckDB without a dbt dependency.

Layout, as in a dbt project:

    models/sources.yml          tables written by Python (importer, audit engine, reviewers)
    models/staging/*.sql        one view per source table: types, defaults, no joins
    models/intermediate/*.sql   joins and features the checks consume
    models/marts/*.sql          what the app, reports and assistant read
    models/**/*.yml             descriptions and generic tests (not_null, unique, accepted_values, relationships)
    data_tests/*.sql            singular tests: each query returns the failing rows

SQL uses ``{{ ref('model') }}``, ``{{ source('name', 'table') }}`` and an optional
``{{ config(severity='warn') }}`` in tests, so the files can move to real dbt-duckdb later with
little change. Every model is a view: the data is small (a company's supplier invoices) and views
are always current, so imports and audits never need a separate rebuild step. Views are recreated
only when the model files change (tracked by a fingerprint in ``_model_build``).
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parent
RUNNER_VERSION = "1"

_REF = re.compile(r"\{\{\s*ref\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
_SOURCE = re.compile(r"\{\{\s*source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}")
_CONFIG = re.compile(r"\{\{\s*config\((.*?)\)\s*\}\}", re.S)
_CONFIG_ARG = re.compile(r"(\w+)\s*=\s*['\"]([^'\"]*)['\"]")
_REF_ARG = re.compile(r"ref\(\s*['\"](\w+)['\"]\s*\)")


class ProjectError(ValueError):
    """The model files are inconsistent (unknown ref, cycle, bad YAML)."""


@dataclass
class Model:
    name: str
    path: Path
    layer: str                      # staging, intermediate, marts
    raw_sql: str
    refs: set[str]
    description: str = ""
    columns: dict[str, dict[str, Any]] = field(default_factory=dict)   # name -> {description, tests}
    source_tables: set[str] = field(default_factory=set)              # physical tables read via source()


@dataclass
class DataTest:
    name: str
    model: str | None
    sql: str                        # compiled; returns the failing rows
    severity: str = "error"         # error | warn
    description: str = ""


@dataclass
class TestResult:
    name: str
    model: str | None
    severity: str
    status: str                     # pass | warn | fail | error
    failures: int
    message: str = ""


def _leading_comment(sql: str) -> str:
    out = []
    for line in sql.lstrip().splitlines():
        if not line.startswith("--"):
            break
        out.append(line[2:].strip())
    return " ".join(out).strip()


def _config(sql: str) -> dict[str, str]:
    m = _CONFIG.search(sql)
    return dict(_CONFIG_ARG.findall(m.group(1))) if m else {}


def _quote(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


class Project:
    """Models, sources and tests read from the package (or another folder with the same layout)."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.sources: dict[tuple[str, str], str] = {}        # (source, table) -> physical table
        self.source_docs: dict[str, str] = {}                # physical table -> description
        self.models: dict[str, Model] = {}
        self._load()

    # ------------------------------------------------------------------ loading
    def _load(self) -> None:
        models_dir = self.root / "models"
        for path in sorted(models_dir.rglob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            name = path.stem
            if name in self.models:
                raise ProjectError(f"Duplicate model name {name}")
            layer = path.relative_to(models_dir).parts[0]
            self.models[name] = Model(name, path, layer, sql, set(_REF.findall(sql)), _leading_comment(sql))
        for path in sorted(models_dir.rglob("*.yml")):
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise ProjectError(f"{path.name}: {exc}") from exc
            for src in doc.get("sources", []):
                for t in src.get("tables", []):
                    ident = t.get("identifier", t["name"])
                    self.sources[(src["name"], t["name"])] = ident
                    self.source_docs[ident] = t.get("description", "")
            for m in doc.get("models", []):
                model = self.models.get(m["name"])
                if model is None:
                    raise ProjectError(f"{path.name} documents unknown model {m['name']}")
                model.description = m.get("description", model.description)
                for c in m.get("columns", []):
                    model.columns[c["name"]] = {"description": c.get("description", ""),
                                                "tests": c.get("data_tests", c.get("tests", []))}
        for m in self.models.values():
            missing = m.refs - set(self.models)
            if missing:
                raise ProjectError(f"{m.name} refs unknown model(s): {', '.join(sorted(missing))}")
            for src in _SOURCE.findall(m.raw_sql):
                if src not in self.sources:
                    raise ProjectError(f"{m.name} reads unknown source {src[0]}.{src[1]}")
                m.source_tables.add(self.sources[src])

    def compile(self, sql: str) -> str:
        def source(match: re.Match) -> str:
            key = (match.group(1), match.group(2))
            if key not in self.sources:
                raise ProjectError(f"Unknown source {key[0]}.{key[1]}")
            return self.sources[key]

        sql = _CONFIG.sub("", sql)
        sql = _SOURCE.sub(source, sql)
        return _REF.sub(lambda m: m.group(1), sql).strip().rstrip(";")

    def order(self) -> list[Model]:
        try:
            names = list(TopologicalSorter({m.name: m.refs for m in self.models.values()}).static_order())
        except CycleError as exc:
            raise ProjectError(f"Model cycle: {exc.args[1]}") from exc
        return [self.models[n] for n in names]

    def fingerprint(self) -> str:
        h = hashlib.sha256(RUNNER_VERSION.encode())
        for path in sorted((self.root / "models").rglob("*")):
            if path.is_file():
                h.update(path.relative_to(self.root).as_posix().encode())
                h.update(path.read_bytes())
        return h.hexdigest()[:16]

    def layer(self, layer: str) -> list[Model]:
        return [m for m in self.order() if m.layer == layer]

    # ------------------------------------------------------------------ build ("dbt run")
    def build(self, con, force: bool = False) -> bool:
        """Create or replace every model view in dependency order. Returns False when nothing changed."""
        fp = self.fingerprint()
        con.execute("CREATE TABLE IF NOT EXISTS _model_build (fingerprint VARCHAR, models VARCHAR, built_at TIMESTAMP)")
        row = con.execute("SELECT fingerprint, models FROM _model_build").fetchone()
        if row and row[0] == fp and not force:
            return False
        con.execute("BEGIN")
        try:
            # views of models that were renamed or removed would otherwise linger
            for old in set(json.loads(row[1]) if row else []) - set(self.models):
                con.execute(f"DROP VIEW IF EXISTS {old}")
            for m in self.order():
                con.execute(f"CREATE OR REPLACE VIEW {m.name} AS\n{self.compile(m.raw_sql)}")
                if m.description:
                    con.execute(f"COMMENT ON VIEW {m.name} IS {_quote(m.description)}")
                for col, spec in m.columns.items():
                    if spec["description"]:
                        con.execute(f"COMMENT ON COLUMN {m.name}.{col} IS {_quote(spec['description'])}")
            con.execute("DELETE FROM _model_build")
            con.execute("INSERT INTO _model_build VALUES (?, ?, ?)", [fp, json.dumps(sorted(self.models)), datetime.now()])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        return True

    # ------------------------------------------------------------------ tests ("dbt test")
    def tests(self) -> list[DataTest]:
        out: list[DataTest] = []
        for m in self.order():
            for col, spec in m.columns.items():
                for t in spec["tests"]:
                    out.append(self._generic_test(m.name, col, t))
        for path in sorted((self.root / "data_tests").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            refs = _REF.findall(sql)
            out.append(DataTest(path.stem, refs[0] if refs else None, self.compile(sql),
                                _config(sql).get("severity", "error"), _leading_comment(sql)))
        return out

    def _generic_test(self, model: str, col: str, spec: str | dict) -> DataTest:
        kind, args = (spec, {}) if isinstance(spec, str) else next(iter(spec.items()))
        args = dict(args or {})
        severity = (args.pop("config", None) or {}).get("severity", args.pop("severity", "error"))
        if kind == "not_null":
            sql = f"SELECT * FROM {model} WHERE {col} IS NULL"
        elif kind == "unique":
            sql = f"SELECT {col} FROM {model} WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*) > 1"
        elif kind == "accepted_values":
            values = ", ".join(_quote(v) for v in args["values"])
            sql = f"SELECT * FROM {model} WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) NOT IN ({values})"
        elif kind == "relationships":
            m = _REF_ARG.search(str(args["to"]))
            if not m or m.group(1) not in self.models:
                raise ProjectError(f"{model}.{col}: relationships needs to: ref('<model>')")
            to, fld = m.group(1), args["field"]
            sql = (f"SELECT c.* FROM {model} c WHERE c.{col} IS NOT NULL "
                   f"AND NOT EXISTS (SELECT 1 FROM {to} p WHERE p.{fld} = c.{col})")
        else:
            raise ProjectError(f"{model}.{col}: unknown test {kind!r}")
        return DataTest(f"{kind}_{model}_{col}", model, sql, severity)

    def run_tests(self, con) -> list[TestResult]:
        results = []
        for t in self.tests():
            try:
                n = int(con.execute(f"SELECT COUNT(*) FROM ({t.sql})").fetchone()[0])
            except Exception as exc:  # noqa: BLE001 - a broken test is reported, not raised
                results.append(TestResult(t.name, t.model, t.severity, "error", 0, str(exc)[:300]))
                continue
            status = "pass" if n == 0 else ("warn" if t.severity == "warn" else "fail")
            results.append(TestResult(t.name, t.model, t.severity, status, n, "" if n == 0 else t.description))
        return results


@functools.cache
def project() -> Project:
    """The package's model project, loaded once per process."""
    return Project()
