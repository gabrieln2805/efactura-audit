import { useMemo, useRef, useState } from "react";
import { CheckCircle2, FolderOpen, Upload } from "lucide-react";
import { useApp, useCall } from "../state";
import { Spinner } from "../components/chrome";
import { DataTable, type Col } from "../components/DataTable";
import { Callout, Field } from "../components/ui";

type TestRow = { status: string; test_name: string; model: string; failures: number; message: string | null };
type LogRow = { logged_at: string; status: string; source: string; message: string | null };
type ImportResult = { summary: string; errors: string[]; flags: number };

const ACCEPT = /\.(zip|xml)$/i;

export function Import() {
  const { L, lang, status, busy, mutate, toast } = useApp();
  const [buyer, setBuyer] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const { data } = useCall<{ tests: TestRow[]; log: LogRow[] }>("import_info");

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
  const loadDemo = async () => {
    if (await mutate("load_demo")) toast(L("demo_loaded"));
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
          <button className="btn" onClick={loadDemo} disabled={!!busy}>
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

      {data && data.tests.length > 0 && (
        <section className="card">
          <div className="card-head"><h2>{L("data_checks")}</h2></div>
          {issues.length === 0
            ? <div className="card-body caption"><CheckCircle2 size={15} className="ok-icon" /> {L("data_checks_ok", { n: data.tests.length })}</div>
            : <div style={{ marginTop: 12 }}><DataTable rows={issues} cols={testCols} lang={lang} /></div>}
        </section>
      )}
      <section className="card">
        <div className="card-head"><h2>{L("import_log")}</h2></div>
        <div style={{ marginTop: 12 }}>
          <DataTable rows={data?.log ?? []} cols={logCols} lang={lang} maxHeight={360} testId="import-log" />
        </div>
      </section>
    </>
  );
}
