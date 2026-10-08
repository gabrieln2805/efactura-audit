// Data: the tables and SQL models (lineage, catalog, columns, preview), charts of the data, the data tests,
// and a read-only SQL box. Mirrors the Streamlit app's Data tab.
import { useEffect, useMemo, useRef, useState } from "react";
import type { Data as PlotData, Layout } from "plotly.js";
import { Download, Play, RotateCcw } from "lucide-react";
import { engine, useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData, Spinner } from "../components/chrome";
import { DataTable, ResultTable, type Col } from "../components/DataTable";
import { BLUE, MUTED, Plot, SEQUENTIAL, SEV_COLORS, surface, useDark } from "../components/Plot";
import { Disclosure, Field, SevBadge } from "../components/ui";
import { SEVERITY, fmtNum, pick, type Lang } from "../i18n";

type CatalogRow = { layer: string; name: string; rows: number; columns: number; description: string };
type Lineage = { groups: Record<string, string[]>; edges: [string, string][] };
type ResultData = { columns: string[]; types: string[]; rows: unknown[][] };
type TableDetail = { name: string; layer: string; description: string; sql: string | null; preview: ResultData;
                     columns: { column_name: string; data_type: string; comment: string; tests: string }[] };

const TABS = ["data_tables", "data_charts", "data_tests_tab", "sql"] as const;
const TEST_ICONS: Record<string, string> = { pass: "✅", warn: "⚠️", fail: "❌", error: "⛔" };
const SQL_LIMIT = 5000;

export function Data() {
  const { L, status } = useApp();
  const [tab, setTab] = useState<(typeof TABS)[number]>("data_tables");
  if (status && status.invoices === 0) return <NoData />;
  return (
    <>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t === "sql" ? "SQL" : L(t)}</button>
        ))}
      </div>
      {tab === "data_tables" && <TablesTab />}
      {tab === "data_charts" && <ChartsTab />}
      {tab === "data_tests_tab" && <TestsTab />}
      {tab === "sql" && <SqlTab />}
    </>
  );
}

// ------------------------------------------------------------------------------------ tables & models
const layerLabel = (layer: string, L: (k: string) => string) =>
  layer === "sources" || layer === "other" ? L(`layer_${layer}`) : layer;

type GraphvizT = { dot(src: string): string };
let graphviz: Promise<GraphvizT> | null = null;
const loadGraphviz = () => (graphviz ??= import("@hpcc-js/wasm-graphviz").then((m) => m.Graphviz.load()));

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function lineageDot(lin: Lineage, counts: Record<string, number>, selected: string, L: (k: string) => string, lang: Lang) {
  const fill = cssVar("--surface"), ink = cssVar("--text"), line = cssVar("--border-strong");
  const rows = L("rows").toLowerCase();
  const out = ['digraph { rankdir=LR; bgcolor="transparent"; nodesep=0.12; ranksep=0.55;',
    `node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="${line}", fillcolor="${fill}", fontcolor="${ink}", penwidth=1, margin="0.12,0.04"];`,
    `edge [color="${MUTED}", arrowsize=0.5, penwidth=0.8];`];
  for (const [layer, names] of Object.entries(lin.groups)) {
    out.push(`subgraph cluster_${layer} { label="${layerLabel(layer, L)}"; fontname="Helvetica"; fontsize=11; fontcolor="${MUTED}"; color="${line}"; style="rounded";`);
    for (const n of names) {
      let attrs = `label="${n}\\n${fmtNum(counts[n] ?? 0, lang)} ${rows}", id="node-${n}"`;
      if (n === selected) attrs += `, fillcolor="${BLUE}", fontcolor="#ffffff", color="${BLUE}"`;
      out.push(`"${n}" [${attrs}];`);
    }
    out.push("}");
  }
  for (const [a, b] of lin.edges) out.push(`"${a}" -> "${b}";`);
  out.push("}");
  return out.join("\n");
}

function LineageGraph({ catalog, selected, onSelect }: { catalog: CatalogRow[]; selected: string; onSelect: (n: string) => void }) {
  const { L, lang } = useApp();
  const dark = useDark();
  const { data: lin } = useCall<Lineage>("lineage");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!lin) return;
    let live = true;
    const counts = Object.fromEntries(catalog.map((c) => [c.name, c.rows]));
    loadGraphviz().then((g) => {
      if (live && ref.current) ref.current.innerHTML = g.dot(lineageDot(lin, counts, selected, L, lang));
    });
    return () => { live = false; };
  }, [lin, catalog, selected, L, lang, dark]);
  const click = (e: React.MouseEvent) => {
    const node = (e.target as Element).closest("g.node");
    const name = node?.id?.replace(/^node-/, "");
    if (name) onSelect(name);
  };
  return <div className="lineage" ref={ref} onClick={click} data-testid="lineage" />;
}

