import { useState } from "react";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useApp } from "../state";
import { NoData, Spinner } from "../components/chrome";
import { Segmented } from "../components/ui";
import type { Lang } from "../i18n";
import { download } from "./Data";

const TYPES = { xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", pdf: "application/pdf" };
type Kind = keyof typeof TYPES;

export function Report() {
  const { L, lang, status, busy, mutate } = useApp();
  const [rlang, setRlang] = useState<Lang>(lang);
  const [built, setBuilt] = useState<Partial<Record<Kind, { bytes: Uint8Array; lang: Lang }>>>({});
  const [building, setBuilding] = useState<Kind | null>(null);
  if (status && status.invoices === 0) return <NoData />;

  const build = async (kind: Kind) => {
    setBuilding(kind);
    const bytes = await mutate<Uint8Array>("report", { kind, lang: rlang });
    setBuilding(null);
    if (bytes) setBuilt((b) => ({ ...b, [kind]: { bytes, lang: rlang } }));
  };
  const card = (kind: Kind, label: string, Icon: typeof FileText) => {
    const file = built[kind];
    return (
      <div className="card detail report-card">
        <Icon size={26} className="report-icon" />
        <button className="btn" onClick={() => build(kind)} disabled={!!busy} data-testid={`build-${kind}`}>
          {building === kind && <Spinner />}{label}
        </button>
        {file && (
          <button className="btn primary" data-testid={`download-${kind}`}
                  onClick={() => download(file.bytes as BlobPart, `clarifact-${file.lang}.${kind}`, TYPES[kind])}>
            <Download size={15} />{L("download")} .{kind}
          </button>
        )}
      </div>
    );
  };
  return (
    <>
      <div className="row">
        <span className="field-label">{L("report_lang")}</span>
        <Segmented ariaLabel={L("report_lang")} options={["ro", "en"] as Lang[]} value={rlang} onChange={setRlang}
                   render={(l) => (l === "ro" ? "Română" : "English")} />
      </div>
      <section className="grid-even">
        {card("xlsx", L("make_excel"), FileSpreadsheet)}
        {card("pdf", L("make_pdf"), FileText)}
      </section>
    </>
  );
}
