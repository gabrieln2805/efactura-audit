// App-wide state: the engine, language, theme, the data version (bumped after every write so screens
// re-query), and toasts.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Engine, type EngineState } from "./engine/client";
import { tr, type Lang } from "./i18n";

export type Theme = "system" | "light" | "dark";
export type Toast = { id: number; text: string; kind: "ok" | "error" };
export type Status = { version: string; invoices: number; open_flags: number; last_audit: string | null; buyer_cui: string };

export const engine = new Engine();   // starts loading as soon as the page opens
if (import.meta.env.DEV) (window as any).__engine = engine;   // used by the Playwright tests

function stored<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice lasts for this visit */
  }
}

type Ctx = {
  engine: EngineState;
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  L: (key: string, params?: Record<string, string | number>) => string;
  version: number;
  status: Status | null;
  busy: string | null;
  /** Run an engine call that changes data: shows the busy state, bumps the data version, reports errors. */
  mutate: <T>(method: string, args?: Record<string, unknown>, files?: File[], onLog?: (text: string) => void) => Promise<T | undefined>;
  toast: (text: string, kind?: Toast["kind"]) => void;
  toasts: Toast[];
};

const AppContext = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [engineState, setEngineState] = useState<EngineState>(engine.state);
  const [lang, setLangState] = useState<Lang>(() => stored<Lang>("lang", "ro", ["ro", "en"]));
  const [theme, setThemeState] = useState<Theme>(() => stored<Theme>("theme", "system", ["system", "light", "dark"]));
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => engine.subscribe(setEngineState), []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [theme]);

  const ready = engineState.phase === "ready";
  useEffect(() => {
    if (ready) engine.call<Status>("status").then(setStatus).catch(() => setStatus(null));
  }, [ready, version]);

  const L = useCallback((key: string, params?: Record<string, string | number>) => tr(key, lang, params), [lang]);
  const toast = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { id, text, kind }]);
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), kind === "error" ? 9000 : 4500);
  }, []);

  const mutate = useCallback(async <T,>(method: string, args: Record<string, unknown> = {}, files?: File[],
                                      onLog?: (text: string) => void) => {
    setBusy(method);
    try {
      const result = await engine.call<T>(method, args, files, onLog);
      setVersion((v) => v + 1);
      // keep the database when the browser is short of space (needs the page, not the worker)
      navigator.storage?.persist?.().catch(() => {});
      return result;
    } catch (e) {
      toast(`${tr("error", lang)}: ${(e as Error).message}`, "error");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, [lang, toast]);

  const value = useMemo<Ctx>(() => ({
    engine: engineState, lang, theme, L, version, status, busy, mutate, toast, toasts,
    setLang: (l) => { setLangState(l); store("lang", l); },
    setTheme: (t) => { setThemeState(t); store("theme", t); },
  }), [engineState, lang, theme, L, version, status, busy, mutate, toast, toasts]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

/** Query the engine; re-runs when the arguments, the language or the data version change. */
export function useCall<T>(method: string, args: Record<string, unknown> = {}, enabled = true) {
  const { engine: es, version } = useApp();
  const key = JSON.stringify(args);
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: enabled });
  const [nonce, setNonce] = useState(0);
  const ready = es.phase === "ready";
  useEffect(() => {
    if (!enabled || !ready) return;
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    engine.call<T>(method, JSON.parse(key))
      .then((data) => live && setState({ data, loading: false }))
      .catch((e) => live && setState({ error: (e as Error).message, loading: false }));
    return () => { live = false; };
  }, [method, key, version, ready, enabled, nonce]);
  return { ...state, reload: () => setNonce((n) => n + 1) };
}

/** A per-browser preference (localStorage), e.g. the Settings toggles. */
export function usePref(key: string, fallback: boolean): [boolean, (v: boolean) => void] {
  const [v, setV] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : raw === "1";
    } catch {
      return fallback;
    }
  });
  return [v, (next) => { setV(next); store(key, next ? "1" : "0"); }];
}
