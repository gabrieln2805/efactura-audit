// Landing page: what the tool does, how invoices stay private, and the way into the demo.
// Copy is web-only (not shared with the Streamlit app), so it lives here rather than in i18n.py.
import { ArrowRight, Building2, Copy, Cpu, FileDown, HardDrive, KeyRound, Lock, Monitor, Moon, Percent, ReceiptText,
         Sun, TrendingUp, Upload, Waves } from "lucide-react";
import { engine, useApp, type Theme } from "../state";
import { CHECKS, fmtLei, pick, type Lang } from "../i18n";
import { SevBadge } from "../components/ui";

const COPY = {
  ro: {
    eyebrow: "Pentru controlori financiari, contabili și antreprenori",
    title: "Verificați facturile furnizorilor din e-Factura, direct în browser.",
    lead: "Găsiți facturi duplicate, creșteri de preț, sume neobișnuite, tipare de TVA ciudate și conturi bancare schimbate. Facturile nu sunt încărcate pe niciun server.",
    demo: "Încercați demo-ul", open: "Deschideți aplicația",
    demoNote: "Demo cu date sintetice: 964 de facturi de la 22 de furnizori, 18 luni.",
    checksTitle: "Cinci verificări, rulate la fiecare import",
    checks: {
      near_duplicate: "Facturi aproape identice de la același furnizor: același total, aceleași linii, numere apropiate.",
      price_increase: "Prețuri unitare peste nivelul obișnuit al produsului sau mai mari decât la alt furnizor.",
      outlier: "Sume ieșite din tiparul furnizorului, inclusiv o virgulă pusă greșit la cantitate sau preț.",
      vat: "Cote de TVA neobișnuite pentru perioada facturii și TVA care nu se verifică aritmetic.",
      supplier: "Cont bancar schimbat, furnizori noi cu sume mari, CUI invalid.",
    } as Record<string, string>,
    howTitle: "Cum funcționează",
    steps: [
      ["Descărcați arhivele din SPV", "Arhivele ZIP de la ANAF, un export din programul de contabilitate sau fișiere XML."],
      ["Le trageți în aplicație", "Facturile sunt citite și verificate în browser, în câteva secunde."],
      ["Verificați semnalările", "Fiecare semnalare are dovezile și ce trebuie verificat; raport Excel sau PDF pentru echipă."],
    ],
    privacyTitle: "Facturile rămân la dumneavoastră",
    privacy: [
      ["Procesare în browser", "Motorul de audit rulează pe calculatorul dumneavoastră (WebAssembly). Nu există server care să primească facturile."],
      ["Stocare locală", "Datele sunt păstrate în spațiul privat al browserului și pot fi șterse oricând."],
      ["Asistent AI opțional", "Implicit un model local (Ollama). Modelele cloud doar dacă le activați, cu cheia dumneavoastră și cu IBAN-urile mascate."],
    ],
    firstVisit: "Prima pornire descarcă aproximativ 50 MB (motorul de analiză); următoarele pornesc din memoria browserului.",
    disclaimer: "Semnalările sunt indicii de verificat, nu concluzii. Instrumentul nu oferă consultanță fiscală sau contabilă.",
  },
  en: {
    eyebrow: "For finance controllers, accountants and business owners",
    title: "Check your suppliers' e-Factura invoices, right in your browser.",
    lead: "Find duplicate invoices, price increases, unusual amounts, odd VAT patterns and changed bank accounts. Your invoices are never uploaded to any server.",
    demo: "Try the demo", open: "Open the app",
    demoNote: "Demo with synthetic data: 964 invoices from 22 suppliers over 18 months.",
    checksTitle: "Five checks, run on every import",
    checks: {
      near_duplicate: "Near-identical invoices from the same supplier: same total, same lines, close numbers.",
      price_increase: "Unit prices above the item's usual level, or higher than another supplier charges.",
      outlier: "Amounts outside the supplier's pattern, including a misplaced decimal in quantity or price.",
      vat: "VAT rates unusual for the invoice's period, and VAT that doesn't add up.",
      supplier: "Changed bank account, new suppliers with large amounts, invalid CUI.",
    } as Record<string, string>,
    howTitle: "How it works",
    steps: [
      ["Download the archives from SPV", "ANAF's ZIP files, an export from your accounting software, or XML files."],
      ["Drop them into the app", "Invoices are read and checked in your browser, in seconds."],
      ["Review the flags", "Each flag comes with its evidence and what to check; Excel or PDF report for the team."],
    ],
    privacyTitle: "Your invoices stay with you",
    privacy: [
      ["Processed in the browser", "The audit engine runs on your computer (WebAssembly). There is no server that receives invoices."],
      ["Stored locally", "Data is kept in the browser's private storage and can be deleted at any time."],
      ["Optional AI assistant", "A local model (Ollama) by default. Cloud models only if you enable them, with your own key and IBANs masked."],
    ],
    firstVisit: "The first start downloads about 50 MB (the analysis engine); later visits start from the browser's cache.",
    disclaimer: "Flags are prompts to check, not conclusions. The tool gives no tax or accounting advice.",
  },
};

