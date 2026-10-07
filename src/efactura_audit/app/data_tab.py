"""Data tab: the tables and SQL models, charts of the data, the data tests, and a read-only SQL box."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from efactura_audit.app.i18n import SEVERITY, pick
from efactura_audit.app.theme import BLUE, MUTED, SEQUENTIAL, SEV_COLORS, chart_layout, is_dark, surface
from efactura_audit.assistant.tools import readonly_select
from efactura_audit.store import Store
from efactura_audit.transform import project

LAYER_ORDER = ("sources", "staging", "intermediate", "marts", "other")
TEST_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌", "error": "⛔"}
SQL_LIMIT = 5000
PRICE_FLAGS = """SELECT fi.invoice_key, f.severity, json_extract_string(f.evidence, '$.item_group') AS item_group
                 FROM fct_flags f JOIN fct_flag_invoices fi USING (flag_id)
                 WHERE f.check_name = 'price_increase' AND f.rule <> 'cross_supplier' AND f.status <> 'dismissed'"""


def render(store: Store, q: Callable[..., pd.DataFrame], L: Callable[..., str], lang: str, version: int,
           bump: Callable[[], None]) -> None:
    t_tables, t_charts, t_tests, t_sql = st.tabs([L("data_tables"), L("data_charts"), L("data_tests_tab"), "SQL"])
    with t_tables:
        _tables(q, L, lang, version)
    with t_charts:
        _charts(q, L, lang, version)
    with t_tests:
        _tests(store, q, L, version, bump)
    with t_sql:
        _sql(store, L)


def _num(n: int, lang: str) -> str:
    s = f"{int(n):,}"
    return s.replace(",", ".") if lang == "ro" else s


# ------------------------------------------------------------------------------------ tables & models
def _catalog(q, L, version: int) -> pd.DataFrame:
    """Every table and view: layer, row count, column count, description."""
    p = project()
    objs = q("""SELECT t.table_name AS name, COUNT(c.column_name) AS n_columns
                FROM information_schema.tables t JOIN information_schema.columns c USING (table_schema, table_name)
                WHERE t.table_schema = 'main' GROUP BY 1""", _v=version)
    rows = []
    for name, n_cols in zip(objs["name"], objs["n_columns"]):
        if name in p.models:
            layer, desc = p.models[name].layer, p.models[name].description
        elif name in p.source_docs:
            layer, desc = "sources", p.source_docs[name]
        else:
            layer, desc = "other", ""
        n = int(q(f'SELECT COUNT(*) AS n FROM "{name}"', _v=version)["n"].iloc[0])
        rows.append({"layer": layer, "name": name, "rows": n, "columns": int(n_cols), "description": desc})
    cat = pd.DataFrame(rows)
    cat["order"] = cat["layer"].map(LAYER_ORDER.index)
    return cat.sort_values(["order", "name"]).drop(columns="order").reset_index(drop=True)


def _dates_as_dates(df: pd.DataFrame) -> pd.DataFrame:
    """DuckDB DATE columns arrive as timestamps at midnight; show them as plain dates."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) and (df[c].dropna().dt.normalize() == df[c].dropna()).all():
            df[c] = df[c].dt.date
    return df


def _layer_label(layer: str, L) -> str:
    return L(f"layer_{layer}") if layer in ("sources", "other") else layer


def _lineage_dot(cat: pd.DataFrame, selected: str, L, lang: str) -> str:
    p = project()
    dark = is_dark()
    fill, ink, line = ("#1a1a19", "#ffffff", "#383835") if dark else ("#fcfcfb", "#0b0b0b", "#c3c2b7")
    counts = dict(zip(cat["name"], cat["rows"]))
    rows_word = L("rows").lower()
    out = ['digraph { rankdir=LR; bgcolor="transparent"; nodesep=0.12; ranksep=0.55;',
           f'node [shape=box, style="rounded,filled", fontname="Segoe UI", fontsize=10, color="{line}", '
           f'fillcolor="{fill}", fontcolor="{ink}", penwidth=1, margin="0.12,0.04"];',
           f'edge [color="{MUTED}", arrowsize=0.5, penwidth=0.8];']
    groups = {"sources": sorted({t for m in p.models.values() for t in m.source_tables})}
    groups.update({layer: sorted(m.name for m in p.layer(layer)) for layer in ("staging", "intermediate", "marts")})
    for layer, names in groups.items():
        out.append(f'subgraph cluster_{layer} {{ label="{_layer_label(layer, L)}"; fontname="Segoe UI"; fontsize=11; '
                   f'fontcolor="{MUTED}"; color="{line}"; style="rounded";')
        for n in names:
            attrs = f'label="{n}\\n{_num(counts.get(n, 0), lang)} {rows_word}"'
            if n == selected:
                attrs += f', fillcolor="{BLUE}", fontcolor="#ffffff", color="{BLUE}"'
            out.append(f'"{n}" [{attrs}];')
        out.append("}")
    for m in p.models.values():
        for upstream in sorted(m.source_tables | m.refs):
            out.append(f'"{upstream}" -> "{m.name}";')
    out.append("}")
    return "\n".join(out)


