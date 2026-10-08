// AI assistant: the same tool-calling assistant as the Streamlit app, running in the browser's engine.
// Cloud providers are off by default (Settings) and use the user's own key, kept in memory for this visit only.
import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { ArrowUp, Lock, RotateCcw, Sparkles } from "lucide-react";
import { engine, useApp, useCall, usePref } from "../state";
import { NoData, Spinner } from "../components/chrome";
import { Callout, Disclosure, Field, JsonTree } from "../components/ui";
import { EXAMPLES } from "../i18n";

type Trace = { name: string; arguments: Record<string, unknown>; result: unknown };
type Msg = { role: "user" | "assistant"; content: string; trace?: Trace[] };
type Options = { providers: string[]; cloud: string[]; models: { model: string; approved: boolean }[] };

// conversation and keys live for this visit only (like Streamlit's session state), never in storage
let chat: Msg[] = [];
export const sessionKeys = new Map<string, string>();

function Markdown({ text }: { text: string }) {
  // answers can quote invoice text, so the HTML is sanitized
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text, { async: false }) as string), [text]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Assistant() {
  const { L, lang, status } = useApp();
  const [cloudEnabled] = usePref("cloud_enabled", false);
  const [allowUntested] = usePref("allow_untested", false);
  const [provider, setProvider] = useState("ollama");
  const { data: opts } = useCall<Options>("assistant_options", { provider, cloud_enabled: cloudEnabled, allow_untested: allowUntested });
  const [model, setModel] = useState<string | null>(null);
  const [key, setKey] = useState(() => sessionKeys.get(provider) ?? "");
  const [messages, setMessages] = useState<Msg[]>(chat);
  const [question, setQuestion] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { chat = messages; endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);
  useEffect(() => { setKey(sessionKeys.get(provider) ?? ""); setModel(null); }, [provider]);
  const cloud = opts?.cloud.includes(provider) ?? false;
  const chosen = opts?.models.find((m) => m.model === model) ?? opts?.models[0] ?? null;

  const ask = async (q: string) => {
    if (!q.trim() || !chosen) return;
    setError(null);
    setThinking(true);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setQuestion("");
    try {
      const history = messages.slice(-8).map(({ role, content }) => ({ role, content }));
      const ans = await engine.call<{ text: string; error: string | null; trace: Trace[] }>("ask", {
        provider, model: chosen.model, question: q, history, api_key: cloud ? key : "", lang });
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

  return (
    <>
      <Callout kind="info">{L("ai_label")}</Callout>
      <section className="card filters">
        <Field label={L("provider")}>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} data-testid="provider">
            {(opts?.providers ?? ["ollama"]).map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label={L("model")} grow={1.4}>
          <select value={chosen?.model ?? ""} onChange={(e) => setModel(e.target.value)} disabled={!opts?.models.length} data-testid="model">
            {(opts?.models ?? []).map((m) => <option key={m.model} value={m.model}>{m.approved ? m.model : `${m.model} (${L("untested")})`}</option>)}
          </select>
        </Field>
        {cloud && (
          <Field label={L("api_key")} grow={1.4}>
            <input type="password" autoComplete="off" value={key}
                   onChange={(e) => { setKey(e.target.value); sessionKeys.set(provider, e.target.value); }} />
          </Field>
        )}
      </section>
      {cloud ? <Callout kind="warn">{L("cloud_warning", { p: provider })}</Callout>
        : <div className="caption"><Lock size={13} style={{ verticalAlign: "-2px" }} /> {L("local_model")}</div>}

      {opts && !chosen ? <Callout kind="warn">{L("no_models")}</Callout>
        : status && status.invoices === 0 ? <NoData /> : (
        <section className="card chat">
          <div className="chat-log" data-testid="chat-log">
            {messages.length === 0 && (
              <div className="chat-empty">
                <Sparkles size={22} />
                <div className="hint">{L("examples")}</div>
                <div className="examples">
                  {EXAMPLES[lang].map((ex) => <button key={ex} className="chip-btn" onClick={() => ask(ex)} disabled={thinking || !chosen}>{ex}</button>)}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="msg-who">{m.role === "user" ? L("you") : <><Sparkles size={13} /> {chosen?.model ?? "AI"}</>}</div>
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
                   disabled={thinking || !chosen} data-testid="chat-input" />
            <button className="btn primary" type="submit" disabled={thinking || !question.trim() || !chosen} aria-label={L("send")}>
              <ArrowUp size={16} />
            </button>
          </form>
          {messages.length > 0 && <div className="hint" style={{ padding: "0 16px 12px" }}>{L("examples")}: {EXAMPLES[lang].join(" · ")}</div>}
        </section>
      )}
    </>
  );
}
