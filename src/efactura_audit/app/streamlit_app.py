"""Local web app: audit view, flag review, reports and the AI assistant.

Start with `efactura-audit app` (binds to 127.0.0.1 only).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from efactura_audit.app import data_tab
from efactura_audit.app.i18n import CHECKS, EXAMPLES, SEVERITY, SEVERITY_ICON, STATUS, fmt_compact, fmt_lei, pick, tr
from efactura_audit.app.theme import BLUE, SEV_COLORS, chart_layout
from efactura_audit.assistant.agent import Assistant
from efactura_audit.assistant.backends import LocalBackend, MCPBackend
from efactura_audit.assistant.evaluation import approved_models, load_approved, run_model_test, save_result
from efactura_audit.assistant.providers import CLOUD_PROVIDERS, SUGGESTED_MODELS, make_provider, ollama_models
from efactura_audit.assistant.tools import AuditTools
from efactura_audit.config import load_workspace
from efactura_audit.engine import run_audit
from efactura_audit.importer import import_paths, import_sources, iter_uploaded
from efactura_audit.report import excel_report, pdf_report
from efactura_audit.store import Store
from efactura_audit.synthetic import write_dataset

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "mistral": "MISTRAL_API_KEY"}

st.set_page_config(page_title="e-Factura audit", page_icon="🧾", layout="wide")


@st.cache_resource
def get_workspace(root: str | None):
    ws = load_workspace(root)
    return ws, Store(ws.db_path)


ws, store = get_workspace(os.environ.get("EFACTURA_HOME"))
ss = st.session_state
ss.setdefault("lang", "ro")
ss.setdefault("chat", [])
ss.setdefault("cloud_enabled", bool(ws.section("assistant").get("cloud_enabled", False)))
ss.setdefault("allow_untested", bool(ws.section("assistant").get("allow_untested_models", False)))
ss.setdefault("data_version", 0)


def L(key: str, **kw) -> str:
    return tr(key, ss.lang, **kw)


def bump():
    ss.data_version += 1
    st.cache_data.clear()


@st.cache_data(show_spinner=False)
def q(sql: str, params: tuple = (), _v: int = 0) -> pd.DataFrame:
    return store.df(sql, list(params))


@st.cache_data(show_spinner=False)
def load_flags(include_dismissed: bool, _v: int = 0) -> pd.DataFrame:
    return store.flags(include_dismissed=include_dismissed)


def sev_label(sev: str) -> str:
    return f"{SEVERITY_ICON.get(sev, '')} {pick(SEVERITY, sev, ss.lang)}"


def do_audit():
    with st.spinner("…"):
        res = run_audit(store, ws.settings)
    bump()
    st.toast(L("audit_done", n=len(res.flags), s=res.seconds))


def load_demo():
    with st.spinner("…"):
        store.reset()
        data = ws.root / "demo_data"
        write_dataset(data, seed=7)
        import_paths(store, [data / "spv_downloads"])
        run_audit(store, ws.settings)
    bump()
    st.toast(L("demo_loaded"))


# ------------------------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown(f"### 🧾 {L('app_title')}")
    ss.lang = st.segmented_control(L("language"), ["ro", "en"], default=ss.lang,
                                   format_func=lambda x: "Română" if x == "ro" else "English") or ss.lang
    if st.button(L("run_audit"), type="primary", width="stretch"):
        do_audit()
    st.caption(f"🔒 {L('local_only')}")
    st.caption(f"{L('workspace')}: `{ws.root}`")
    last = q("SELECT finished_at, n_flags FROM runs ORDER BY finished_at DESC LIMIT 1", _v=ss.data_version)
    if not last.empty:
        st.caption(f"⏱ {str(last['finished_at'].iloc[0])[:16]}")

n_inv = int(q("SELECT COUNT(*) AS n FROM fct_invoices", _v=ss.data_version)["n"].iloc[0])

tabs = st.tabs([L("tab_overview"), L("tab_flags"), L("tab_invoices"), L("tab_suppliers"), L("tab_data"), L("tab_import"),
                L("tab_report"), L("tab_assistant"), L("tab_settings")])

# ------------------------------------------------------------------------------------ overview
with tabs[0]:
    if n_inv == 0:
        st.info(L("no_data"))
        if st.button(L("load_demo")):
            load_demo()
            st.rerun()
    else:
        ov = AuditTools(store, ss.lang).audit_overview()
        flags = load_flags(False, _v=ss.data_version)
        st.caption(f"{ov.get('company') or ''} · {L('period')}: {ov['first_date']} – {ov['last_date']}")
        c = st.columns(5)
        c[0].metric(L("invoices"), f"{ov['invoices']:,}".replace(",", "."))
        c[1].metric(L("suppliers"), ov["suppliers"])
        c[2].metric(L("spend"), fmt_compact(ov["total_spend_ron"], ss.lang), help=fmt_lei(ov["total_spend_ron"], ss.lang))
        c[3].metric(L("flags"), ov["flags_total"])
        c[4].metric(L("to_review"), fmt_compact(ov["amount_to_review_ron"], ss.lang), help=fmt_lei(ov["amount_to_review_ron"], ss.lang))

        left, right = st.columns([1, 1.4])
        with left:
            st.markdown(f"**{L('flags_by_check')}**")
            counts = [(pick(CHECKS, k, ss.lang), int((flags["check_name"] == k).sum()) if not flags.empty else 0) for k in CHECKS]
            fig = go.Figure(go.Bar(x=[v for _, v in counts][::-1], y=[k for k, _ in counts][::-1], orientation="h",
                                   marker=dict(color=BLUE, cornerradius=4), text=[v for _, v in counts][::-1],
                                   textposition="outside", hovertemplate="%{y}: %{x}<extra></extra>"))
            fig.update_xaxes(visible=False)
            st.plotly_chart(chart_layout(fig), width="stretch", config={"displayModeBar": False})
        with right:
            st.markdown(f"**{L('monthly_spend')}**")
            m = q("""SELECT month, SUM(spend_ron) AS spend, SUM(invoices) AS n
                     FROM mart_supplier_monthly_spend GROUP BY 1 ORDER BY 1""", _v=ss.data_version)
            fig = go.Figure(go.Bar(x=m["month"], y=m["spend"], marker=dict(color=BLUE, cornerradius=4),
                                   customdata=m["n"],
                                   hovertemplate="%{x}<br>%{y:,.0f} lei<br>%{customdata} " + L("invoices").lower() + "<extra></extra>"))
            st.plotly_chart(chart_layout(fig), width="stretch", config={"displayModeBar": False})

        st.markdown(f"**{L('top_flags')}**")
        if not flags.empty:
            top = flags.head(10)
            st.dataframe(pd.DataFrame({
                L("severity"): top["severity"].map(sev_label),
                L("check"): top["check_name"].map(lambda c: pick(CHECKS, c, ss.lang)),
                L("supplier"): top["supplier_name"],
                L("to_review"): top["amount_at_risk_ron"],
                L("finding"): top[f"title_{ss.lang}"],
            }), hide_index=True, width="stretch",
                column_config={L("to_review"): st.column_config.NumberColumn(format="%.2f")})
        st.caption(L("disclaimer"))

# ------------------------------------------------------------------------------------ flags
with tabs[1]:
    if n_inv == 0:
        st.info(L("no_data"))
    else:
        f1, f2, f3, f4, f5 = st.columns([1.3, 1, 1.2, 1, 0.9])
        checks_sel = f1.multiselect(L("check"), list(CHECKS), format_func=lambda c: pick(CHECKS, c, ss.lang),
                                    placeholder=L("all"))
        sev_sel = f2.multiselect(L("severity"), ["high", "medium", "low"], format_func=sev_label, placeholder=L("all"))
        sup_q = f3.text_input(L("supplier"), key="flag_sup")
        min_amt = f4.number_input(L("min_amount"), min_value=0.0, value=0.0, step=1000.0)
        show_dismissed = f5.checkbox(L("show_dismissed"))
        flags = load_flags(show_dismissed, _v=ss.data_version)
        view = flags.copy()
        if checks_sel:
            view = view[view["check_name"].isin(checks_sel)]
        if sev_sel:
            view = view[view["severity"].isin(sev_sel)]
        if sup_q:
            view = view[view["supplier_name"].fillna("").str.contains(sup_q, case=False, regex=False)]
        if min_amt:
            view = view[view["amount_at_risk_ron"].fillna(0) >= min_amt]
        view = view.reset_index(drop=True)
        st.caption(L("matching", n=len(view), amt=fmt_lei(view["amount_at_risk_ron"].fillna(0).sum(), ss.lang)))
        table = pd.DataFrame({
            L("severity"): view["severity"].map(sev_label),
            L("check"): view["check_name"].map(lambda c: pick(CHECKS, c, ss.lang)),
            L("supplier"): view["supplier_name"],
            L("number"): view["invoice_numbers"].map(lambda v: ", ".join(json.loads(v)[:3])),
            L("date"): view["issue_date"].astype(str).str[:10],
            L("to_review"): view["amount_at_risk_ron"],
            L("finding"): view[f"title_{ss.lang}"],
            L("status"): view["status"].map(lambda s: pick(STATUS, s, ss.lang)),
        })
        event = st.dataframe(table, hide_index=True, width="stretch", height=360, on_select="rerun",
                             selection_mode="single-row", key="flag_table",
                             column_config={L("to_review"): st.column_config.NumberColumn(format="%.2f"),
                                            L("finding"): st.column_config.TextColumn(width="large")})
        rows = event.selection.rows if event and event.selection else []
        if not rows:
            st.caption(L("select_flag"))
        else:
            f = view.iloc[rows[0]]
            ev = json.loads(f["evidence"])
            st.divider()
            st.markdown(f"#### {sev_label(f['severity'])} · {pick(CHECKS, f['check_name'], ss.lang)}")
            st.markdown(f"**{f[f'title_{ss.lang}']}**")
            st.caption(f"{f['flag_id']} · {f['check_name']}/{f['rule']} · score {f['score']:.2f}")
            a, b = st.columns([1.3, 1])
            with a:
                notes = ev.get(f"notes_{ss.lang}") or []
                for n in notes:
                    st.warning(n)
                todo = ev.get(f"what_to_check_{ss.lang}")
                if todo:
                    st.info(f"**{L('what_to_check')}:** {todo}")
                if f["check_name"] == "price_increase" and ev.get("history"):
                    hist = pd.DataFrame(ev["history"])
                    aff = pd.DataFrame(ev.get("affected", []))
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist["date"], y=hist["price_ron"], mode="lines+markers", name="before",
                                             line=dict(color=BLUE, width=2), marker=dict(size=8),
                                             hovertemplate="%{x}<br>%{y:,.2f} lei<extra></extra>"))
                    if not aff.empty:
                        fig.add_trace(go.Scatter(x=aff["date"], y=aff["price_ron"], mode="markers", name="flagged",
                                                 marker=dict(size=10, color=SEV_COLORS["high"], symbol="diamond",
                                                             line=dict(width=2, color="white")),
                                                 hovertemplate="%{x}<br>%{y:,.2f} lei<extra></extra>"))
                    base = ev.get("baseline_median_price_ron")
                    if base:
                        fig.add_hline(y=base, line=dict(color="gray", dash="dot", width=1))
                    st.markdown(f"**{L('price_history')}**")
                    st.plotly_chart(chart_layout(fig, 240), width="stretch", config={"displayModeBar": False})
                with st.expander(L("evidence"), expanded=f["check_name"] != "price_increase"):
                    clean = {k: v for k, v in ev.items() if not k.startswith(("what_to_check", "notes_"))}
                    st.json(clean, expanded=2)
            with b:
                st.markdown(f"**{L('invoices_involved')}**")
                keys = json.loads(f["invoice_keys"])[:6]
                for key in keys:
                    h = q("SELECT number, issue_date, supplier_name, amount_ron, currency, payable, anaf_id FROM fct_invoices WHERE invoice_key = ?",
                          (key,), _v=ss.data_version)
                    if h.empty:
                        continue
                    h = h.iloc[0]
                    with st.expander(f"{h['number']} · {str(h['issue_date'])[:10]} · {fmt_lei(h['amount_ron'], ss.lang)}"):
                        lines = q("""SELECT item_name, quantity, unit_code, unit_price, net_amount, vat_rate FROM fct_invoice_lines
                                     WHERE invoice_key = ? ORDER BY TRY_CAST(line_no AS INTEGER)""", (key,), _v=ss.data_version)
                        st.dataframe(lines, hide_index=True, width="stretch")
                        if h["anaf_id"]:
                            st.caption(f"ANAF id: {h['anaf_id']} · {h['currency']} {h['payable']:,.2f}")
                st.markdown(f"**{L('review')}**")
                with st.form(f"review_{f['flag_id']}"):
                    status_codes = ["open", "confirmed", "dismissed"]
                    status_labels = [pick(STATUS, c, ss.lang) for c in status_codes]
                    chosen = st.radio(L("status"), status_labels, horizontal=True,
                                      index=status_codes.index(f["status"]))
                    status = status_codes[status_labels.index(chosen)]
                    note = st.text_area(L("note"), value=f["review_note"] or "", height=80)
                    if st.form_submit_button(L("save")):
                        store.set_feedback(f["flag_id"], status, note)
                        bump()
                        st.toast(L("saved"))
                        st.rerun()

# ------------------------------------------------------------------------------------ invoices
with tabs[2]:
    if n_inv == 0:
        st.info(L("no_data"))
    else:
        c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 1, 1])
        sup = c1.text_input(L("supplier"), key="inv_sup")
        num = c2.text_input(L("number"), key="inv_num")
        dfrom = c3.date_input(L("from"), value=None, key="inv_from")
        dto = c4.date_input(L("to"), value=None, key="inv_to")
        flagged = c5.checkbox(L("flagged_only"))
        res = AuditTools(store, ss.lang).search_invoices(
            supplier=sup or None, number=num or None, date_from=dfrom.isoformat() if dfrom else None,
            date_to=dto.isoformat() if dto else None, flagged_only=flagged, limit=100)
        st.caption(L("matching", n=res["total_matching"], amt=fmt_lei(res["total_amount_ron"], ss.lang)) +
                   (" · max 100" if res["total_matching"] > 100 else ""))
        inv = pd.DataFrame(res["invoices"])
        if not inv.empty:
            ev = st.dataframe(inv, hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key="inv_table",
                              column_config={"amount_ron": st.column_config.NumberColumn(format="%.2f"),
                                             "payable": st.column_config.NumberColumn(format="%.2f")})
            sel = ev.selection.rows if ev and ev.selection else []
            if sel:
                row = inv.iloc[sel[0]]
                detail = AuditTools(store, ss.lang).get_invoice(row["number"], row["supplier_cui"])
                for d in detail.get("invoices", []):
                    st.markdown(f"**{d['number']}** · {d['supplier_name']} · {d['issue_date']} · {fmt_lei(d['amount_ron'], ss.lang)}")
                    st.dataframe(pd.DataFrame(d["lines"]), hide_index=True, width="stretch")
                    for fl in d["flags"]:
                        st.markdown(f"- {sev_label(fl['severity'])} `{fl['flag_id']}` {fl['title']}")

# ------------------------------------------------------------------------------------ suppliers
with tabs[3]:
    if n_inv == 0:
        st.info(L("no_data"))
    else:
        sups = q("""SELECT supplier_name, supplier_cui, invoices, ROUND(total_spend_ron, 2) AS spend_ron,
                           first_invoice, last_invoice, flags
                    FROM dim_suppliers ORDER BY spend_ron DESC""", _v=ss.data_version)
        ev = st.dataframe(sups, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          key="sup_table", column_config={"spend_ron": st.column_config.NumberColumn(format="%.2f")})
        sel = ev.selection.rows if ev and ev.selection else []
        if sel:
            info = AuditTools(store, ss.lang).supplier_summary(sups.iloc[sel[0]]["supplier_cui"])["suppliers"][0]
            st.markdown(f"#### {info['supplier_name']} · CUI {info['supplier_cui']}")
            a, b = st.columns([1.5, 1])
            with a:
                m = pd.DataFrame(info["monthly_spend"])
                fig = go.Figure(go.Bar(x=m["month"], y=m["spend_ron"], marker=dict(color=BLUE, cornerradius=4),
                                       hovertemplate="%{x}<br>%{y:,.0f} lei<extra></extra>"))
                st.plotly_chart(chart_layout(fig, 240), width="stretch", config={"displayModeBar": False})
            with b:
                st.markdown(f"**{L('bank_accounts')}**")
                st.dataframe(pd.DataFrame(info["bank_accounts"]), hide_index=True, width="stretch")
                for fl in info["flags"]:
                    st.markdown(f"- {sev_label(fl['severity'])} {fl['title']}")

# ------------------------------------------------------------------------------------ data
with tabs[4]:
    if n_inv == 0:
        st.info(L("no_data"))
    else:
        data_tab.render(store, q, L, ss.lang, ss.data_version, bump)

# ------------------------------------------------------------------------------------ import
with tabs[5]:
    st.caption(L("anaf_window"))
    buyer = st.text_input(L("buyer_filter"), value=ws.section("company").get("buyer_cui", ""))
    files = st.file_uploader(L("upload"), type=["zip", "xml"], accept_multiple_files=True)
    folder = st.text_input(L("folder"))
    if st.button(L("import_btn"), type="primary", disabled=not files and not folder):
        with st.spinner("…"):
            if files:
                def gen():
                    for f in files:
                        yield from iter_uploaded(f.name, f.getvalue())
                res = import_sources(store, gen(), buyer)
            else:
                res = import_paths(store, [Path(folder).expanduser()], buyer)
            run_audit(store, ws.settings)
        bump()
        st.success(L("imported", s=res.summary()))
        for e in res.errors[:10]:
            st.error(e)
    if st.button(L("load_demo"), key="demo2"):
        load_demo()
        st.rerun()
    tests = q("""SELECT status, test_name, model, failures, message FROM data_test_results
                 ORDER BY status = 'pass', test_name""", _v=ss.data_version)
    if not tests.empty:
        st.markdown(f"**{L('data_checks')}**")
        issues = tests[tests["status"] != "pass"]
        if issues.empty:
            st.caption(f"✅ {L('data_checks_ok', n=len(tests))}")
        else:
            st.dataframe(issues, hide_index=True, width="stretch")
    st.markdown(f"**{L('import_log')}**")
    st.dataframe(q("SELECT logged_at, status, source, message FROM import_log ORDER BY logged_at DESC LIMIT 200", _v=ss.data_version),
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------ report
with tabs[6]:
    if n_inv == 0:
        st.info(L("no_data"))
    else:
        rlang = st.segmented_control(L("report_lang"), ["ro", "en"], default=ss.lang,
                                     format_func=lambda x: "Română" if x == "ro" else "English", key="rlang") or "ro"
        st.caption(L("disclaimer"))
        c1, c2 = st.columns(2)
        if c1.button(L("make_excel"), width="stretch"):
            ss.xlsx = excel_report(store, rlang)
        if c2.button(L("make_pdf"), width="stretch"):
            ss.pdf = pdf_report(store, rlang)
        if ss.get("xlsx"):
            c1.download_button(f"⬇ {L('download')} .xlsx", ss.xlsx, f"audit-efactura-{rlang}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        if ss.get("pdf"):
            c2.download_button(f"⬇ {L('download')} .pdf", ss.pdf, f"audit-efactura-{rlang}.pdf", "application/pdf",
                               width="stretch")

# ------------------------------------------------------------------------------------ assistant
with tabs[7]:
    st.info(L("ai_label"))
    providers = ["ollama"] + (sorted(CLOUD_PROVIDERS) if ss.cloud_enabled else [])
    c1, c2, c3 = st.columns([1, 1.4, 1])
    provider = c1.selectbox(L("provider"), providers)
    approved = [m["model"] for m in approved_models(ws) if m["provider"] == provider]
    options = list(approved)
    if ss.allow_untested:
        extra = ollama_models(ws.section("assistant").get("ollama_url", "http://localhost:11434")) if provider == "ollama" else []
        options += [m for m in extra + SUGGESTED_MODELS.get(provider, []) if m not in options]
    labels = [m if m in approved else f"{m} ({L('untested')})" for m in options]
    chosen_model = c2.selectbox(L("model"), labels, key="chat_model") if options else None
    model = options[labels.index(chosen_model)] if chosen_model else None
    transport_label = c3.radio(L("transport"), [L("transport_local"), L("transport_mcp")], horizontal=True)
    transport = "mcp" if transport_label == L("transport_mcp") else "local"
    api_key = ""
    if provider in CLOUD_PROVIDERS:
        api_key = st.text_input(L("api_key"), type="password", value=os.environ.get(KEY_ENV[provider], ""))
        st.warning(L("cloud_warning", p=provider))
    else:
        st.caption(f"🔒 {L('local_model')}")

    if not model:
        st.warning(L("no_models"))
    elif n_inv == 0:
        st.info(L("no_data"))
    else:
        if st.button(L("clear_chat")):
            ss.chat = []
        for msg in ss.chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("trace"):
                    with st.expander(L("sources", n=len(msg["trace"]))):
                        for t in msg["trace"]:
                            st.markdown(f"`{t['name']}({json.dumps(t['arguments'], ensure_ascii=False)})`")
                            st.json(t["result"], expanded=False)
        st.caption(L("examples") + ": " + " · ".join(EXAMPLES[ss.lang]))
        question = st.chat_input(L("ask_placeholder"))
        if question:
            with st.chat_message("user"):
                st.markdown(question)
            history = [{"role": m["role"], "content": m["content"]} for m in ss.chat[-8:]]
            tools = AuditTools(store, ss.lang)
            backend = MCPBackend(str(ws.root), ss.lang) if transport == "mcp" else LocalBackend(tools)
            try:
                prov = make_provider(provider, model, api_key, ws.section("assistant").get("ollama_url", "") if provider == "ollama" else "")
                with st.spinner(L("thinking")):
                    ans = Assistant(prov, backend, tools.audit_overview(),
                                    int(ws.section("assistant").get("max_tool_rounds", 6))).ask(question, history)
            except ValueError as exc:
                ans = None
                st.error(str(exc))
            finally:
                backend.close()
            if ans is not None:
                text = ans.text if not ans.error else f"**{L('error')}:** {ans.error}"
                trace = [{"name": t.name, "arguments": t.arguments, "result": t.result} for t in ans.trace]
                ss.chat += [{"role": "user", "content": question},
                            {"role": "assistant", "content": text, "trace": trace}]
                st.rerun()

# ------------------------------------------------------------------------------------ settings
with tabs[8]:
    # keyed widgets update session state before the script runs, so the Assistant tab above sees changes at once
    st.toggle(L("cloud_enable"), key="cloud_enabled")
    st.toggle(L("allow_untested"), key="allow_untested")
    url = ws.section("assistant").get("ollama_url", "http://localhost:11434")
    installed = ollama_models(url)
    st.caption(L("ollama_status", n=len(installed)) if installed else L("ollama_off", u=url))

    st.markdown(f"#### {L('model_test')}")
    st.caption(L("model_test_help"))
    c1, c2, c3 = st.columns([1, 1.4, 1.4])
    tprov = c1.selectbox(L("provider"), ["ollama"] + (sorted(CLOUD_PROVIDERS) if ss.cloud_enabled else []), key="tprov")
    suggestions = (installed if tprov == "ollama" else []) + SUGGESTED_MODELS.get(tprov, [])
    tmodel = c2.selectbox(L("model"), list(dict.fromkeys(suggestions)) or [""], key="tmodel", accept_new_options=True)
    tkey = c3.text_input(L("api_key"), type="password", key="tkey",
                         value=os.environ.get(KEY_ENV.get(tprov, ""), "")) if tprov in CLOUD_PROVIDERS else ""
    if st.button(L("run_test"), disabled=not tmodel):
        try:
            prov = make_provider(tprov, tmodel, tkey, url if tprov == "ollama" else "")
            log = st.empty()
            with st.spinner("…"):
                with tempfile.TemporaryDirectory() as tmp:
                    result = run_model_test(prov, Path(tmp), progress=lambda s: log.caption(s))
            save_result(ws, result)
            (st.success if result.passed else st.error)(result.summary().splitlines()[0])
            st.code(result.summary())
        except ValueError as exc:
            st.error(str(exc))
    tested = load_approved(ws)
    if tested:
        st.markdown(f"**{L('approved_models')}**")
        st.dataframe(pd.DataFrame([{k: m[k] for k in ("provider", "model", "score", "structured_ok", "passed", "tested_at")}
                                   for m in tested]), hide_index=True, width="stretch")

    st.markdown(f"#### {L('feedback_stats')}")
    fb = store.feedback_stats()
    if not fb.empty:
        st.dataframe(fb, hide_index=True, width="stretch")
    st.caption(L("thresholds", p=ws.config_path))
