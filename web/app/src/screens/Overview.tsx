import { useApp, useCall } from "../state";
import { ErrorNote, Loading, NoData } from "../components/chrome";
import { fmtCompact, fmtLei, fmtNum } from "../i18n";

type OverviewData =
  | { empty: true }
  | { empty: false; overview: { invoices: number; suppliers: number; total_spend_ron: number; flags_total: number;
                                amount_to_review_ron: number; company: string | null; first_date: string; last_date: string } };

export function Overview() {
  const { L, lang } = useApp();
  const { data, error } = useCall<OverviewData>("overview", { lang });
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
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
      <div className="hint">{ov.company ?? ""} · {L("period")}: {ov.first_date} – {ov.last_date}</div>
      <section className="kpis">
        {kpis.map(([key, value, title]) => (
          <div className="card kpi" key={key} data-testid={`kpi-${key}`} title={title}>
            <div className="kpi-label">{L(key)}</div>
            <div className="kpi-value">{value}</div>
          </div>
        ))}
      </section>
      <div className="disclaimer">{L("disclaimer")}</div>
    </>
  );
}
