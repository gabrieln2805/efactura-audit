"""dbt-style model layer: project graph, data tests, model build and migration of 0.1.x workspaces."""
from datetime import date

import pytest

from efactura_audit.assistant.tools import AuditTools
from efactura_audit.config import default_settings
from efactura_audit.engine import run_audit
from efactura_audit.importer import import_sources
from efactura_audit.importer.anaf_zip import XmlSource
from efactura_audit.store import Store
from efactura_audit.transform import Project, ProjectError, project
from efactura_audit.ubl_writer import InvoiceDoc, Line, Party, render

SUP = Party("Furnizor Test SRL", "18547290", iban="RO49AAAA1B31007593840000")
BUY = Party("Client SRL", "14399840")
LAYERS = {"staging": 0, "intermediate": 1, "marts": 2}


def _store_with(tmp_path, docs) -> Store:
    store = Store(tmp_path / "t.duckdb")
    import_sources(store, (XmlSource(f"{i}.xml", render(d), str(i)) for i, d in enumerate(docs)))
    return store


def _monthly(n: int, buyer: Party = BUY) -> list[InvoiceDoc]:
    return [InvoiceDoc(number=f"FT-{100 + m}", issue_date=date(2025, 1 + m, 10), supplier=SUP, buyer=buyer,
                       lines=[Line("Hartie copiator A4 80g", 10 + m, 24.5, 21.0)]) for m in range(n)]


def _results(store: Store) -> dict:
    return {r.name: r for r in store.run_data_tests()}


def test_models_only_read_upstream_layers():
    p = project()
    assert {m.layer for m in p.models.values()} <= set(LAYERS)
    for m in p.models.values():
        for r in m.refs:
            assert LAYERS[p.models[r].layer] <= LAYERS[m.layer], f"{m.name} reads downstream model {r}"
    assert all(not m.refs for m in p.layer("staging")), "staging models read sources only"
    # run_sql advertises the documented mart columns, so every mart needs them
    assert all(m.description and m.columns for m in p.layer("marts"))


def test_data_tests_pass_on_demo(demo):
    results = demo["store"].run_data_tests()
    assert len(results) > 20
    assert [r for r in results if r.status != "pass"] == []


def test_data_tests_report_bad_data(tmp_path):
    docs = _monthly(3) + [InvoiceDoc(number="FT-900", issue_date=date(2025, 5, 2), supplier=SUP,
                                     buyer=Party("Alt Client SRL", "40000004"),
                                     lines=[Line("Toner HP 85A", 1, 210.0, 21.0)])]
    store = _store_with(tmp_path, docs)
    assert all(r.status == "pass" for n, r in _results(store).items() if n != "assert_single_buyer")
    with store.connect() as con:
        con.execute("INSERT INTO raw_invoice_lines (invoice_key, line_no, item_name) VALUES ('no-such-invoice', '1', 'x')")
    res = _results(store)
    assert res["assert_single_buyer"].status == "warn" and res["assert_single_buyer"].failures == 2
    assert res["relationships_stg_invoice_lines_invoice_key"].status == "fail"
    assert res["relationships_stg_invoice_lines_invoice_key"].failures == 1
    stored = store.df("SELECT status, COUNT(*) AS n FROM data_test_results GROUP BY 1")
    assert set(stored["status"]) == {"pass", "warn", "fail"}


def test_models_rebuild_only_when_files_change(tmp_path):
    store = Store(tmp_path / "a.duckdb")
    assert store.build_models() is False
    assert store.build_models(force=True) is True
    assert store.scalar("SELECT COUNT(*) FROM duckdb_views() WHERE NOT internal") == len(project().models)


def test_project_rejects_unknown_ref(tmp_path):
    (tmp_path / "models" / "staging").mkdir(parents=True)
    (tmp_path / "models" / "staging" / "stg_a.sql").write_text("select * from {{ ref('missing') }}", encoding="utf-8")
    with pytest.raises(ProjectError, match="missing"):
        Project(tmp_path)


def test_run_sql_advertises_the_marts(tmp_path):
    spec = next(s for s in AuditTools(Store(tmp_path / "a.duckdb")).specs() if s.name == "run_sql")
    assert "fct_invoices(" in spec.description and "spend_ron" in spec.description
    assert "fct_flags(" in spec.description and "flags_view" not in spec.description


def test_lineage_graph_shows_every_model_and_dependency():
    import pandas as pd

    from efactura_audit.app.data_tab import _lineage_dot
    p = project()
    cat = pd.DataFrame({"name": list(p.models), "rows": 1})
    dot = _lineage_dot(cat, "fct_invoices", lambda key, **kw: key, "en")
    for m in p.models.values():
        assert f'"{m.name}" [' in dot
        for upstream in m.refs | m.source_tables:
            assert f'"{upstream}" -> "{m.name}";' in dot
    assert {t for m in p.models.values() for t in m.source_tables} >= {"raw_invoices", "item_groups", "flags"}


def test_legacy_workspace_is_migrated(tmp_path):
    store = _store_with(tmp_path, _monthly(4))
    run_audit(store, default_settings())
    with store.connect() as con:   # a flag to review, so feedback has something to survive
        con.execute("""INSERT INTO flags (flag_id, check_name, rule, severity, score, invoice_keys, invoice_numbers,
                                          title_en, title_ro, evidence)
                       VALUES ('SUP-test', 'supplier', 'iban_changed', 'medium', 0.7, '[]', '[]', 't', 't', '{}')""")
    store.set_feedback("SUP-test", "dismissed", "known")
    n_lines = store.scalar("SELECT COUNT(*) FROM raw_invoice_lines")

    # turn the workspace back into the 0.1.x layout
    with store.connect() as con:
        for m in project().models:
            con.execute(f"DROP VIEW IF EXISTS {m}")
        con.execute("DROP TABLE _model_build")
        con.execute("DROP TABLE item_groups")
        for t in ("invoices", "invoice_lines", "vat_breakdown"):
            con.execute(f"ALTER TABLE raw_{t} RENAME TO {t}")
        con.execute("ALTER TABLE invoice_lines ADD COLUMN item_group VARCHAR")
        con.execute("UPDATE invoice_lines SET item_group = 'n:18547290:abc'")
        con.execute("CREATE VIEW flags_view AS SELECT * FROM flags")

    migrated = Store(tmp_path / "t.duckdb")
    assert migrated.scalar("SELECT COUNT(*) FROM fct_invoices") == 4
    assert migrated.scalar("SELECT COUNT(*) FROM fct_invoice_lines WHERE item_group = 'n:18547290:abc'") == n_lines
    assert migrated.scalar("SELECT COUNT(*) FROM duckdb_views() WHERE view_name = 'flags_view'") == 0
    assert "item_group" not in set(migrated.df("SELECT * FROM raw_invoice_lines LIMIT 0").columns)
    assert migrated.scalar("SELECT status FROM fct_flags WHERE flag_id = 'SUP-test'") == "dismissed"
    run_audit(migrated, default_settings())
    assert migrated.scalar("SELECT COUNT(*) FROM flag_feedback WHERE status = 'dismissed'") == 1
