import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";
import { useApp, useCall, usePref } from "../state";
import { Spinner } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { Callout, Disclosure, Field, JsonTree, Toggle } from "../components/ui";
import { sessionKeys } from "./Assistant";

type Tested = { provider: string; model: string; score: number; structured_ok: boolean; passed: boolean; tested_at: string };
type Feedback = { check_name: string; rule: string; confirmed: number; dismissed: number };
type SettingsData = { settings: Record<string, unknown>; feedback: Feedback[] };

export function Settings() {
  const { L, lang, busy, mutate } = useApp();
  const [cloudEnabled, setCloudEnabled] = usePref("cloud_enabled", false);
  const [allowUntested, setAllowUntested] = usePref("allow_untested", false);
  const { data: ollama } = useCall<{ url: string; models: string[] }>("ollama_status");
  const { data: settings } = useCall<SettingsData>("settings");
  const { data: tested } = useCall<Tested[]>("tested_models");
  const providers = ["ollama", ...(cloudEnabled ? ["anthropic", "mistral", "openai"] : [])];
  const [tprov, setTprov] = useState("ollama");
  const { data: suggestions } = useCall<string[]>("model_suggestions", { provider: tprov });
  const [tmodel, setTmodel] = useState("");
  const [tkey, setTkey] = useState(() => sessionKeys.get(tprov) ?? "");
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<{ passed: boolean; summary: string } | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const model = tmodel || suggestions?.[0] || "";

  const runTest = async () => {
    setLog([]);
    setResult(null);
    setTestError(null);
    const res = await mutate<{ passed: boolean; summary: string }>(
      "model_test", { provider: tprov, model, api_key: tprov === "ollama" ? "" : tkey }, undefined,
      (line) => setLog((l) => [...l.slice(-30), line]));
    if (res) setResult(res);
    else setTestError(L("error"));
  };

  const testedCols = useMemo<Col<Tested>[]>(() => [
    { key: "provider", label: L("provider") }, { key: "model", label: L("model") },
    { key: "score", label: L("score"), kind: "num" }, { key: "structured_ok", label: "structured_ok", kind: "bool" },
    { key: "passed", label: "passed", kind: "bool" }, { key: "tested_at", label: L("date"), kind: "date" },
  ], [L]);
  const fbCols = useMemo<Col<Feedback>[]>(() => [
    { key: "check_name", label: L("check") }, { key: "rule", label: "rule" },
    { key: "confirmed", label: "confirmed", kind: "int" }, { key: "dismissed", label: "dismissed", kind: "int" },
  ], [L]);

  return (
    <>
      <section className="card detail">
        <Toggle label={L("cloud_enable")} checked={cloudEnabled} onChange={setCloudEnabled} />
        <Toggle label={L("allow_untested")} checked={allowUntested} onChange={setAllowUntested} />
        {ollama && (
          <div className="hint" data-testid="ollama-status">
            {ollama.models.length ? L("ollama_status", { n: ollama.models.length }) : `${L("ollama_off", { u: ollama.url })} ${L("no_ollama_web")}`}
          </div>
        )}
      </section>

      <section className="card detail">
        <div><h3 style={{ marginTop: 0 }}>{L("model_test")}</h3><div className="hint">{L("model_test_help")}</div></div>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <Field label={L("provider")}>
            <select value={tprov} onChange={(e) => { setTprov(e.target.value); setTmodel(""); setTkey(sessionKeys.get(e.target.value) ?? ""); }}>
              {providers.map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label={L("model")} grow={1.4}>
            <input type="text" list="model-suggestions" value={model} onChange={(e) => setTmodel(e.target.value)} />
            <datalist id="model-suggestions">{(suggestions ?? []).map((m) => <option key={m} value={m} />)}</datalist>
          </Field>
          {tprov !== "ollama" && (
            <Field label={L("api_key")} grow={1.4}>
              <input type="password" autoComplete="off" value={tkey} onChange={(e) => { setTkey(e.target.value); sessionKeys.set(tprov, e.target.value); }} />
            </Field>
          )}
          <button className="btn primary" onClick={runTest} disabled={!model || !!busy}>
            {busy === "model_test" ? <Spinner /> : <FlaskConical size={15} />}{L("run_test")}
          </button>
        </div>
        {log.length > 0 && !result && <div className="error-box" aria-label={L("test_log")}>{log.join("\n")}</div>}
        {result && (
          <>
            <Callout kind={result.passed ? "info" : "warn"}>{result.summary.split("\n")[0]}</Callout>
            <pre className="code">{result.summary}</pre>
          </>
        )}
        {testError && !result && <Callout kind="warn">{testError}</Callout>}
        {tested && tested.length > 0 && (
          <>
            <div className="section-title">{L("approved_models")}</div>
            <div className="card" style={{ boxShadow: "none" }}><DataTable rows={tested} cols={testedCols} lang={lang} /></div>
          </>
        )}
      </section>

      <section className="card detail">
        <h3 style={{ marginTop: 0 }}>{L("feedback_stats")}</h3>
        {settings && settings.feedback.length > 0 && (
          <div className="card" style={{ boxShadow: "none" }}><DataTable rows={settings.feedback} cols={fbCols} lang={lang} testId="feedback-stats" /></div>
        )}
        <div className="hint">{L("thresholds_web")}</div>
        {settings && (
          <Disclosure title="config_default.toml">
            <div className="json"><JsonTree value={settings.settings} depth={1} /></div>
          </Disclosure>
        )}
      </section>
    </>
  );
}
