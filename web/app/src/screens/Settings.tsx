import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";
import { useApp, useCall, usePref } from "../state";
import { Spinner } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { Callout, Disclosure, Field, JsonTree, Toggle } from "../components/ui";
import { HOSTED, sessionKeys, useHostedInfo, useModelTest } from "../ai";

type Tested = { provider: string; model: string; score: number; structured_ok: boolean; passed: boolean; tested_at: string };
type Feedback = { check_name: string; rule: string; confirmed: number; dismissed: number };
type SettingsData = { settings: Record<string, unknown>; feedback: Feedback[] };

function DeveloperOptions({ tested, reloadTested }: { tested?: Tested[]; reloadTested: () => void }) {
  const { L, lang } = useApp();
  const hosted = useHostedInfo();
  const [cloudEnabled, setCloudEnabled] = usePref("cloud_enabled", false);
  const [allowUntested, setAllowUntested] = usePref("allow_untested", false);
  const { data: ollama } = useCall<{ url: string; models: string[] }>("ollama_status");
  const providers = [...(hosted?.available ? [HOSTED] : []), "ollama", ...(cloudEnabled ? ["anthropic", "mistral", "openai"] : [])];
  const [tprov, setTprov] = useState<string | null>(null);
  const prov = tprov ?? providers[0];
  const { data: suggestions } = useCall<string[]>("model_suggestions", { provider: prov }, prov !== HOSTED);
  const [tmodel, setTmodel] = useState("");
  const [tkey, setTkey] = useState("");
  const test = useModelTest(() => reloadTested());
  const model = prov === HOSTED ? hosted?.model ?? "" : tmodel || suggestions?.[0] || "";
  const ollamaOff = prov === "ollama" && !!ollama && ollama.models.length === 0;
  const needsKey = prov !== "ollama" && prov !== HOSTED;

  const testedCols = useMemo<Col<Tested>[]>(() => [
    { key: "provider", label: L("provider") }, { key: "model", label: L("model") },
    { key: "score", label: L("score"), kind: "num" }, { key: "structured_ok", label: "structured_ok", kind: "bool" },
    { key: "passed", label: "passed", kind: "bool" }, { key: "tested_at", label: L("date"), kind: "date" },
  ], [L]);

  return (
    <>
      <Toggle label={L("cloud_enable")} checked={cloudEnabled} onChange={setCloudEnabled} />
      <Toggle label={L("allow_untested")} checked={allowUntested} onChange={setAllowUntested} />
      {ollama && (
        <div className="hint" data-testid="ollama-status">
          {ollama.models.length ? L("ollama_status", { n: ollama.models.length }) : `${L("ollama_off", { u: ollama.url })} ${L("no_ollama_web")}`}
        </div>
      )}
      <div><h3 style={{ margin: "8px 0 2px" }}>{L("model_test")}</h3><div className="hint">{L("model_test_help")}</div></div>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <Field label={L("provider")}>
          <select value={prov} data-testid="test-provider"
                  onChange={(e) => { setTprov(e.target.value); setTmodel(""); setTkey(sessionKeys.get(e.target.value) ?? ""); }}>
            {providers.map((p) => <option key={p} value={p}>{p === HOSTED ? L("hosted_name") : p}</option>)}
          </select>
        </Field>
        <Field label={L("model")} grow={1.4}>
          <input type="text" list="model-suggestions" value={model} readOnly={prov === HOSTED} onChange={(e) => setTmodel(e.target.value)} />
          <datalist id="model-suggestions">{(suggestions ?? []).map((m) => <option key={m} value={m} />)}</datalist>
        </Field>
        {needsKey && (
          <Field label={L("api_key")} grow={1.4}>
            <input type="password" autoComplete="off" value={tkey} onChange={(e) => { setTkey(e.target.value); sessionKeys.set(prov, e.target.value); }} />
          </Field>
        )}
        <button className="btn primary" onClick={() => test.run(prov, model, needsKey ? tkey : "")}
                disabled={!model || test.running || ollamaOff} data-testid="run-model-test">
          {test.running ? <Spinner /> : <FlaskConical size={15} />}{L("run_test")}
        </button>
      </div>
      {ollamaOff && <Callout kind="warn">{L("ollama_off", { u: ollama!.url })} {L("no_ollama_web")}</Callout>}
      {test.running && test.log.length > 0 && <div className="error-box" aria-label={L("test_log")}>{test.log.join("\n")}</div>}
      {test.result && (
        <>
          <Callout kind={test.result.passed ? "info" : "warn"}>{test.result.summary.split("\n")[0]}</Callout>
          <pre className="code">{test.result.summary}</pre>
        </>
      )}
      {test.error && <Callout kind="warn">{L("error")}: {test.error}</Callout>}
      {tested && tested.length > 0 && (
        <>
          <div className="section-title">{L("approved_models")}</div>
          <div className="card" style={{ boxShadow: "none" }}><DataTable rows={tested} cols={testedCols} lang={lang} /></div>
        </>
      )}
    </>
  );
}

export function Settings() {
  const { L, lang } = useApp();
  const hosted = useHostedInfo();
  const [devMode, setDevMode] = usePref("dev_mode", false);
  const { data: settings } = useCall<SettingsData>("settings");
  const { data: tested, reload: reloadTested } = useCall<Tested[]>("tested_models");
  const hostedOk = !!hosted?.available && (hosted.approved || (tested ?? []).some((t) => t.provider === HOSTED && t.model === hosted.model && t.passed));
  const fbCols = useMemo<Col<Feedback>[]>(() => [
    { key: "check_name", label: L("check") }, { key: "rule", label: "rule" },
    { key: "confirmed", label: "confirmed", kind: "int" }, { key: "dismissed", label: "dismissed", kind: "int" },
  ], [L]);

  return (
    <>
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

      <section className="card detail" data-testid="ai-status">
        <h3 style={{ marginTop: 0 }}>{L("ai_section")}</h3>
        <div className="caption">
          {!hosted ? <Spinner size={13} /> : !hosted.available ? L("ai_not_set_up")
            : L(hostedOk ? "ai_status_ok" : "ai_status_untested", { m: hosted.model ?? "", u: hosted.upstream ?? "" })}
        </div>
        {hosted && !hosted.available && hosted.reason && <div className="error-box">{hosted.reason}</div>}
      </section>

      <section className="card detail">
        <Toggle label={L("dev_options")} checked={devMode} onChange={setDevMode} />
        <div className="hint">{L("dev_options_help")}</div>
        {devMode && <DeveloperOptions tested={tested} reloadTested={reloadTested} />}
      </section>
    </>
  );
}
