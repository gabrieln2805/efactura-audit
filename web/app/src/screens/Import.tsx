import { useMemo, useRef, useState } from "react";
import { CheckCircle2, FolderOpen, Trash2, Upload } from "lucide-react";
import { useApp, useCall } from "../state";
import { Spinner } from "../components/chrome";
import { Confirm } from "../components/Confirm";
import { DataTable, type Col } from "../components/DataTable";
import { Callout, Disclosure, Field } from "../components/ui";
import { fmtNum } from "../i18n";

type TestRow = { status: string; test_name: string; model: string; failures: number; message: string | null };
type LogRow = { logged_at: string; status: string; source: string; message: string | null };
type ImportResult = { summary: string; errors: string[]; flags: number };
type ImportRow = { import_id: string | null; imported_at: string; sources: string | null; buyer_filter: string | null;
                   imported: number; duplicates: number | null; skipped: number | null; other_buyer: number | null;
                   failed: number | null; invoices_kept: number };
type Buyer = { buyer_cui: string | null; buyer_name: string | null; invoices: number };
type Pending =
  | { kind: "remove"; row: ImportRow }
  | { kind: "keep"; buyer: Buyer; others: number }
  | { kind: "reset" }
  | { kind: "demo" };

const ACCEPT = /\.(zip|xml)$/i;
const when = (ts: string) => ts.replace("T", " ").slice(0, 16);

