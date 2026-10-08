import { useEffect, useMemo, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import { X } from "lucide-react";
import { useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData, Spinner } from "../components/chrome";
import { DataTable, ResultTable, type Col } from "../components/DataTable";
import { BLUE, Plot, SEV_COLORS, surface } from "../components/Plot";
import { Callout, Disclosure, Field, JsonTree, MultiSelect, Segmented, SevBadge, StatusBadge, Toggle, checkLabel } from "../components/ui";
import { CHECK_KEYS, STATUS, fmtLei, fmtNum, pick, type Lang } from "../i18n";

export type FlagRow = {
  flag_id: string; check_name: string; rule: string; severity: string; score: number;
  supplier_cui: string | null; supplier_name: string | null; invoice_keys: string[]; invoice_numbers: string[];
  issue_date: string | null; amount_at_risk_ron: number | null; title_ro: string; title_en: string;
  evidence: Record<string, any>; status: string; review_note: string | null;
};
type InvolvedInvoice = { invoice_key: string; number: string; issue_date: string; supplier_name: string;
                         amount_ron: number | null; currency: string; payable: number; anaf_id: string | null;
                         lines: { columns: string[]; types: string[]; rows: unknown[][] } };

const SEVS = ["high", "medium", "low"];
const SEV_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

export function Flags() {
  const { L, lang, status } = useApp();
  const [checks, setChecks] = useState<string[]>([]);
  const [sevs, setSevs] = useState<string[]>([]);
  const [supplier, setSupplier] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, error } = useCall<FlagRow[]>("flags", { include_dismissed: showDismissed });
  const detailRef = useRef<HTMLDivElement>(null);

  const view = useMemo(() => (data ?? []).filter((f) =>
    (!checks.length || checks.includes(f.check_name)) &&
    (!sevs.length || sevs.includes(f.severity)) &&
    (!supplier || (f.supplier_name ?? "").toLowerCase().includes(supplier.toLowerCase())) &&
    (!Number(minAmount) || (f.amount_at_risk_ron ?? 0) >= Number(minAmount))), [data, checks, sevs, supplier, minAmount]);
  const total = view.reduce((s, f) => s + (f.amount_at_risk_ron ?? 0), 0);
  const flag = view.find((f) => f.flag_id === selected) ?? null;

  useEffect(() => {
    if (flag) detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [flag?.flag_id]);

  const cols = useMemo<Col<FlagRow>[]>(() => [
    { key: "severity", label: L("severity"), render: (r) => <SevBadge sev={r.severity} lang={lang} />, value: (r) => SEV_RANK[r.severity] },
    { key: "check_name", label: L("check"), value: (r) => checkLabel(r.check_name, lang) },
    { key: "supplier_name", label: L("supplier") },
    { key: "number", label: L("number"), value: (r) => r.invoice_numbers.slice(0, 3).join(", ") },
    { key: "issue_date", label: L("date"), kind: "date" },
    { key: "amount_at_risk_ron", label: L("to_review"), kind: "money" },
    { key: "title", label: L("finding"), value: (r) => (lang === "ro" ? r.title_ro : r.title_en), grow: true },
    { key: "status", label: L("status"), render: (r) => <StatusBadge status={r.status} lang={lang} />,
      value: (r) => pick(STATUS, r.status, lang) },
  ], [L, lang]);

  if (status && status.invoices === 0) return <NoData />;
  if (error) return <ErrorNote error={error} />;
  return (
    <>
      <section className="card filters">
        <MultiSelect label={L("check")} allLabel={L("all")} options={CHECK_KEYS} value={checks} onChange={setChecks}
                     render={(c) => checkLabel(c, lang)} />
        <MultiSelect label={L("severity")} allLabel={L("all")} options={SEVS} value={sevs} onChange={setSevs}
                     render={(s) => <SevBadge sev={s} lang={lang} />} />
        <Field label={L("supplier")}>
          <input type="search" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
        </Field>
        <Field label={L("min_amount")}>
          <input type="number" min={0} step={1000} value={minAmount} onChange={(e) => setMinAmount(e.target.value)} placeholder="0" />
        </Field>
        <Toggle label={L("show_dismissed")} checked={showDismissed} onChange={setShowDismissed} />
      </section>
      {!data ? <Loading /> : (
        <>
          <div className="caption" data-testid="flags-caption">{L("matching", { n: view.length, amt: fmtLei(total, lang) })}</div>
          <section className="card">
            <DataTable rows={view} cols={cols} lang={lang} rowKey={(r) => r.flag_id} selected={selected}
                       onSelect={(k) => setSelected(k)} maxHeight={360} testId="flags-table" />
          </section>
          {!flag ? <div className="hint">{L("select_flag")}</div>
            : <div ref={detailRef}><FlagDetail key={flag.flag_id} flag={flag} onClose={() => setSelected(null)} /></div>}
        </>
      )}
    </>
  );
}

function PriceHistory({ ev }: { ev: Record<string, any> }) {
  const { L } = useApp();
  const { data, layout } = useMemo(() => {
    const hist = ev.history as { date: string; price_ron: number }[];
    const aff = (ev.affected ?? []) as { date: string; price_ron: number }[];
    const traces: Data[] = [{
      type: "scatter", mode: "lines+markers", name: L("chart_before"), x: hist.map((h) => h.date), y: hist.map((h) => h.price_ron),
      line: { color: BLUE, width: 2 }, marker: { size: 8 }, hovertemplate: "%{x}<br>%{y:,.2f} lei<extra></extra>",
    }];
    if (aff.length) traces.push({
      type: "scatter", mode: "markers", name: L("chart_flagged"), x: aff.map((a) => a.date), y: aff.map((a) => a.price_ron),
      marker: { size: 10, color: SEV_COLORS.high, symbol: "diamond", line: { width: 2, color: surface() } },
      hovertemplate: "%{x}<br>%{y:,.2f} lei<extra></extra>",
    });
    const base = ev.baseline_median_price_ron as number | undefined;
    const lay: Partial<Layout> = base ? {
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: base, y1: base, line: { color: "gray", dash: "dot", width: 1 } }],
    } : {};
    return { data: traces, layout: lay };
  }, [ev, L]);
  return (
    <div>
      <div className="section-title">{L("price_history")}</div>
      <Plot data={data} layout={layout} height={240} testId="price-history" />
    </div>
  );
}

