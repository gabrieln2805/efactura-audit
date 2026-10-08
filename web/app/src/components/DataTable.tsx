// Sortable table with optional single-row selection.
import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { fmtNum, type Lang } from "../i18n";

export type Kind = "text" | "num" | "money" | "int" | "date" | "bool";

export type Col<T> = {
  key: string;
  label: string;
  kind?: Kind;
  /** custom cell; the raw value is still used for sorting */
  render?: (row: T) => ReactNode;
  value?: (row: T) => unknown;
  width?: number | string;
  grow?: boolean;
};

type Props<T> = {
  rows: T[];
  cols: Col<T>[];
  lang: Lang;
  rowKey?: (row: T, i: number) => string;
  selected?: string | null;
  onSelect?: (key: string | null, row: T | null) => void;
  maxHeight?: number;
  testId?: string;
  yesNo?: [string, string];
  /** keep every cell on one line (result grids) */
  nowrap?: boolean;
};

export function formatCell(v: unknown, kind: Kind | undefined, lang: Lang, yesNo: [string, string] = ["✓", ""]): ReactNode {
  if (v === null || v === undefined || v === "") return kind === "text" || !kind ? "" : "–";
  switch (kind) {
    case "money": return fmtNum(Number(v), lang, 2);
    case "num": return typeof v === "number" ? fmtNum(v, lang, Number.isInteger(v) ? 0 : 2) : String(v);
    case "int": return fmtNum(Number(v), lang, 0);
    case "date": return String(v).slice(0, 10);
    case "bool": return v ? yesNo[0] : yesNo[1];
    default: return typeof v === "object" ? JSON.stringify(v) : String(v);
  }
}

const collator = new Intl.Collator("ro", { numeric: true, sensitivity: "base" });

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined || a === "") return 1;   // empty values last in both directions
  if (b === null || b === undefined || b === "") return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return collator.compare(String(a), String(b));
}

export function DataTable<T>({ rows, cols, lang, rowKey, selected, onSelect, maxHeight = 420, testId, yesNo, nowrap }: Props<T>) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(null);
  const valueOf = (c: Col<T>, r: T) => (c.value ? c.value(r) : (r as Record<string, unknown>)[c.key]);
  const keyed = useMemo(() => rows.map((r, i) => ({ r, k: rowKey ? rowKey(r, i) : String(i) })), [rows, rowKey]);
  const sorted = useMemo(() => {
    const c = sort && cols.find((x) => x.key === sort.key);
    if (!c) return keyed;
    const out = [...keyed].sort((a, b) => {
      const va = valueOf(c, a.r), vb = valueOf(c, b.r);
      const empty = (v: unknown) => v === null || v === undefined || v === "";
      if (empty(va) || empty(vb)) return compare(va, vb);
      return sort!.desc ? compare(vb, va) : compare(va, vb);
    });
    return out;
  }, [keyed, sort, cols]);
  const cycle = (key: string) => setSort((s) => (!s || s.key !== key ? { key, desc: false } : !s.desc ? { key, desc: true } : null));
  const numeric = (k?: Kind) => k === "num" || k === "money" || k === "int";
  return (
    <div className="table-wrap" style={{ maxHeight }} data-testid={testId}>
      <table className={`table${onSelect ? " selectable" : ""}${nowrap ? " nowrap" : ""}`}>
        <thead>
          <tr>
            {cols.map((c) => {
              const dir = sort?.key === c.key ? (sort.desc ? "desc" : "asc") : null;
              return (
                <th key={c.key} className={numeric(c.kind) ? "r" : ""} style={{ width: c.width }}
                    aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined}>
                  <button type="button" onClick={() => cycle(c.key)}>
                    {c.label}
                    {dir === "asc" ? <ArrowUp size={12} /> : dir === "desc" ? <ArrowDown size={12} /> : null}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ r, k }) => {
            const isSel = selected != null && k === selected;
            const select = () => onSelect?.(isSel ? null : k, isSel ? null : r);
            return (
              <tr key={k} aria-selected={onSelect ? isSel : undefined} tabIndex={onSelect ? 0 : undefined}
                  onClick={onSelect ? select : undefined}
                  onKeyDown={onSelect ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } } : undefined}>
                {cols.map((c) => (
                  <td key={c.key} className={`${numeric(c.kind) ? "r num" : ""}${c.grow ? " grow" : ""}${c.kind === "date" ? " nowrap" : ""}`}>
                    {c.render ? c.render(r) : formatCell(valueOf(c, r), c.kind, lang, yesNo)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Table for {columns, rows} results from the engine (SQL box, previews, invoice lines). */
export function ResultTable({ data, lang, labels = {}, maxHeight, testId }:
  { data: { columns: string[]; types?: string[]; rows: unknown[][] }; lang: Lang; labels?: Record<string, string>;
    maxHeight?: number; testId?: string }) {
  const kindOf = (t?: string): Kind => {
    if (!t) return "text";
    if (/int/i.test(t)) return "int";
    if (/float|double|decimal/i.test(t)) return "num";
    if (/bool/i.test(t)) return "bool";
    if (/date/i.test(t)) return "text";
    return "text";
  };
  const cols = useMemo<Col<unknown[]>[]>(() => data.columns.map((c, i) => ({
    key: `${i}`, label: labels[c] ?? c, kind: kindOf(data.types?.[i]), value: (r) => r[i],
  })), [data, labels]);
  return <DataTable rows={data.rows} cols={cols} lang={lang} maxHeight={maxHeight} testId={testId} nowrap />;
}
