// UI strings come from efactura_audit/app/i18n.py (exported to strings.json by scripts/prepare.py),
// so the web app and the Streamlit app share one Romanian/English source.
import raw from "./strings.json";

export type Lang = "ro" | "en";
type Pair = [string, string];
const data = raw as unknown as {
  S: Record<string, Pair>; CHECKS: Record<string, Pair>; SEVERITY: Record<string, Pair>; STATUS: Record<string, Pair>;
  EXAMPLES: Record<Lang, string[]>;
};
const S = data.S;
export const CHECKS = data.CHECKS;
export const SEVERITY = data.SEVERITY;
export const STATUS = data.STATUS;
export const EXAMPLES = data.EXAMPLES;
export const CHECK_KEYS = Object.keys(CHECKS);

/** Python str.format subset: {name} and {name:.Nf}, with Romanian decimal commas. */
export function tr(key: string, lang: Lang, params: Record<string, string | number> = {}): string {
  const [ro, en] = S[key] ?? [key, key];
  return (lang === "ro" ? ro : en).replace(/\{(\w+)(?::\.(\d+)f)?\}/g, (_, name: string, digits?: string) => {
    const v = params[name];
    if (v === undefined) return `{${name}}`;
    if (digits !== undefined && typeof v === "number") return fmtNum(v, lang, Number(digits));
    return String(v);
  });
}

export function pick(mapping: Record<string, Pair>, key: string, lang: Lang): string {
  const [ro, en] = mapping[key] ?? [key, key];
  return lang === "ro" ? ro : en;
}

const locale = (lang: Lang) => (lang === "ro" ? "ro-RO" : "en-GB");

export function fmtNum(x: number | null | undefined, lang: Lang, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  // ro-RO drops the thousands separator under 10.000; the Streamlit app always shows it
  return new Intl.NumberFormat(locale(lang), { minimumFractionDigits: digits, maximumFractionDigits: digits,
                                               useGrouping: "always" } as Intl.NumberFormatOptions).format(x);
}

export function fmtLei(x: number | null | undefined, lang: Lang): string {
  return x === null || x === undefined ? "–" : `${fmtNum(x, lang, 2)} lei`;
}

/** Short amounts for KPI tiles: 9,97 mil. lei / 713.041 lei. */
export function fmtCompact(x: number | null | undefined, lang: Lang): string {
  if (x === null || x === undefined) return "–";
  if (Math.abs(x) >= 1_000_000) {
    const v = fmtNum(x / 1_000_000, lang, 2);
    return lang === "ro" ? `${v} mil. lei` : `${v}M lei`;
  }
  return `${fmtNum(x, lang, 0)} lei`;
}