function InvoicesInvolved({ flagId, lang }: { flagId: string; lang: Lang }) {
  const { L } = useApp();
  const { data } = useCall<InvolvedInvoice[]>("flag_invoices", { flag_id: flagId });
  const labels = useMemo(() => Object.fromEntries(
    ["item_name", "quantity", "unit_code", "unit_price", "net_amount", "vat_rate"].map((c) => [c, L(`col_${c}`)])), [L]);
  if (!data) return <Spinner />;
  return (
    <div className="stack" style={{ gap: 8 }}>
      {data.map((h) => (
        <Disclosure key={h.invoice_key} title={`${h.number} · ${h.issue_date.slice(0, 10)} · ${fmtLei(h.amount_ron, lang)}`}>
          <ResultTable data={h.lines} lang={lang} labels={labels} maxHeight={260} />
          {h.anaf_id && <div className="hint">ANAF id: {h.anaf_id} · {h.currency} {fmtNum(h.payable, lang, 2)}</div>}
        </Disclosure>
      ))}
    </div>
  );
}

function Review({ flag }: { flag: FlagRow }) {
  const { L, lang, mutate, busy, toast } = useApp();
  const [st, setSt] = useState(flag.status);
  const [note, setNote] = useState(flag.review_note ?? "");
  const save = async () => {
    if (await mutate("set_feedback", { flag_id: flag.flag_id, status: st, note })) toast(L("saved"));
  };
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); save(); }} data-testid="review-form">
      <div className="section-title" style={{ margin: 0 }}>{L("review")}</div>
      <Segmented ariaLabel={L("status")} options={["open", "confirmed", "dismissed"]} value={st} onChange={setSt}
                 render={(s) => pick(STATUS, s, lang)} />
      <Field label={L("note")}><textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <div><button className="btn primary" type="submit" disabled={!!busy}>{busy === "set_feedback" && <Spinner />}{L("save")}</button></div>
    </form>
  );
}

export function FlagDetail({ flag, onClose }: { flag: FlagRow; onClose: () => void }) {
  const { L, lang } = useApp();
  const ev = flag.evidence;
  const notes: string[] = ev[`notes_${lang}`] ?? [];
  const todo: string | undefined = ev[`what_to_check_${lang}`];
  const clean = Object.fromEntries(Object.entries(ev).filter(([k]) => !k.startsWith("what_to_check") && !k.startsWith("notes_")));
  return (
    <section className="card detail" data-testid="flag-detail">
      <div className="detail-head">
        <div>
          <div className="eyebrow"><SevBadge sev={flag.severity} lang={lang} /><span>·</span><span>{checkLabel(flag.check_name, lang)}</span></div>
          <h3>{lang === "ro" ? flag.title_ro : flag.title_en}</h3>
          <div className="hint mono">{flag.flag_id} · {flag.check_name}/{flag.rule} · score {flag.score.toFixed(2)}</div>
        </div>
        <button className="close-btn" onClick={onClose} aria-label={L("close")}><X size={18} /></button>
      </div>
      <div className="grid-split">
        <div className="stack">
          {notes.map((n) => <Callout kind="warn" key={n}>{n}</Callout>)}
          {todo && <Callout kind="info"><b>{L("what_to_check")}:</b> {todo}</Callout>}
          {flag.check_name === "price_increase" && ev.history && <PriceHistory ev={ev} />}
          <Disclosure title={L("evidence")} open={flag.check_name !== "price_increase"} testId="evidence">
            <div className="json"><JsonTree value={clean} depth={2} /></div>
          </Disclosure>
        </div>
        <div className="stack">
          <div className="section-title" style={{ margin: 0 }}>{L("invoices_involved")}</div>
          <InvoicesInvolved flagId={flag.flag_id} lang={lang} />
          <Review flag={flag} />
        </div>
      </div>
    </section>
  );
}