// an illustration of the flag list (values from the demo data)
const MOCK: [string, string, number | string][] = [
  ["high", "near_duplicate", 32842.51], ["high", "price_increase", 1870.2], ["medium", "supplier", "RO47…4F5U"], ["low", "vat", 236],
];
const CHECK_ICONS = { near_duplicate: Copy, price_increase: TrendingUp, outlier: Waves, vat: Percent, supplier: Building2 };
const STEP_ICONS = [Upload, Cpu, FileDown];
const PRIVACY_ICONS = [Lock, HardDrive, KeyRound];
const THEMES: Theme[] = ["system", "light", "dark"];
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

export function Landing() {
  const { lang, setLang, theme, setTheme, L } = useApp();
  const c = COPY[lang];
  const ThemeIcon = THEME_ICON[theme];
  const warm = () => engine.start();   // begin the 50 MB download while the visitor decides
  return (
    <div className="landing">
      <header className="landing-bar">
        <a className="brand" href="#/"><span className="brand-mark"><ReceiptText size={17} /></span>
          <span className="brand-name">auditefactura<span>.ro</span></span></a>
        <div className="landing-actions">
          <div className="seg" role="group" aria-label={L("language")}>
            {(["ro", "en"] as Lang[]).map((l) => (
              <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>
            ))}
          </div>
          <button className="icon-btn" onClick={() => setTheme(THEMES[(THEMES.indexOf(theme) + 1) % 3])}
                  aria-label={`${L("theme")}: ${L(`theme_${theme}`)}`}><ThemeIcon size={15} /></button>
          <a className="btn" href="#/overview" onMouseEnter={warm} onFocus={warm}>{c.open}</a>
        </div>
      </header>

      <section className="hero">
        <div className="hero-text">
          <div className="eyebrow-pill">{c.eyebrow}</div>
          <h1>{c.title}</h1>
          <p className="lead">{c.lead}</p>
          <div className="row">
            <a className="btn primary lg" href="#/overview?demo" onMouseEnter={warm} onFocus={warm} onTouchStart={warm}
               data-testid="try-demo">{c.demo}<ArrowRight size={16} /></a>
            <a className="btn lg" href="#/overview" onMouseEnter={warm} onFocus={warm}>{c.open}</a>
          </div>
          <div className="hint">{c.demoNote}</div>
        </div>
        <div className="hero-card card" aria-hidden="true">
          {MOCK.map(([sev, check, value]) => (
            <div className="mock-row" key={check}>
              <SevBadge sev={sev} lang={lang} /><span>{pick(CHECKS, check, lang)}</span>
              <b className="num">{typeof value === "number" ? fmtLei(value, lang) : value}</b>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2>{c.checksTitle}</h2>
        <div className="feature-grid">
          {Object.entries(CHECK_ICONS).map(([k, Icon]) => (
            <div className="card feature" key={k}>
              <Icon size={20} className="feature-icon" />
              <h3>{pick(CHECKS, k, lang)}</h3>
              <p>{c.checks[k]}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2>{c.howTitle}</h2>
        <ol className="steps">
          {c.steps.map(([t, d], i) => {
            const Icon = STEP_ICONS[i];
            return <li key={t} className="card feature"><span className="step-n">{i + 1}</span><Icon size={20} className="feature-icon" /><h3>{t}</h3><p>{d}</p></li>;
          })}
        </ol>
      </section>

      <section className="landing-section privacy-band">
        <h2>{c.privacyTitle}</h2>
        <div className="feature-grid three">
          {c.privacy.map(([t, d], i) => {
            const Icon = PRIVACY_ICONS[i];
            return <div key={t} className="feature plain"><Icon size={20} className="feature-icon" /><h3>{t}</h3><p>{d}</p></div>;
          })}
        </div>
        <div className="hint">{c.firstVisit}</div>
      </section>

      <footer className="landing-foot">
        <span>{c.disclaimer}</span>
      </footer>
    </div>
  );
}