function TablesTab() {
  const { L, lang } = useApp();
  const { data: catalog, error } = useCall<CatalogRow[]>("catalog");
  const [selected, setSelected] = useState("fct_invoices");
  const { data: detail } = useCall<TableDetail>("table_detail", { name: selected });
  const catCols = useMemo<Col<CatalogRow>[]>(() => [
    { key: "layer", label: L("layer"), value: (r) => layerLabel(r.layer, L) },
    { key: "name", label: L("table"), render: (r) => <span className="mono">{r.name}</span> },
    { key: "rows", label: L("rows"), kind: "int" }, { key: "columns", label: L("columns"), kind: "int" },
    { key: "description", label: L("description"), grow: true },
  ], [L]);
  const colCols = useMemo<Col<TableDetail["columns"][number]>[]>(() => [
    { key: "column_name", label: L("columns"), render: (r) => <span className="mono">{r.column_name}</span> },
    { key: "data_type", label: L("type") }, { key: "comment", label: L("description") }, { key: "tests", label: L("tests") },
  ], [L]);
  if (error) return <ErrorNote error={error} />;
  if (!catalog) return <Loading />;
  return (
    <>
      <section className="card detail">
        <Field label={L("choose_table")}>
          <select value={selected} onChange={(e) => setSelected(e.target.value)} data-testid="table-select">
            {catalog.map((c) => <option key={c.name} value={c.name}>{layerLabel(c.layer, L)} · {c.name}</option>)}
          </select>
        </Field>
        <div className="hint">{L("lineage")}</div>
        <LineageGraph catalog={catalog} selected={selected} onSelect={setSelected} />
      </section>
      <section className="card">
        <DataTable rows={catalog} cols={catCols} lang={lang} rowKey={(r) => r.name} selected={selected}
                   onSelect={(k) => k && setSelected(k)} maxHeight={260} testId="catalog" />
      </section>
      <section className="card detail" data-testid="table-detail">
        <div>
          <h3 className="mono" style={{ fontSize: 15 }}>{selected}</h3>
          {detail?.description && <div className="hint">{detail.description}</div>}
        </div>
        {!detail ? <Loading rows={1} /> : (
          <>
            <div className="grid-cols-preview">
              <div className="card" style={{ boxShadow: "none" }}>
                <DataTable rows={detail.columns} cols={colCols} lang={lang} maxHeight={420} />
              </div>
              <div className="stack" style={{ gap: 6 }}>
                <div className="hint">{L("preview", { n: 500 })}</div>
                <div className="card" style={{ boxShadow: "none" }}>
                  <ResultTable data={detail.preview} lang={lang} maxHeight={420} testId="preview" />
                </div>
              </div>
            </div>
            {detail.sql && <Disclosure title={L("model_sql")}><pre className="code">{detail.sql}</pre></Disclosure>}
          </>
        )}
      </section>
    </>
  );
}

// ------------------------------------------------------------------------------------ charts
type Heatmap = { suppliers: string[]; months: string[]; z: (number | null)[][]; zmax: number | null };
type ChartSupplier = { supplier_cui: string; supplier_name: string; flags: number; high_flags: number };
type SupInvoice = { number: string; issue_date: string; spend_ron: number; is_credit_note: boolean; checks: string | null; severity: string | null };
type Item = { item_group: string; label: string; n: number; flagged: boolean };
type PricePoint = { invoice_key: string; number: string; issue_date: string; price_ron: number; quantity: number; severity: string | null };

function severityTraces<T extends { severity: string | null; issue_date: string; number: string }>(
  rows: T[], y: (r: T) => number, name: (s: string) => string, detail: (r: T) => string, hover: string): PlotData[] {
  const ring = surface();
  return ["low", "medium", "high"].flatMap((sev) => {   // high drawn last, on top
    const part = rows.filter((r) => r.severity === sev);
    return part.length ? [{
      type: "scatter", mode: "markers", name: name(sev), x: part.map((r) => r.issue_date), y: part.map(y),
      marker: { size: 12, color: SEV_COLORS[sev], symbol: "diamond", line: { width: 2, color: ring } },
      customdata: part.map((r) => [r.number, detail(r)]) as any, hovertemplate: hover,
    } as PlotData] : [];
  });
}