def _tables(q, L, lang: str, version: int) -> None:
    cat = _catalog(q, L, version)
    names = cat["name"].tolist()
    layers = dict(zip(cat["name"], cat["layer"]))
    selected = st.selectbox(L("choose_table"), names, index=names.index("fct_invoices") if "fct_invoices" in names else 0,
                            format_func=lambda n: f"{_layer_label(layers[n], L)} · {n}", key="data_table")
    st.caption(L("lineage"))
    st.graphviz_chart(_lineage_dot(cat, selected, L, lang), width="stretch")

    st.dataframe(cat.assign(layer=cat["layer"].map(lambda x: _layer_label(x, L)))
                 .rename(columns={"layer": L("layer"), "name": L("table"), "rows": L("rows"),
                                  "columns": L("columns"), "description": L("description")}),
                 hide_index=True, width="stretch", height=260)

    p = project()
    model = p.models.get(selected)
    st.markdown(f"#### {selected}")
    desc = model.description if model else p.source_docs.get(selected, "")
    if desc:
        st.caption(desc)
    cols = q("""SELECT column_name, data_type, comment FROM duckdb_columns()
                WHERE schema_name = 'main' AND table_name = ? ORDER BY column_index""", (selected,), _v=version)
    specs = model.columns if model else {}
    cols["tests"] = cols["column_name"].map(
        lambda c: ", ".join(t if isinstance(t, str) else next(iter(t)) for t in specs.get(c, {}).get("tests", [])))
    cols["comment"] = cols["comment"].fillna("")
    left, right = st.columns([1, 1.6])
    left.dataframe(cols.rename(columns={"column_name": L("columns"), "data_type": L("type"), "comment": L("description"),
                                        "tests": L("tests")}),
                   hide_index=True, width="stretch", height=min(38 + 35 * len(cols), 420))
    with right:
        st.caption(L("preview", n=500))
        st.dataframe(_dates_as_dates(q(f'SELECT * FROM "{selected}" LIMIT 500', _v=version)),
                     hide_index=True, width="stretch", height=420)
    if model:
        with st.expander(L("model_sql")):
            st.code(model.raw_sql.strip(), language="sql")


# ------------------------------------------------------------------------------------ charts
def _charts(q, L, lang: str, version: int) -> None:
    _spend_heatmap(q, L, lang, version)
    st.divider()
    sups = q("""SELECT supplier_cui, supplier_name, flags, high_flags
                FROM dim_suppliers ORDER BY total_spend_ron DESC""", _v=version)
    if sups.empty:
        return
    names = dict(zip(sups["supplier_cui"], sups["supplier_name"]))
    busiest = int(sups.sort_values(["high_flags", "flags"], ascending=False).index[0])
    cui = st.selectbox(L("supplier"), sups["supplier_cui"].tolist(), index=busiest, key="data_sup",
                       format_func=lambda c: f"{names[c]} · CUI {c}")
    left, right = st.columns(2)
    with left:
        _supplier_invoices(q, L, lang, version, cui)
    with right:
        _item_prices(q, L, lang, version, cui)


def _spend_heatmap(q, L, lang: str, version: int) -> None:
    m = q("""SELECT d.supplier_name, m.month, m.spend_ron, d.total_spend_ron
             FROM mart_supplier_monthly_spend m JOIN dim_suppliers d USING (supplier_cui)""", _v=version)
    if m.empty:
        return
    st.markdown(f"**{L('spend_heatmap')}**")
    order = m.groupby("supplier_name")["total_spend_ron"].max().sort_values().index   # largest on top
    pv = m.pivot_table(index="supplier_name", columns="month", values="spend_ron", aggfunc="sum").reindex(order)
    z = pv.to_numpy()
    positive = z[np.isfinite(z) & (z > 0)]
    # one extreme month would wash out every other cell: saturate above the 95th percentile (hover keeps exact values)
    zmax = float(np.percentile(positive, 95)) if positive.size else None
    fig = go.Figure(go.Heatmap(
        z=z, x=list(pv.columns), y=list(pv.index), zmin=0, zmax=zmax, xgap=2, ygap=2, hoverongaps=False,
        colorscale=SEQUENTIAL,
        colorbar=dict(title=dict(text="lei"), thickness=10, outlinewidth=0),
        hovertemplate="%{y}<br>%{x}: %{z:,.0f} lei<extra></extra>"))
    fig.update_xaxes(type="category", tickangle=-45)
    st.plotly_chart(chart_layout(fig, 70 + 24 * len(pv), lang), width="stretch", config={"displayModeBar": False})
    with st.expander(L("table_view")):
        st.dataframe(pv.iloc[::-1].round(0), width="stretch")


