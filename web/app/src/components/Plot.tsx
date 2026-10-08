// Plotly chart with the app's look (the same layout rules as the Streamlit app's theme.py), loaded on first use.
import { useEffect, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import { useApp } from "../state";

export const BLUE = "#2a78d6";
export const SEV_COLORS: Record<string, string> = { high: "#d03b3b", medium: "#ec835a", low: "#fab219" };
export const MUTED = "#898781";
// sequential: one blue whose opacity grows with the value, so near-zero recedes into either theme's surface
export const SEQUENTIAL: [number, string][] = [[0, "rgba(42,120,214,0.10)"], [1, "rgba(42,120,214,1.0)"]];

type PlotlyModule = typeof import("plotly.js");
let plotly: Promise<PlotlyModule> | null = null;
const loadPlotly = () => (plotly ??= import("plotly.js-cartesian-dist-min").then((m) => (m.default ?? m) as PlotlyModule));

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Page surface color, for the ring around overlapping markers. */
export function surface(): string {
  return cssVar("--surface") || "#ffffff";
}

export function useDark(): boolean {
  const { theme } = useApp();
  const [systemDark, setSystemDark] = useState(() => matchMedia("(prefers-color-scheme: dark)").matches);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSystemDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return theme === "dark" || (theme === "system" && systemDark);
}

type Props = { data: Data[]; layout?: Partial<Layout>; height?: number; testId?: string };

export function Plot({ data, layout = {}, height = 280, testId }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { lang } = useApp();
  const dark = useDark();
  useEffect(() => {
    let live = true;
    const el = ref.current;
    loadPlotly().then((P) => {
      if (!live || !el) return;
      const text = cssVar("--text-2");
      const base: Partial<Layout> = {
        height, margin: { l: 8, r: 8, t: 8, b: 8 }, plot_bgcolor: "rgba(0,0,0,0)", paper_bgcolor: "rgba(0,0,0,0)",
        showlegend: false, font: { size: 12, color: text, family: "Inter Variable, Segoe UI, sans-serif" },
        hoverlabel: { font: { size: 12 } }, bargap: 0.45, separators: lang === "ro" ? ",." : ".,",
        ...layout,
        xaxis: { showgrid: false, zeroline: false, automargin: true, ...layout.xaxis },
        yaxis: { gridcolor: "rgba(128,128,128,0.15)", zeroline: false, automargin: true, ...layout.yaxis },
      };
      P.react(el, data, base, { displayModeBar: false, responsive: true });
    });
    return () => { live = false; };
  }, [data, layout, height, lang, dark]);
  useEffect(() => {
    const el = ref.current;
    return () => { if (el) loadPlotly().then((P) => P.purge(el)); };
  }, []);
  return <div ref={ref} className="plot" style={{ minHeight: height }} data-testid={testId} />;
}
