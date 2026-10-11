// AI assistant: the same tool-calling assistant as the Streamlit app, running in the browser's engine.
// Users get the site's own assistant (our server adds the model key). Ollama and cloud models with the user's own
// key are developer options (Settings); such keys stay in memory for this visit only.
import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { ArrowUp, FlaskConical, Lock, RotateCcw, Settings as SettingsIcon, Sparkles } from "lucide-react";
import { engine, useApp, useCall, usePref } from "../state";
import { Loading, NoData, Spinner } from "../components/chrome";
import { Callout, Disclosure, Field, JsonTree } from "../components/ui";
import { EXAMPLES } from "../i18n";
import { HOSTED, sessionKeys, useHostedInfo, useModelTest } from "../ai";

type Trace = { name: string; arguments: Record<string, unknown>; result: unknown };
type Msg = { role: "user" | "assistant"; content: string; trace?: Trace[] };
type Options = { providers: string[]; provider: string | null; cloud: string[]; models: { model: string; approved: boolean }[];
                 hosted_untested: boolean };

// the conversation lives for this visit only (like Streamlit's session state), never in storage
let chat: Msg[] = [];

function Markdown({ text }: { text: string }) {
  // answers can quote invoice text, so the HTML is sanitized
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text, { async: false }) as string), [text]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** The site's model has not passed the Romanian test: explain, and let the operator run it here. */
function HostedUntested({ model, onPassed }: { model: string; onPassed: () => void }) {
  const { L } = useApp();
  const test = useModelTest((r) => r.passed && onPassed());
  return (
    <section className="card detail" data-testid="hosted-untested">
      <Callout kind="warn">{L("hosted_untested", { m: model })}</Callout>
      <div className="hint">{L("hosted_untested_help")}</div>
      <div><button className="btn primary" onClick={() => test.run(HOSTED, model)} disabled={test.running}>
        {test.running ? <Spinner /> : <FlaskConical size={15} />}{L("run_test_now")}
      </button></div>
      {test.running && test.log.length > 0 && <div className="error-box" aria-label={L("test_log")}>{test.log.join("\n")}</div>}
      {test.result && (
        <>
          <Callout kind={test.result.passed ? "info" : "warn"}>{test.result.passed ? L("test_passed") : test.result.summary.split("\n")[0]}</Callout>
          {!test.result.passed && <pre className="code">{test.result.summary}</pre>}
        </>
      )}
      {test.error && <Callout kind="warn">{L("error")}: {test.error}</Callout>}
    </section>
  );
}

/** The assistant is parked: users see what is coming; developer options (Settings) open the working version. */
export function Assistant() {
  const [devMode] = usePref("dev_mode", false);
  return devMode ? <AssistantChat /> : <AssistantSoon />;
}

function AssistantSoon() {
  const { L, lang } = useApp();
  return (
    <section className="card center-card soon-card" data-testid="ai-soon">
      <Sparkles size={24} className="feature-icon" />
      <h2>{L("ai_soon_title")}</h2>
      <p className="hint">{L("ai_soon_body")}</p>
      <div className="examples" aria-hidden="true">
        {EXAMPLES[lang].map((ex) => <span key={ex} className="chip-btn static">{ex}</span>)}
      </div>
    </section>
  );
}