export function Import() {
  const { L, lang, status, busy, mutate, toast } = useApp();
  const [buyer, setBuyer] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [withFeedback, setWithFeedback] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const { data } = useCall<{ tests: TestRow[]; log: LogRow[] }>("import_info");
  const { data: imports } = useCall<ImportRow[]>("imports");
  const { data: buyers } = useCall<Buyer[]>("buyers");
  const hasData = !!status && status.invoices > 0;

  const add = (list: FileList | File[] | null) => {
    if (!list) return;
    const picked = Array.from(list).filter((f) => ACCEPT.test(f.name));   // a folder holds other files too
    setFiles((cur) => [...cur, ...picked]);
  };
  const mb = files.reduce((s, f) => s + f.size, 0) / 1048576;

  const runImport = async () => {
    setResult(null);
    const res = await mutate<ImportResult>("import_files", { buyer_cui: buyer ?? status?.buyer_cui ?? "" }, files);
    if (res) {
      setResult(res);
      setFiles([]);
    }
  };

  const confirm = async () => {
    const p = pending;
    setPending(null);
    if (!p) return;
    setResult(null);
    if (p.kind === "remove") {
      const r = await mutate<{ removed: number }>("delete_import", { import_id: p.row.import_id });
      if (r) toast(L("import_removed", { n: fmtNum(r.removed, lang) }));
    } else if (p.kind === "keep") {
      if (await mutate("keep_buyer", { buyer_cui: p.buyer.buyer_cui })) toast(L("kept_only", { c: p.buyer.buyer_name ?? "" }));
    } else if (p.kind === "reset") {
      if (await mutate("reset", { include_feedback: withFeedback })) toast(L("reset_done"));
      setWithFeedback(false);
    } else if (await mutate("load_demo")) {
      toast(L("demo_loaded"));
    }
  };

  const issues = (data?.tests ?? []).filter((t) => t.status !== "pass");
  const testCols = useMemo<Col<TestRow>[]>(() => [
    { key: "status", label: L("status") }, { key: "test_name", label: L("tests") }, { key: "model", label: L("table") },
    { key: "failures", label: L("rows"), kind: "int" }, { key: "message", label: L("description"), grow: true },
  ], [L]);
  const logCols = useMemo<Col<LogRow>[]>(() => [
    { key: "logged_at", label: L("date"), render: (r) => <span className="num">{r.logged_at.replace("T", " ")}</span> },
    { key: "status", label: L("status") }, { key: "source", label: L("source") },
    { key: "message", label: L("description"), grow: true },
  ], [L]);
  const importCols = useMemo<Col<ImportRow>[]>(() => [
    { key: "imported_at", label: L("date"), render: (r) => <span className="num" style={{ whiteSpace: "nowrap" }}>{when(r.imported_at)}</span> },
    { key: "sources", label: L("files"), grow: true, render: (r) => r.import_id ? (r.sources ?? "") : <i>{L("earlier_imports")}</i> },
    { key: "buyer_filter", label: L("col_cui") },
    { key: "imported", label: L("col_imported"), kind: "int" },
    { key: "duplicates", label: L("col_duplicates"), kind: "int" },
    { key: "skipped", label: L("col_skipped"), kind: "int" },
    { key: "other_buyer", label: L("col_other_buyer"), kind: "int" },
    { key: "failed", label: L("col_failed"), kind: "int" },
    { key: "invoices_kept", label: L("col_kept"), kind: "int" },
    { key: "remove", label: "", render: (r) => (
      <button type="button" className="btn sm" onClick={() => setPending({ kind: "remove", row: r })} disabled={!!busy}
              aria-label={`${L("remove")} ${r.sources ?? L("earlier_imports")}`}>
        <Trash2 size={14} />{L("remove")}
      </button>) },
  ], [L, busy]);
  const total = (buyers ?? []).reduce((s, b) => s + b.invoices, 0);
  const buyerCols = useMemo<Col<Buyer>[]>(() => [
    { key: "buyer_name", label: L("company"), grow: true },
    { key: "buyer_cui", label: L("col_cui") },
    { key: "invoices", label: L("invoices"), kind: "int" },
    { key: "keep", label: "", render: (b) => (
      <button type="button" className="btn sm" disabled={!!busy}
              onClick={() => setPending({ kind: "keep", buyer: b, others: total - b.invoices })}>{L("keep_only")}</button>) },
  ], [L, busy, total]);

  return (
    <>
      <div className="caption">{L("anaf_window")}</div>
      <section className="card detail">
        <Field label={L("buyer_filter")}>
          <input type="text" inputMode="numeric" value={buyer ?? status?.buyer_cui ?? ""} onChange={(e) => setBuyer(e.target.value)} />
        </Field>
        <div className={`dropzone${drag ? " over" : ""}`} data-testid="dropzone"
             onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
             onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}>
          <Upload size={22} />
          <div>{L("upload")}</div>
          <div className="hint">
            {L("drop_files")}{" "}
            <button type="button" className="link" onClick={() => fileInput.current?.click()}>{L("choose_files")}</button>
            {" · "}
            <button type="button" className="link" onClick={() => folderInput.current?.click()}>
              <FolderOpen size={13} style={{ verticalAlign: "-2px" }} /> {L("choose_folder")}
            </button>
          </div>
          <input ref={fileInput} type="file" accept=".zip,.xml" multiple hidden data-testid="file-input"
                 onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          <input ref={folderInput} type="file" multiple hidden {...{ webkitdirectory: "" }}
                 onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        </div>
        {files.length > 0 && (
          <div className="row">
            <span className="caption">{L("files_chosen", { n: files.length, mb: mb.toFixed(1) })}</span>
            <button type="button" className="btn" onClick={() => setFiles([])}>{L("clear")}</button>
          </div>
        )}
        <div className="row">
          <button className="btn primary" onClick={runImport} disabled={!files.length || !!busy}>
            {busy === "import_files" && <Spinner />}{L("import_btn")}
          </button>
          <button className="btn" disabled={!!busy}
                  onClick={() => (hasData ? setPending({ kind: "demo" }) : confirmDemoNow())}>
            {busy === "load_demo" && <Spinner />}{L("load_demo")}
          </button>
        </div>
        {result && (
          <div className="stack" data-testid="import-result">
            <Callout kind="info">{L("imported", { s: result.summary })}</Callout>
            {result.errors.map((e) => <Callout kind="warn" key={e}>{e}</Callout>)}
          </div>
        )}
      </section>

      {buyers && buyers.length > 1 && (
        <section className="card" data-testid="buyers">
          <div className="card-head"><h2>{L("buyers_title")}</h2></div>
          <div className="card-body hint" style={{ paddingBottom: 12 }}>{L("buyers_help")}</div>
          <DataTable rows={buyers} cols={buyerCols} lang={lang} rowKey={(b) => b.buyer_cui ?? "-"} />
        </section>
      )}

      {data && data.tests.length > 0 && (
        <section className="card">
          <div className="card-head"><h2>{L("data_checks")}</h2></div>
          {issues.length === 0
            ? <div className="card-body caption"><CheckCircle2 size={15} className="ok-icon" /> {L("data_checks_ok", { n: data.tests.length })}</div>
            : <div style={{ marginTop: 12 }}><DataTable rows={issues} cols={testCols} lang={lang} /></div>}
        </section>
      )}

      {imports && imports.length > 0 && (
        <section className="card" data-testid="imports">
          <div className="card-head"><h2>{L("imports_title")}</h2></div>
          <div className="card-body hint" style={{ paddingBottom: 12 }}>{L("imports_help")}</div>
          <DataTable rows={imports} cols={importCols} lang={lang} rowKey={(r) => r.import_id ?? "earlier"} maxHeight={360} />
        </section>
      )}

      <Disclosure title={L("import_log")}>
        <DataTable rows={data?.log ?? []} cols={logCols} lang={lang} maxHeight={360} testId="import-log" />
      </Disclosure>

      {hasData && (
        <section className="card detail danger-zone">
          <div>
            <h3 style={{ marginTop: 0 }}>{L("reset_title")}</h3>
            <div className="hint">{L("reset_help")}</div>
          </div>
          <div><button className="btn danger" onClick={() => setPending({ kind: "reset" })} disabled={!!busy} data-testid="reset">
            {busy === "reset" ? <Spinner /> : <Trash2 size={15} />}{L("reset_btn")}
          </button></div>
        </section>
      )}

      <Confirm open={pending !== null} onCancel={() => { setPending(null); setWithFeedback(false); }} onConfirm={confirm}
               danger={pending?.kind !== "demo"}
               title={pending?.kind === "remove" ? L("remove_import_title")
                 : pending?.kind === "keep" ? L("keep_only_title", { c: pending.buyer.buyer_name ?? "" })
                 : pending?.kind === "reset" ? L("reset_confirm_title") : L("demo_replace_title")}
               confirmLabel={pending?.kind === "remove" ? L("remove") : pending?.kind === "keep" ? L("keep_only")
                 : pending?.kind === "reset" ? L("reset_btn") : L("load_demo")}>
        {pending?.kind === "remove" && <p>{L("remove_import_body", { n: fmtNum(pending.row.invoices_kept, lang), d: when(pending.row.imported_at) })}</p>}
        {pending?.kind === "keep" && <p>{L("keep_only_body", { n: fmtNum(pending.others, lang) })}</p>}
        {pending?.kind === "demo" && <p>{L("demo_replace_body")}</p>}
        {pending?.kind === "reset" && (
          <>
            <p>{L("reset_confirm_body")}</p>
            <label className="check"><input type="checkbox" checked={withFeedback} onChange={(e) => setWithFeedback(e.target.checked)} />
              <span>{L("reset_feedback")}</span></label>
          </>
        )}
      </Confirm>
    </>
  );

  async function confirmDemoNow() {
    if (await mutate("load_demo")) toast(L("demo_loaded"));
  }
}
