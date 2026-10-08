import { useMemo } from "react";
import type { Data } from "plotly.js";
import { useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { BLUE, Plot } from "../components/Plot";
import { SevBadge, checkLabel } from "../components/ui";
import { CHECK_KEYS, fmtCompact, fmtLei, fmtNum } from "../i18n";

type TopFlag = { flag_id: string; severity: string; check_name: string; supplier_name: string | null;
                 amount_at_risk_ron: number | null; title_ro: string; title_en: string };
type OverviewData =
  | { empty: true }
  | { empty: false;
      overview: { invoices: number; suppliers: number; total_spend_ron: number; flags_total: number;
                  amount_to_review_ron: number; company: string | null; first_date: string; last_date: string };
      flags_by_check: Record<string, number>;
      monthly: { month: string; spend: number; n: number }[];
      top_flags: TopFlag[] };

export function Overview() {
  const { L, lang } = useApp();
  const { data, error } = useCall<OverviewData>("overview", { lang });

  const charts = useMemo(() => {
    if (!data || data.empty) return null;
    const counts = CHECK_KEYS.map((k) => [checkLabel(k, lang), data.flags_by_check[k] ?? 0] as const).reverse();
    const byCheck: Data[] = [{
      type: "bar", orientation: "h", x: counts.map((c) => c[1]), y: counts.map((c) => c[0]),
      marker: { color: BLUE, cornerradius: 4 } as any, text: counts.map((c) => String(c[1])), textposition: "outside",
      hovertemplate: "%{y}: %{x}<extra></extra>", cliponaxis: false,
    }];
    const monthly: Data[] = [{
      type: "bar", x: data.monthly.map((m) => m.month), y: data.monthly.map((m) => m.spend),
      customdata: data.monthly.map((m) => m.n) as any, marker: { color: BLUE, cornerradius: 4 } as any,
      hovertemplate: `%{x}<br>%{y:,.0f} lei<br>%{customdata} ${L("invoices").toLowerCase()}<extra></extra>`,
    }];
    return { byCheck, monthly };
  }, [data, lang, L]);

  const cols = useMemo<Col<TopFlag>[]>(() => [
    { key: "severity", label: L("severity"), render: (r) => <SevBadge sev={r.severity} lang={lang} />,
      value: (r) => ({ high: 0, medium: 1, low: 2 })[r.severity] },
    { key: "check_name", label: L("check"), value: (r) => checkLabel(r.check_name, lang) },
    { key: "supplier_name", label: L("supplier") },
    { key: "amount_at_risk_ron", label: L("to_review"), kind: "money" },
    { key: "title", label: L("finding"), value: (r) => (lang === "ro" ? r.title_ro : r.title_en), grow: true },
  ], [L, lang]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading rows={3} />;
  if (data.empty) return <NoData />;
  const ov = data.overview;
  const kpis: [string, string, string?][] = [
    ["invoices", fmtNum(ov.invoices, lang)],
    ["suppliers", fmtNum(ov.suppliers, lang)],
    ["spend", fmtCompact(ov.total_spend_ron, lang), fmtLei(ov.total_spend_ron, lang)],
    ["flags", fmtNum(ov.flags_total, lang)],
    ["to_review", fmtCompact(ov.amount_to_review_ron, lang), fmtLei(ov.amount_to_review_ron, lang)],
  ];
  return (
    <>
      <div className="caption">{ov.company ?? ""} · {L("period")}: {ov.first_date} – {ov.last_date}</div>
      <section className="kpis">
        {kpis.map(([key, value, title]) => (
          <div className="card kpi" key={key} data-testid={`kpi-${key}`} title={title}>
            <div className="kpi-label">{L(key)}</div>
            <div className="kpi-value">{value}</div>
          </div>
        ))}
      </section>
      <section className="grid-2">
        <div className="card">
          <div className="card-head"><h2>{L("flags_by_check")}</h2></div>
          <div className="card-body"><Plot data={charts!.byCheck} layout={{ xaxis: { visible: false } }} testId="chart-by-check" /></div>
        </div>
        <div className="card">
          <div className="card-head"><h2>{L("monthly_spend")}</h2></div>
          <div className="card-body"><Plot data={charts!.monthly} testId="chart-monthly" /></div>
        </div>
      </section>
      <section className="card">
        <div className="card-head"><h2>{L("top_flags")}</h2></div>
        <div className="card-body" style={{ padding: 0, marginTop: 12 }}>
          <DataTable rows={data.top_flags} cols={cols} lang={lang} rowKey={(r) => r.flag_id} testId="top-flags" />
        </div>
      </section>
    </>
  );
}
