// Small form and display pieces shared by the screens.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, Info, TriangleAlert } from "lucide-react";
import { CHECKS, SEVERITY, STATUS, pick, type Lang } from "../i18n";

export function SevBadge({ sev, lang }: { sev: string; lang: Lang }) {
  return <span className={`sev sev-${sev}`}><i />{pick(SEVERITY, sev, lang)}</span>;
}

export function StatusBadge({ status, lang }: { status: string; lang: Lang }) {
  return <span className={`status status-${status}`}>{pick(STATUS, status, lang)}</span>;
}

export const checkLabel = (c: string, lang: Lang) => pick(CHECKS, c, lang);

export function Field({ label, children, grow }: { label: string; children: ReactNode; grow?: number }) {
  return (
    <label className="field" style={grow ? { flex: grow } : undefined}>
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track"><span /></span>
      {label}
    </label>
  );
}

/** Dropdown of checkboxes; an empty selection means "all". */
export function MultiSelect({ options, value, onChange, label, allLabel, render }: {
  options: string[]; value: string[]; onChange: (v: string[]) => void; label: string; allLabel: string;
  render: (o: string) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  return (
    <div className="field multi" ref={ref}>
      <span className="field-label">{label}</span>
      <button type="button" className="input select-btn" aria-haspopup="listbox" aria-expanded={open}
              onClick={() => setOpen(!open)}>
        <span className="select-value">
          {value.length === 0 ? <span className="placeholder">{allLabel}</span>
            : value.map((v) => <span className="chip" key={v}>{render(v)}</span>)}
        </span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="popover" role="listbox" aria-multiselectable="true">
          {options.map((o) => (
            <button type="button" key={o} role="option" aria-selected={value.includes(o)} onClick={() => toggle(o)}>
              <span className="box">{value.includes(o) && <Check size={12} />}</span>{render(o)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, render, ariaLabel }: {
  options: T[]; value: T; onChange: (v: T) => void; render: (o: T) => ReactNode; ariaLabel: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={ariaLabel}>
      {options.map((o) => (
        <button type="button" key={o} role="radio" aria-checked={value === o} onClick={() => onChange(o)}>{render(o)}</button>
      ))}
    </div>
  );
}

export function Disclosure({ title, children, open: initial = false, testId }: {
  title: ReactNode; children: ReactNode; open?: boolean; testId?: string;
}) {
  const [open, setOpen] = useState(initial);
  useEffect(() => setOpen(initial), [initial]);
  return (
    <div className={`disclosure${open ? " open" : ""}`} data-testid={testId}>
      <button type="button" className="disclosure-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<span>{title}</span>
      </button>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  );
}

export function Callout({ kind, children }: { kind: "warn" | "info"; children: ReactNode }) {
  return (
    <div className={`callout ${kind}`}>
      {kind === "warn" ? <TriangleAlert size={16} /> : <Info size={16} />}
      <div>{children}</div>
    </div>
  );
}

/** Collapsible JSON, open to `depth` levels (like st.json(expanded=2)). */
export function JsonTree({ value, depth = 2, name }: { value: unknown; depth?: number; name?: string }) {
  const [open, setOpen] = useState(depth > 0);
  const label = name !== undefined ? <span className="json-key">{name}: </span> : null;
  if (value === null || typeof value !== "object") {
    const cls = value === null ? "null" : typeof value;
    return <div className="json-row">{label}<span className={`json-${cls}`}>{JSON.stringify(value)}</span></div>;
  }
  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value);
  const [l, r] = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  return (
    <div className="json-row">
      <button type="button" className="json-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {label}{l}{!open && <span className="json-more"> {entries.length} … </span>}{!open && r}
      {open && (
        <div className="json-children">
          {entries.map(([k, v]) => <JsonTree key={k} name={k} value={v} depth={depth - 1} />)}
        </div>
      )}
      {open && r}
    </div>
  );
}
