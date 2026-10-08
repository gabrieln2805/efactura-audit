import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { Field, SevBadge, Toggle } from "../components/ui";
import { fmtLei, type Lang } from "../i18n";

type InvoiceRow = { number: string; issue_date: string; supplier_name: string; supplier_cui: string; currency: string;
                    payable: number; amount_ron: number; is_credit_note: boolean; n_flags: number };
type Search = { total_matching: number; total_amount_ron: number; invoices: InvoiceRow[] };
type LineRow = Record<string, unknown>;
type InvoiceDetail = { invoices: { number: string; supplier_name: string; issue_date: string; amount_ron: number;
                                   lines: LineRow[]; flags: { flag_id: string; severity: string; title: string }[] }[];
                       error?: string };

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const LINE_COLS = ["line_no", "item_name", "quantity", "unit_code", "unit_price", "net_amount", "vat_category", "vat_rate"];

export function LinesTable({ lines, lang }: { lines: LineRow[]; lang: Lang }) {
  const { L } = useApp();
  const cols = useMemo<Col<LineRow>[]>(() => LINE_COLS.map((c) => ({
    key: c, label: L(`col_${c}`),
    kind: ["quantity", "unit_price", "net_amount", "vat_rate"].includes(c) ? "num" : "text",
    grow: c === "item_name",
  })), [L]);
  return <DataTable rows={lines} cols={cols} lang={lang} maxHeight={320} />;
}

export function FlagList({ flags, lang, showId = false }:
  { flags: { flag_id: string; severity: string; title: string }[]; lang: Lang; showId?: boolean }) {
  return (
    <ul className="flag-list">
      {flags.map((f) => (
        <li key={f.flag_id}><SevBadge sev={f.severity} lang={lang} />{showId && <code className="mono">{f.flag_id}</code>}<span>{f.title}</span></li>
      ))}
    </ul>
  );
}

function InvoiceDetailCard({ row, onClose }: { row: InvoiceRow; onClose: () => void }) {
  const { L, lang } = useApp();
  const { data } = useCall<InvoiceDetail>("get_invoice", { number: row.number, supplier_cui: row.supplier_cui, lang });
  if (!data) return <Loading rows={1} />;
  return (
    <section className="card detail" data-testid="invoice-detail">
      {(data.invoices ?? []).map((d, i) => (
        <div className="stack" key={i}>
          <div className="detail-head">
            <h3><b>{d.number}</b> · {d.supplier_name} · {d.issue_date} · {fmtLei(d.amount_ron, lang)}</h3>
            {i === 0 && <button className="close-btn" onClick={onClose} aria-label={L("close")}><X size={18} /></button>}
          </div>
          <div className="card" style={{ boxShadow: "none" }}><LinesTable lines={d.lines} lang={lang} /></div>
          {d.flags.length > 0 && <FlagList flags={d.flags} lang={lang} showId />}
        </div>
      ))}
    </section>
  );
}

export function Invoices() {
  const { L, lang, status } = useApp();
  const [supplier, setSupplier] = useState("");
  const [number, setNumber] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const args = useDebounced({ supplier, number, date_from: from, date_to: to, flagged_only: flagged, lang });
  const { data, error } = useCall<Search>("search_invoices", args);
  const rowKey = (r: InvoiceRow) => `${r.supplier_cui}|${r.number}|${r.issue_date}`;
  const row = data?.invoices.find((r) => rowKey(r) === selected) ?? null;

  const cols = useMemo<Col<InvoiceRow>[]>(() => [
    { key: "number", label: L("number") },
    { key: "issue_date", label: L("date"), kind: "date" },
    { key: "supplier_name", label: L("supplier"), grow: true },
    { key: "supplier_cui", label: L("col_cui") },
    { key: "currency", label: L("col_currency") },
    { key: "payable", label: L("col_payable"), kind: "money" },
    { key: "amount_ron", label: L("col_amount_ron"), kind: "money" },
    { key: "is_credit_note", label: L("col_credit_note"), kind: "bool" },
    { key: "n_flags", label: L("col_flags"), kind: "int" },
  ], [L]);

  if (status && status.invoices === 0) return <NoData />;
  if (error) return <ErrorNote error={error} />;
  return (
    <>
      <section className="card filters">
        <Field label={L("supplier")} grow={1.2}><input type="search" value={supplier} onChange={(e) => setSupplier(e.target.value)} /></Field>
        <Field label={L("number")}><input type="search" value={number} onChange={(e) => setNumber(e.target.value)} /></Field>
        <Field label={L("from")}><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={L("to")}><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Toggle label={L("flagged_only")} checked={flagged} onChange={setFlagged} />
      </section>
      {!data ? <Loading /> : (
        <>
          <div className="caption" data-testid="invoices-caption">
            {L("matching", { n: data.total_matching, amt: fmtLei(data.total_amount_ron, lang) })}
            {data.total_matching > 100 ? " · max 100" : ""}
          </div>
          {data.invoices.length > 0 && (
            <section className="card">
              <DataTable rows={data.invoices} cols={cols} lang={lang} rowKey={rowKey} selected={selected}
                         onSelect={(k) => setSelected(k)} maxHeight={420} testId="invoices-table"
                         yesNo={[L("yes"), ""]} />
            </section>
          )}
          {row && <InvoiceDetailCard key={selected} row={row} onClose={() => setSelected(null)} />}
        </>
      )}
    </>
  );
}