const legendTop: Partial<Layout> = { showlegend: true, legend: { orientation: "h", yanchor: "bottom", y: 1.0, x: 0 } };

function SpendHeatmap() {
  const { L, lang } = useApp();
  const { data } = useCall<Heatmap>("spend_heatmap");
  const dark = useDark();
  const chart = useMemo(() => data && data.suppliers.length ? {
    data: [{
      type: "heatmap", z: data.z, x: data.months, y: data.suppliers, zmin: 0, zmax: data.zmax ?? undefined,
      xgap: 2, ygap: 2, hoverongaps: false, colorscale: SEQUENTIAL,
      colorbar: { title: { text: "lei" }, thickness: 10, outlinewidth: 0 },
      hovertemplate: "%{y}<br>%{x}: %{z:,.0f} lei<extra></extra>",
    } as PlotData],
    layout: { xaxis: { type: "category", tickangle: -45 } } as Partial<Layout>,
  } : null, [data, dark]);
  const tableRows = useMemo(() => data ? data.suppliers.map((s, i) => ({ s, z: data.z[i] })).reverse() : [], [data]);
  const tableCols = useMemo<Col<{ s: string; z: (number | null)[] }>[]>(() => data ? [
    { key: "s", label: L("supplier") },
    ...data.months.map((m, j) => ({ key: m, label: m, kind: "int" as const, value: (r: { z: (number | null)[] }) => r.z[j] === null ? null : Math.round(r.z[j]!) })),
  ] : [], [data, L]);
  if (!data) return <Loading rows={1} />;
  if (!chart) return null;
  return (
    <section className="card detail">
      <div className="section-title" style={{ margin: 0 }}>{L("spend_heatmap")}</div>
      <Plot data={chart.data} layout={chart.layout} height={70 + 24 * data.suppliers.length} testId="heatmap" />
      <Disclosure title={L("table_view")}><DataTable rows={tableRows} cols={tableCols} lang={lang} maxHeight={400} /></Disclosure>
    </section>
  );
}

function SupplierInvoicesChart({ cui }: { cui: string }) {
  const { L, lang } = useApp();
  const { data } = useCall<{ invoices: SupInvoice[]; median: number | null }>("supplier_invoices", { cui });
  const dark = useDark();
  const chart = useMemo(() => {
    if (!data) return null;
    const hover = "%{customdata[0]}<br>%{x|%Y-%m-%d}<br>%{y:,.2f} lei<extra>%{customdata[1]}</extra>";
    const base = data.invoices.filter((r) => !r.severity);
    const traces: PlotData[] = [{
      type: "scatter", mode: "markers", name: L("not_flagged"), x: base.map((r) => r.issue_date), y: base.map((r) => r.spend_ron),
      marker: { size: 8, color: MUTED }, customdata: base.map((r) => [r.number, r.checks ?? ""]) as any, hovertemplate: hover,
    } as PlotData, ...severityTraces(data.invoices, (r) => r.spend_ron, (s) => pick(SEVERITY, s, lang), (r) => r.checks ?? "", hover)];
    const layout: Partial<Layout> = {
      ...legendTop, yaxis: { title: { text: "lei" } }, xaxis: { tickformat: "%Y-%m" },
      ...(data.median !== null ? {
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: data.median, y1: data.median, line: { color: MUTED, width: 1 } }],
        annotations: [{ xref: "paper", x: 0, y: data.median, yanchor: "bottom", xanchor: "left", text: L("median"),
                        showarrow: false, font: { color: MUTED, size: 11 } }],
      } : {}),
    };
    return { traces, layout };
  }, [data, L, lang, dark]);
  const cols = useMemo<Col<SupInvoice>[]>(() => [
    { key: "number", label: L("number") }, { key: "issue_date", label: L("date"), kind: "date" },
    { key: "spend_ron", label: L("col_amount_ron"), kind: "money" },
    { key: "severity", label: L("severity"), render: (r) => r.severity ? <SevBadge sev={r.severity} lang={lang} /> : "" },
    { key: "checks", label: L("check") },
  ], [L, lang]);
  return (
    <div className="stack">
      <div className="section-title" style={{ margin: 0 }}>{L("supplier_invoices")}</div>
      {!chart ? <Loading rows={1} /> : <Plot data={chart.traces} layout={chart.layout} height={340} testId="supplier-invoices" />}
      {data && <Disclosure title={L("table_view")}><DataTable rows={data.invoices} cols={cols} lang={lang} maxHeight={300} /></Disclosure>}
    </div>
  );
}

