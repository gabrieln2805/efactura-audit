// Shell pieces: engine start-up card, engine status chip, spinner, toasts, and the no-data state.
import { AlertTriangle, Check, CheckCircle2, Circle, Database, LoaderCircle, Upload } from "lucide-react";
import type { EngineState } from "../engine/client";
import { STAGES } from "../engine/protocol";
import { useApp } from "../state";

export function Spinner({ size = 15 }: { size?: number }) {
  return <LoaderCircle size={size} className="spin" />;
}

export function EngineSplash() {
  const { engine, L } = useApp();
  if (engine.phase === "locked" || engine.phase === "error") {
    return (
      <div className="card center-card" role="alert">
        <h2>{engine.phase === "locked" ? L("other_tab") : L("engine_error")}</h2>
        {engine.phase === "error" && <div className="error-box">{engine.error}</div>}
        <div className="empty-actions">
          <button className="btn primary" onClick={() => location.reload()}>{L("reload")}</button>
        </div>
      </div>
    );
  }
  if (engine.phase !== "loading") return null;
  const current = STAGES.indexOf(engine.stage);
  const pct = ((current + (engine.total ? engine.done / engine.total : 0)) / STAGES.length) * 100;
  return (
    <div className="card center-card" aria-busy="true">
      <h2>{L("engine_loading")}</h2>
      <div className="hint">{L("first_visit")}</div>
      <ol className="stages">
        {STAGES.map((s, i) => (
          <li key={s} className={i < current ? "done" : i === current ? "active" : ""}>
            {i < current ? <Check size={16} className="tick" /> : i === current ? <Spinner size={16} /> : <Circle size={16} />}
            {L(`stage_${s}`)}
            {i === current && engine.total > 0 && <span className="count">{engine.done} / {engine.total}</span>}
          </li>
        ))}
      </ol>
      <div className="progress"><div style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export function EngineChip({ state, version }: { state: EngineState; version?: string }) {
  const { L, busy } = useApp();
  const cls = state.phase === "ready" ? (busy ? "busy" : "ok") : state.phase === "loading" ? "busy" : "bad";
  const text = state.phase === "ready" ? (busy ? L("working") : L("engine_ready"))
    : state.phase === "loading" ? L(`stage_${state.stage}`) : state.phase === "locked" ? L("other_tab") : L("engine_error");
  return (
    <div className="engine-chip" data-testid="engine-chip" data-phase={state.phase}>
      <span className={`dot ${cls}`} />
      <span>{text}{version ? ` · v${version}` : ""}</span>
    </div>
  );
}

export function Toasts() {
  const { toasts } = useApp();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          {t.kind === "error" ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

/** Shown on data screens while the workspace has no invoices: load the demo or go to Import. */
export function NoData() {
  const { L, busy, mutate, toast } = useApp();
  const loadDemo = async () => {
    if (await mutate("load_demo")) toast(L("demo_loaded"));
  };
  return (
    <div className="card center-card">
      <h2><Database size={18} style={{ verticalAlign: "-3px", marginRight: 8 }} />{L("no_data").split(". ")[0]}.</h2>
      <div className="hint">{L("no_data").split(". ").slice(1).join(". ")}</div>
      <div className="empty-actions">
        <button className="btn primary" onClick={loadDemo} disabled={!!busy}>
          {busy === "load_demo" && <Spinner />}{L("load_demo")}
        </button>
        <a className="btn" href="#/import"><Upload size={15} />{L("tab_import")}</a>
      </div>
    </div>
  );
}

/** Placeholder while a screen's first query runs. */
export function Loading({ rows = 2 }: { rows?: number }) {
  return <div className="skeleton" aria-busy="true">{Array.from({ length: rows }, (_, i) => <div key={i} />)}</div>;
}

/** A query error, with the engine's message. */
export function ErrorNote({ error }: { error: string }) {
  const { L } = useApp();
  return <div className="card center-card" role="alert"><h2>{L("error")}</h2><div className="error-box">{error}</div></div>;
}
