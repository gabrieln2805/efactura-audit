import { useMemo, useState } from "react";
import type { Data } from "plotly.js";
import { X } from "lucide-react";
import { useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { BLUE, Plot } from "../components/Plot";
import { FlagList } from "./Invoices";

type SupplierRow = { supplier_name: string; supplier_cui: string; invoices: number; spend_ron: number;
                     first_invoice: string; last_invoice: string; flags: number };
type BankRow = { supplier_iban: string; invoices: number; first_used: string; last_used: string };
type SupplierInfo = { supplier_name: string; supplier_cui: string; monthly_spend: { month: string; spend_ron: number }[];
                      bank_accounts: BankRow[]; flags: { flag_id: string; severity: string; title: string }[] };

function SupplierDetail({ cui, onClose }: { cui: string; onClose: () => void }) {
  const { L, lang } = useApp();
  const { data } = useCall<SupplierInfo>("supplier", { cui, lang });
  const chart = useMemo<Data[]>(() => data ? [{
    type: "bar", x: data.monthly_spend.map((m) => m.month), y: data.monthly_spend.map((m) => m.spend_ron),
    marker: { color: BLUE, cornerradius: 4 } as any, hovertemplate: "%{x}<br>%{y:,.0f} lei<extra></extra>",
  }] : [], [data]);
  const bankCols = useMemo<Col<BankRow>[]>(() => [
    { key: "supplier_iban", label: L("col_iban"), render: (r) => <span className="mono">{r.supplier_iban}</span> },
    { key: "invoices", label: L("invoices"), kind: "int" },
    { key: "first_used", label: L("col_first_used"), kind: "date" },
    { key: "last_used", label: L("col_last_used"), kind: "date" },
  ], [L]);
  if (!data) return <Loading rows={1} />;
  return (
    <section className="card detail" data-testid="supplier-detail">
      <div className="detail-head">
        <h3>{data.supplier_name} · CUI {data.supplier_cui}</h3>
        <button className="close-btn" onClick={onClose} aria-label={L("close")}><X size={18} /></button>
      </div>
      <div className="grid-even">
        <div><Plot data={chart} height={240} testId="supplier-monthly" /></div>
        <div className="stack">
          <div className="section-title" style={{ margin: 0 }}>{L("bank_accounts")}</div>
          <div className="card" style={{ boxShadow: "none" }}>
            <DataTable rows={data.bank_accounts} cols={bankCols} lang={lang} maxHeight={220} />
          </div>
          <FlagList flags={data.flags} lang={lang} />
        </div>
      </div>
    </section>
  );
}

export function Suppliers() {
  const { L, lang, status } = useApp();
  const { data, error } = useCall<SupplierRow[]>("suppliers");
  const [selected, setSelected] = useState<string | null>(null);
  const cols = useMemo<Col<SupplierRow>[]>(() => [
    { key: "supplier_name", label: L("supplier"), grow: true },
    { key: "supplier_cui", label: L("col_cui") },
    { key: "invoices", label: L("invoices"), kind: "int" },
    { key: "spend_ron", label: L("col_amount_ron"), kind: "money" },
    { key: "first_invoice", label: L("col_first_invoice"), kind: "date" },
    { key: "last_invoice", label: L("col_last_invoice"), kind: "date" },
    { key: "flags", label: L("col_flags"), kind: "int" },
  ], [L]);
  if (status && status.invoices === 0) return <NoData />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <section className="card">
        <DataTable rows={data} cols={cols} lang={lang} rowKey={(r) => r.supplier_cui} selected={selected}
                   onSelect={(k) => setSelected(k)} maxHeight={460} testId="suppliers-table" />
      </section>
      {selected && <SupplierDetail key={selected} cui={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