function ItemPriceChart({ cui }: { cui: string }) {
  const { L, lang } = useApp();
  const { data: items } = useCall<Item[]>("supplier_items", { cui });
  const [group, setGroup] = useState<string | null>(null);
  const current = items?.find((i) => i.item_group === group) ?? items?.[0];
  const { data: pts } = useCall<PricePoint[]>("item_prices", { item_group: current?.item_group ?? "" }, !!current);
  const dark = useDark();
  const chart = useMemo(() => {
    if (!pts || !current) return null;
    const hover = "%{customdata[0]}<br>%{x|%Y-%m-%d}<br>%{y:,.2f} lei · %{customdata[1]}<extra></extra>";
    const detail = (r: PricePoint) => `qty ${+r.quantity.toPrecision(6)}`;   // Python's f"{v:g}"
    const traces: PlotData[] = [{
      type: "scatter", mode: "lines+markers", name: current.label, x: pts.map((p) => p.issue_date), y: pts.map((p) => p.price_ron),
      line: { color: BLUE, width: 2 }, marker: { size: 8, color: BLUE },
      customdata: pts.map((p) => [p.number, detail(p)]) as any, hovertemplate: hover,
    } as PlotData, ...severityTraces(pts, (p) => p.price_ron, (s) => `${L("price_flag")} (${pick(SEVERITY, s, lang)})`, detail, hover)];
    const layout: Partial<Layout> = { ...legendTop, showlegend: pts.some((p) => p.severity), yaxis: { title: { text: "lei" } },
                                      xaxis: { tickformat: "%Y-%m" } };
    return { traces, layout };
  }, [pts, current, L, lang, dark]);
  const cols = useMemo<Col<PricePoint>[]>(() => [
    { key: "number", label: L("number") }, { key: "issue_date", label: L("date"), kind: "date" },
    { key: "price_ron", label: L("col_unit_price"), kind: "money" }, { key: "quantity", label: L("col_quantity"), kind: "num" },
    { key: "severity", label: L("severity"), render: (r) => r.severity ? <SevBadge sev={r.severity} lang={lang} /> : "" },
  ], [L, lang]);
  return (
    <div className="stack">
      <div className="section-title" style={{ margin: 0 }}>{L("item_price")}</div>
      {items && items.length === 0 && <div className="hint">{L("no_items")}</div>}
      {current && (
        <Field label={L("item")}>
          <select value={current.item_group} onChange={(e) => setGroup(e.target.value)} data-testid="item-select">
            {items!.map((i) => <option key={i.item_group} value={i.item_group}>{i.flagged ? "⚠ " : ""}{i.label} ({i.n})</option>)}
          </select>
        </Field>
      )}
      {current && (!chart ? <Loading rows={1} /> : <Plot data={chart.traces} layout={chart.layout} height={340} testId="item-prices" />)}
      {current && pts && <Disclosure title={L("table_view")}><DataTable rows={pts} cols={cols} lang={lang} maxHeight={300} /></Disclosure>}
    </div>
  );
}

function ChartsTab() {
  const { L } = useApp();
  const { data } = useCall<{ suppliers: ChartSupplier[]; default: string | null }>("chart_suppliers");
  const [cui, setCui] = useState<string | null>(null);
  const current = cui ?? data?.default ?? null;
  return (
    <>
      <SpendHeatmap />
      {data && current && (
        <section className="card detail">
          <Field label={L("supplier")}>
            <select value={current} onChange={(e) => setCui(e.target.value)} data-testid="chart-supplier">
              {data.suppliers.map((s) => <option key={s.supplier_cui} value={s.supplier_cui}>{s.supplier_name} · CUI {s.supplier_cui}</option>)}
            </select>
          </Field>
          <div className="grid-even">
            <SupplierInvoicesChart cui={current} />
            <ItemPriceChart key={current} cui={current} />
          </div>
        </section>
      )}
    </>
  );
}

// ------------------------------------------------------------------------------------ data tests
type TestResultRow = { status: string; test_name: string; model: string; severity: string; failures: number;
                       message: string | null; run_at: string; sql: string | null };