function AssistantChat() {
  const { L, lang, status } = useApp();
  const hosted = useHostedInfo();
  const [devMode] = usePref("dev_mode", false);
  const [cloudEnabled] = usePref("cloud_enabled", false);
  const [allowUntested] = usePref("allow_untested", false);
  const [provider, setProvider] = useState<string | null>(null);
  const { data: opts, reload } = useCall<Options>("assistant_options", {
    provider, dev_mode: devMode, cloud_enabled: cloudEnabled, allow_untested: allowUntested,
    hosted_model: hosted?.available ? hosted.model : null, hosted_approved: !!hosted?.approved,
  }, hosted !== null);
  const [model, setModel] = useState<string | null>(null);
  const current = opts?.provider ?? null;
  const [key, setKey] = useState("");
  const [messages, setMessages] = useState<Msg[]>(chat);
  const [question, setQuestion] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { chat = messages; endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);
  useEffect(() => { setKey(sessionKeys.get(current ?? "") ?? ""); setModel(null); }, [current]);
  const ownKey = !!current && (opts?.cloud.includes(current) ?? false);
  const chosen = opts?.models.find((m) => m.model === model) ?? opts?.models[0] ?? null;

  const ask = async (q: string) => {
    if (!q.trim() || !chosen || !current) return;
    setError(null);
    setThinking(true);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setQuestion("");
    try {
      const history = messages.slice(-8).map(({ role, content }) => ({ role, content }));
      const ans = await engine.call<{ text: string; error: string | null; trace: Trace[] }>("ask", {
        provider: current, model: chosen.model, question: q, history, api_key: ownKey ? key : "", lang });
      const text = ans.error ? `**${L("error")}:** ${ans.error}` : ans.text;
      setMessages((m) => [...m, { role: "assistant", content: text, trace: ans.trace }]);
    } catch (e) {
      setMessages((m) => m.slice(0, -1));   // like Streamlit: a failed call is not kept in the conversation
      setQuestion(q);
      setError((e as Error).message);
    } finally {
      setThinking(false);
    }
  };

  if (status && status.invoices === 0) return <NoData />;
  if (!opts) return <><Callout kind="info">{L("ai_label")}</Callout><Loading rows={1} /></>;

  return (
    <>
      <Callout kind="info">{L("ai_label")}</Callout>

      {opts.providers.length === 0 ? (
        <section className="card center-card" data-testid="ai-not-set-up">
          <h2>{L("ai_not_set_up")}</h2>
          <div className="hint">{L("ai_not_set_up_help")}</div>
          {hosted?.reason && <div className="error-box" data-testid="ai-reason">{hosted.reason}</div>}
          <div className="empty-actions"><a className="btn" href="#/settings"><SettingsIcon size={15} />{L("go_settings")}</a></div>
        </section>
      ) : (
        <>
          {devMode && (
            <section className="card filters">
              <Field label={L("provider")}>
                <select value={current ?? ""} onChange={(e) => setProvider(e.target.value)} data-testid="provider">
                  {opts.providers.map((p) => <option key={p} value={p}>{p === HOSTED ? L("hosted_name") : p}</option>)}
                </select>
              </Field>
              <Field label={L("model")} grow={1.4}>
                <select value={chosen?.model ?? ""} onChange={(e) => setModel(e.target.value)} disabled={!opts.models.length} data-testid="model">
                  {opts.models.map((m) => <option key={m.model} value={m.model}>{m.approved ? m.model : `${m.model} (${L("untested")})`}</option>)}
                </select>
              </Field>
              {ownKey && (
                <Field label={L("api_key")} grow={1.4}>
                  <input type="password" autoComplete="off" value={key}
                         onChange={(e) => { setKey(e.target.value); sessionKeys.set(current!, e.target.value); }} />
                </Field>
              )}
            </section>
          )}
          {current === HOSTED ? <div className="caption"><Lock size={13} style={{ verticalAlign: "-2px" }} /> {L("hosted_note", { m: hosted?.model ?? "" })}</div>
            : ownKey ? <Callout kind="warn">{L("cloud_warning", { p: current! })}</Callout>
            : <div className="caption"><Lock size={13} style={{ verticalAlign: "-2px" }} /> {L("local_model")}</div>}

          {opts.hosted_untested ? <HostedUntested model={hosted?.model ?? ""} onPassed={reload} />
            : !chosen ? <Callout kind="warn">{L("no_models")}</Callout> : (
            <section className="card chat">
              <div className="chat-log" data-testid="chat-log">
                {messages.length === 0 && (
                  <div className="chat-empty">
                    <Sparkles size={22} />
                    <div className="hint">{L("examples")}</div>
                    <div className="examples">
                      {EXAMPLES[lang].map((ex) => <button key={ex} className="chip-btn" onClick={() => ask(ex)} disabled={thinking}>{ex}</button>)}
                    </div>
                  </div>
                )}
                {messages.map((m, i) => (
                  <div key={i} className={`msg ${m.role}`}>
                    <div className="msg-who">{m.role === "user" ? L("you") : <><Sparkles size={13} /> {current === HOSTED ? "auditefactura.ro" : chosen.model}</>}</div>
                    {m.role === "user" ? <div className="msg-text">{m.content}</div> : <Markdown text={m.content} />}
                    {m.trace && m.trace.length > 0 && (
                      <Disclosure title={L("sources", { n: m.trace.length })}>
                        {m.trace.map((t, j) => (
                          <div key={j} className="stack" style={{ gap: 4 }}>
                            <code className="mono">{t.name}({JSON.stringify(t.arguments)})</code>
                            <div className="json"><JsonTree value={t.result} depth={0} /></div>
                          </div>
                        ))}
                      </Disclosure>
                    )}
                  </div>
                ))}
                {thinking && <div className="msg assistant"><div className="hint"><Spinner size={13} /> {L("thinking")}</div></div>}
                <div ref={endRef} />
              </div>
              {error && <div className="error-box" role="alert">{error}</div>}
              <form className="chat-input" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
                {messages.length > 0 && (
                  <button type="button" className="btn" onClick={() => setMessages([])} title={L("clear_chat")} aria-label={L("clear_chat")}>
                    <RotateCcw size={15} />
                  </button>
                )}
                <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={L("ask_placeholder")}
                       disabled={thinking} data-testid="chat-input" />
                <button className="btn primary" type="submit" disabled={thinking || !question.trim()} aria-label={L("send")}>
                  <ArrowUp size={16} />
                </button>
              </form>
              {messages.length > 0 && <div className="hint" style={{ padding: "0 16px 12px" }}>{L("examples")}: {EXAMPLES[lang].join(" · ")}</div>}
            </section>
          )}
        </>
      )}
    </>
  );
}
