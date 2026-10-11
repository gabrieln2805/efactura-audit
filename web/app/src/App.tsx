import { useEffect, useState, type ComponentType } from "react";
import {
  Building2, Database, FileDown, FileText, Flag, LayoutDashboard, Lock, Menu, Monitor, Moon, Play, ReceiptText,
  Settings, Sparkles, Sun, Upload,
} from "lucide-react";
import { engine, useApp, type Theme } from "./state";
import { BRAND } from "./brand";
import { EngineSplash, EngineChip, Spinner, Toasts } from "./components/chrome";
import { Overview } from "./screens/Overview";
import { Flags } from "./screens/Flags";
import { Invoices } from "./screens/Invoices";
import { Suppliers } from "./screens/Suppliers";
import { Data } from "./screens/Data";
import { Import } from "./screens/Import";
import { Report } from "./screens/Report";
import { Assistant } from "./screens/Assistant";
import { Settings as SettingsScreen } from "./screens/Settings";
import { Landing, SiteLinks } from "./screens/Landing";
import { LegalPage, PAGES, type Page } from "./screens/Legal";

type Screen = { id: string; label: string; icon: ComponentType<{ size?: number }>; view: ComponentType; sep?: boolean };

const SCREENS: Screen[] = [
  { id: "overview", label: "tab_overview", icon: LayoutDashboard, view: Overview },
  { id: "flags", label: "tab_flags", icon: Flag, view: Flags },
  { id: "invoices", label: "tab_invoices", icon: FileText, view: Invoices },
  { id: "suppliers", label: "tab_suppliers", icon: Building2, view: Suppliers },
  { id: "data", label: "tab_data", icon: Database, view: Data, sep: true },
  { id: "import", label: "tab_import", icon: Upload, view: Import },
  { id: "report", label: "tab_report", icon: FileDown, view: Report, sep: true },
  { id: "assistant", label: "tab_assistant", icon: Sparkles, view: Assistant },
  { id: "settings", label: "tab_settings", icon: Settings, view: SettingsScreen, sep: true },
];

/** "home" (the landing page, no hash), an info page (about, privacy, terms) or an app screen id. */
function useRoute(): string {
  const read = () => location.hash.replace(/^#\/?/, "").split("?")[0] || "home";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route === "home" || (PAGES as readonly string[]).includes(route) || SCREENS.some((s) => s.id === route) ? route : "overview";
}

const THEMES: Theme[] = ["system", "light", "dark"];
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

function Rail({ route, onNavigate }: { route: string; onNavigate: () => void }) {
  const { L, lang, setLang, theme, setTheme, status, engine } = useApp();
  const ThemeIcon = THEME_ICON[theme];
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  return (
    <aside className="rail">
      <a className="brand" href="#/" onClick={onNavigate}>
        <span className="brand-mark"><ReceiptText size={17} /></span>
        <span className="brand-name">{BRAND}</span>
      </a>
      <nav className="nav" aria-label={L("menu")}>
        {SCREENS.map(({ id, label, icon: Icon, sep }) => (
          <div key={id} style={{ display: "contents" }}>
            {sep && <div className="nav-sep" />}
            <a href={`#/${id}`} aria-current={route === id ? "page" : undefined} onClick={onNavigate}>
              <Icon size={17} />
              {L(label)}
              {id === "flags" && status && status.open_flags > 0 && <span className="badge">{status.open_flags}</span>}
              {id === "assistant" && <span className="badge soon">{L("soon")}</span>}
            </a>
          </div>
        ))}
      </nav>
      <div className="rail-foot">
        <div className="privacy"><Lock size={13} /><span>{L("local_only_web")}</span></div>
        <div className="rail-controls">
          <div className="seg" role="group" aria-label={L("language")}>
            {(["ro", "en"] as const).map((l) => (
              <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>
            ))}
          </div>
          <button className="icon-btn" onClick={() => setTheme(next)}
                  title={`${L("theme")}: ${L(`theme_${theme}`)}`} aria-label={`${L("theme")}: ${L(`theme_${theme}`)}`}>
            <ThemeIcon size={15} />
          </button>
        </div>
        <EngineChip state={engine} version={status?.version} />
      </div>
    </aside>
  );
}

function TopBar({ screen }: { screen: Screen }) {
  const { L, status, engine, busy, mutate, toast } = useApp();
  const ready = engine.phase === "ready";
  const hasData = !!status && status.invoices > 0;
  const runAudit = async () => {
    const res = await mutate<{ flags: number; seconds: number }>("run_audit");
    if (res) toast(L("audit_done", { n: res.flags, s: res.seconds }));
  };
  return (
    <header className="topbar">
      <div>
        <h1>{L(screen.label)}</h1>
        {screen.id === "overview" && <div className="subtitle">{L("app_title")}</div>}
      </div>
      <div className="top-actions">
        {status?.last_audit && (
          <div className="last-run">{L("last_audit")}<br /><span className="num">{status.last_audit.replace("T", " ")}</span></div>
        )}
        <button className="btn primary" onClick={runAudit} disabled={!ready || !hasData || !!busy}>
          {busy === "run_audit" ? <Spinner /> : <Play size={15} />}
          {L("run_audit")}
        </button>
      </div>
    </header>
  );
}

/** "#/overview?demo" (the landing page's demo button): load the demo once the engine is ready, if there is no data. */
function useDemoLink() {
  const { engine: es, status, mutate, toast, L } = useApp();
  useEffect(() => {
    if (!location.hash.includes("?demo") || es.phase !== "ready" || !status) return;
    history.replaceState(null, "", location.hash.replace("?demo", ""));
    if (status.invoices === 0) mutate("load_demo").then((r) => r && toast(L("demo_loaded")));
  }, [es.phase, status, mutate, toast, L]);
}

function Shell({ route }: { route: string }) {
  const { engine: es, L } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const screen = SCREENS.find((s) => s.id === route)!;
  const View = screen.view;
  useDemoLink();
  useEffect(() => {
    document.title = `${L(screen.label)} · ${BRAND}`;
  }, [screen, L]);
  return (
    <div className={`shell${menuOpen ? " menu-open" : ""}`}>
      <Rail route={route} onNavigate={() => setMenuOpen(false)} />
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
      <main className="main">
        <div className="mobile-bar">
          <button className="icon-btn" onClick={() => setMenuOpen(true)} aria-label={L("menu")}><Menu size={18} /></button>
          <span className="brand-name">{BRAND}</span>
        </div>
        <TopBar screen={screen} />
        <div className="content">
          {es.phase === "ready" && !es.persistent && <div className="callout warn" role="status">{L("not_persistent")}</div>}
          {es.phase === "ready" ? <View /> : <EngineSplash />}
        </div>
        <footer className="app-foot"><span>{L("disclaimer")}</span><SiteLinks /></footer>
      </main>
      <Toasts />
    </div>
  );
}

export default function App() {
  const { L } = useApp();
  const route = useRoute();
  const info = (PAGES as readonly string[]).includes(route);
  const inApp = route !== "home" && !info;
  useEffect(() => {
    if (inApp) engine.start();
    window.scrollTo(0, 0);
  }, [inApp]);
  useEffect(() => {
    if (!inApp) document.title = `${BRAND} · ${L("app_title")}`;
  }, [inApp, L]);
  if (info) return <LegalPage page={route as Page} />;
  return inApp ? <Shell route={route} /> : <><Landing /><Toasts /></>;
}