function FailingRows({ test }: { test: string }) {
  const { lang } = useApp();
  const { data, error } = useCall<ResultData>("failing_rows", { test_name: test });
  if (error) return <div className="error-box">{error}</div>;
  return data ? <ResultTable data={data} lang={lang} maxHeight={300} /> : <Spinner />;
}

function TestsTab() {
  const { L, lang, busy, mutate } = useApp();
  const { data } = useCall<{ tests: TestResultRow[]; run_at: string | null }>("data_tests");
  const cols = useMemo<Col<TestResultRow>[]>(() => [
    { key: "status", label: "", render: (r) => `${TEST_ICONS[r.status] ?? ""} ${r.status}` },
    { key: "test_name", label: L("tests"), render: (r) => <span className="mono">{r.test_name}</span> },
    { key: "model", label: L("table") }, { key: "severity", label: L("severity") },
    { key: "failures", label: L("rows"), kind: "int" }, { key: "message", label: L("description"), grow: true },
  ], [L]);
  if (!data) return <Loading />;
  const n = (s: string) => data.tests.filter((t) => t.status === s).length;
  return (
    <>
      <div className="row">
        <button className="btn" onClick={() => mutate("rerun_tests")} disabled={!!busy}>
          {busy === "rerun_tests" ? <Spinner /> : <RotateCcw size={15} />}{L("rerun_tests")}
        </button>
        {data.tests.length > 0 && (
          <span className="caption" data-testid="tests-summary">
            {L("tests_summary", { p: n("pass"), w: n("warn"), f: n("fail"), e: n("error") })} · {data.run_at?.replace("T", " ")}
          </span>
        )}
      </div>
      {data.tests.length === 0 ? <div className="card center-card"><div className="hint">{L("no_tests_yet")}</div></div> : (
        <>
          <section className="card"><DataTable rows={data.tests} cols={cols} lang={lang} maxHeight={460} testId="tests-table" /></section>
          {data.tests.filter((t) => t.status === "warn" || t.status === "fail").map((t) => (
            <Disclosure key={t.test_name} title={`${TEST_ICONS[t.status]} ${t.test_name} · ${t.failures}`} testId="failing-test">
              {t.message && <div className="hint">{t.message}</div>}
              {t.sql && (
                <>
                  <div className="section-title">{L("failing_rows")}</div>
                  <FailingRows test={t.test_name} />
                  <pre className="code">{t.sql}</pre>
                </>
              )}
            </Disclosure>
          ))}
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------------------------ SQL
const DEFAULT_SQL = "SELECT supplier_name, invoices, ROUND(total_spend_ron, 2) AS spend_ron, flags\nFROM dim_suppliers\nORDER BY spend_ron DESC";

function toCsv(d: ResultData): string {
  const cell = (v: unknown) => {
    if (v === null || v === undefined) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return "﻿" + [d.columns.map(cell).join(","), ...d.rows.map((r) => r.map(cell).join(","))].join("\r\n") + "\r\n";
}

export function download(data: BlobPart, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function SqlTab() {
  const { L, lang } = useApp();
  const { data: marts } = useCall<string[]>("marts");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [result, setResult] = useState<ResultData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      setResult(await engine.call<ResultData>("sql", { query: sql }));
      setError(null);
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };
  return (
    <>
      <section className="card detail">
        <div className="hint">{L("sql_help", { n: SQL_LIMIT })}{marts ? ` Marts: ${marts.join(", ")}.` : ""}</div>
        <textarea className="input code-input" value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false}
                  aria-label="SQL" rows={6} data-testid="sql-input"
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); }} />
        <div className="row">
          <button className="btn primary" onClick={run} disabled={running}>{running ? <Spinner /> : <Play size={15} />}{L("run_query")}</button>
          {result && (
            <button className="btn" onClick={() => download(toCsv(result), "query.csv", "text/csv")}>
              <Download size={15} />{L("download_csv")}
            </button>
          )}
        </div>
        {error && <div className="error-box" role="alert">{error}</div>}
      </section>
      {result && (
        <>
          <div className="caption" data-testid="sql-count">{result.rows.length} {L("rows").toLowerCase()}</div>
          <section className="card"><ResultTable data={result} lang={lang} maxHeight={480} testId="sql-result" /></section>
        </>
      )}
    </>
  );
}