def _severity_traces(fig: go.Figure, df: pd.DataFrame, y: str, name: Callable[[str], str], hover: str, lang: str) -> None:
    """Flagged points on top of the base series, one trace per severity (status color + icon + label)."""
    for sev in ("low", "medium", "high"):   # high drawn last, on top
        part = df[df["severity"] == sev]
        if part.empty:
            continue
        fig.add_trace(go.Scatter(
            x=part["issue_date"], y=part[y], mode="markers", name=name(sev),
            marker=dict(size=12, color=SEV_COLORS[sev], symbol="diamond", line=dict(width=2, color=surface())),
            customdata=part[["number", "detail"]], hovertemplate=hover))


def _supplier_invoices(q, L, lang: str, version: int, cui: str) -> None:
    st.markdown(f"**{L('supplier_invoices')}**")
    inv = q("""SELECT i.number, i.issue_date, i.spend_ron, i.is_credit_note, f.sev_rank, f.checks
               FROM fct_invoices i
               LEFT JOIN (SELECT invoice_key,
                                 MIN(CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END) AS sev_rank,
                                 string_agg(DISTINCT check_name, ', ') AS checks
                          FROM fct_flag_invoices WHERE status <> 'dismissed' GROUP BY 1) f USING (invoice_key)
               WHERE i.supplier_cui = ? ORDER BY i.issue_date""", (cui,), _v=version)
    inv["severity"] = inv["sev_rank"].map({0: "high", 1: "medium", 2: "low"})
    inv["detail"] = inv["checks"].fillna("")
    hover = "%{customdata[0]}<br>%{x|%Y-%m-%d}<br>%{y:,.2f} lei<extra>%{customdata[1]}</extra>"
    base = inv[inv["severity"].isna()]
    fig = go.Figure(go.Scatter(x=base["issue_date"], y=base["spend_ron"], mode="markers", name=L("not_flagged"),
                               marker=dict(size=8, color=MUTED), customdata=base[["number", "detail"]],
                               hovertemplate=hover))
    _severity_traces(fig, inv, "spend_ron", lambda s: pick(SEVERITY, s, lang), hover, lang)
    med = float(inv.loc[~inv["is_credit_note"], "spend_ron"].median()) if (~inv["is_credit_note"]).any() else None
    if med is not None:
        fig.add_hline(y=med, line=dict(color=MUTED, width=1), annotation_text=L("median"),
                      annotation_position="top left", annotation_font=dict(color=MUTED, size=11))
    chart_layout(fig, 340, lang)
    fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    fig.update_yaxes(title_text="lei")
    fig.update_xaxes(tickformat="%Y-%m")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with st.expander(L("table_view")):
        st.dataframe(inv[["number", "issue_date", "spend_ron", "severity", "checks"]], hide_index=True, width="stretch")


