// Placeholder for the screens that come in milestones B2 and B3.
import { useApp } from "../state";
import { NoData } from "../components/chrome";

export function Pending() {
  const { L, status } = useApp();
  if (status && status.invoices === 0) return <NoData />;
  return <div className="card center-card"><div className="hint">{L("screen_pending")}</div></div>;
}