def _item_prices(q, L, lang: str, version: int, cui: str) -> None:
    st.markdown(f"**{L('item_price')}**")
    items = q("""SELECT item_group, ANY_VALUE(item_label) AS label, COUNT(*) AS n
                 FROM fct_invoice_lines
                 WHERE supplier_cui = ? AND NOT is_credit_note AND price_ron IS NOT NULL AND item_group IS NOT NULL
                 GROUP BY 1 HAVING COUNT(*) >= 3""", (cui,), _v=version)
    if items.empty:
        st.caption(L("no_items"))
        return
    flags = q(PRICE_FLAGS, _v=version)
    items["flagged"] = items["item_group"].isin(set(flags["item_group"]))
    items = items.sort_values(["flagged", "n"], ascending=False)
    labels = {g: f"{'⚠ ' if f else ''}{lab} ({n})" for g, lab, n, f in
              zip(items["item_group"], items["label"], items["n"], items["flagged"])}
    group = st.selectbox(L("item"), list(labels), format_func=labels.get, key=f"data_item_{cui}")
    pts = q("""SELECT invoice_key, number, issue_date, price_ron, quantity FROM fct_invoice_lines
               WHERE item_group = ? AND NOT is_credit_note AND price_ron IS NOT NULL
               ORDER BY issue_date, invoice_key""", (group,), _v=version)
    sev = flags[flags["item_group"] == group].groupby("invoice_key")["severity"].agg(
        lambda s: min(s, key=["high", "medium", "low"].index))
    pts["severity"] = pts["invoice_key"].map(sev)
    pts["detail"] = pts["quantity"].map(lambda v: f"qty {v:g}")
    hover = "%{customdata[0]}<br>%{x|%Y-%m-%d}<br>%{y:,.2f} lei · %{customdata[1]}<extra></extra>"
    fig = go.Figure(go.Scatter(x=pts["issue_date"], y=pts["price_ron"], mode="lines+markers",
                               name=items.set_index("item_group").loc[group, "label"],
                               line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE),
                               customdata=pts[["number", "detail"]], hovertemplate=hover))
    _severity_traces(fig, pts, "price_ron", lambda s: f"{L('price_flag')} ({pick(SEVERITY, s, lang)})",
                     hover, lang)
    chart_layout(fig, 340, lang)
    fig.update_layout(showlegend=bool(pts["severity"].notna().any()), legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    fig.update_yaxes(title_text="lei")
    fig.update_xaxes(tickformat="%Y-%m")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with st.expander(L("table_view")):
        st.dataframe(pts[["number", "issue_date", "price_ron", "quantity", "severity"]], hide_index=True, width="stretch")


# ------------------------------------------------------------------------------------ data tests
def _tests(store: Store, q, L, version: int, bump) -> None:
    if st.button(L("rerun_tests"), key="data_rerun_tests"):
        store.run_data_tests()
        bump()
        st.rerun()
    res = q("""SELECT status, test_name, model, severity, failures, message, run_at FROM data_test_results
               ORDER BY CASE status WHEN 'error' THEN 0 WHEN 'fail' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END, test_name""",
            _v=version)
    if res.empty:
        st.info(L("no_tests_yet"))
        return
    n = res["status"].value_counts()
    st.caption(L("tests_summary", p=n.get("pass", 0), w=n.get("warn", 0), f=n.get("fail", 0), e=n.get("error", 0))
               + f" · {str(res['run_at'].iloc[0])[:16]}")
    view = res.drop(columns="run_at")
    view.insert(0, "", view.pop("status").map(lambda s: f"{TEST_ICONS.get(s, '')} {s}"))
    st.dataframe(view, hide_index=True, width="stretch", height=min(38 + 35 * len(view), 460))
    tests = {t.name: t for t in project().tests()}
    for r in res[res["status"].isin(["warn", "fail"])].itertuples(index=False):
        with st.expander(f"{TEST_ICONS[r.status]} {r.test_name} · {r.failures}"):
            if r.message:
                st.caption(r.message)
            if r.test_name in tests:
                st.markdown(f"**{L('failing_rows')}**")
                st.dataframe(q(f"SELECT * FROM ({tests[r.test_name].sql}) LIMIT 100", _v=version),
                             hide_index=True, width="stretch")
                st.code(tests[r.test_name].sql, language="sql")


# ------------------------------------------------------------------------------------ SQL
def _sql(store: Store, L) -> None:
    marts = ", ".join(m.name for m in project().layer("marts"))
    st.caption(f"{L('sql_help', n=SQL_LIMIT)} Marts: {marts}.")
    sql = st.text_area("SQL", key="data_sql", height=150, label_visibility="collapsed",
                       value="SELECT supplier_name, invoices, ROUND(total_spend_ron, 2) AS spend_ron, flags\n"
                             "FROM dim_suppliers\nORDER BY spend_ron DESC")
    if st.button(L("run_query"), type="primary", key="data_run_sql"):
        try:
            st.session_state.data_sql_result = readonly_select(store, sql, limit=SQL_LIMIT)
            st.session_state.data_sql_error = None
        except Exception as exc:  # noqa: BLE001 - show DuckDB's message
            st.session_state.data_sql_result, st.session_state.data_sql_error = None, str(exc)
    if st.session_state.get("data_sql_error"):
        st.error(st.session_state.data_sql_error)
    df = st.session_state.get("data_sql_result")
    if df is not None:
        st.caption(f"{len(df)} {L('rows').lower()}")
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button(L("download_csv"), df.to_csv(index=False).encode("utf-8-sig"), "query.csv", "text/csv",
                           key="data_sql_csv")
