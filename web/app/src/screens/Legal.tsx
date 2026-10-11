// About, Privacy and Terms for the free test phase: a non-commercial project run by a private person.
// Copy is web-only, so it lives here rather than in i18n.py. Keep it literally true: if the site starts sending
// or keeping anything new (analytics, accounts, the AI assistant), these pages change first.
import type { ReactNode } from "react";
import { useApp } from "../state";
import { BRAND, CONTACT_EMAIL, OPERATOR } from "../brand";
import type { Lang } from "../i18n";
import { SiteBar, SiteFooter } from "./Landing";

export const PAGES = ["about", "privacy", "terms"] as const;
export type Page = (typeof PAGES)[number];

type Section = { h: string; p: ReactNode[] };
type Doc = { title: string; updated: string; intro: ReactNode; sections: Section[] };

const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
// the controller is the private person who runs the project; their name is added before publishing (brand.ts)
const named = () => (OPERATOR ? `, ${OPERATOR}` : "");
const UPDATED = "11.10.2026";

function docs(lang: Lang): Record<Page, Doc> {
  const ro = lang === "ro";
  return {
    about: ro ? {
      title: `Despre ${BRAND}`, updated: UPDATED,
      intro: <>{BRAND} verifică facturile primite de la furnizori prin e-Factura și semnalează ce merită verificat: posibile duplicate, creșteri de preț, sume neobișnuite, tipare de TVA și schimbări la furnizori.</>,
      sections: [
        { h: "Un proiect de test, gratuit", p: [
          <>{BRAND} este în faza de test. Este gratuit și necomercial: nu există plăți, abonamente sau reclame.</>,
          <>Scopul acestei faze este să aflăm dacă instrumentul este util contabililor și firmelor. Părerea dumneavoastră decide ce urmează.</>] },
        { h: "Facturile rămân la dumneavoastră", p: [
          <>Facturile sunt citite și verificate în browserul dumneavoastră și păstrate doar acolo. Nu sunt trimise către noi sau către alt server.</>] },
        { h: "Cine administrează proiectul", p: [
          <>{BRAND} este un proiect personal, necomercial, administrat de o persoană fizică{named()}. Contact: {mail}.</>] },
        { h: "Feedback", p: [
          <>Ne ajută orice observație: ce a funcționat, ce nu, ce lipsește, dacă ați folosi instrumentul pentru clienții sau firma dumneavoastră. Scrieți-ne la {mail}.</>] },
      ],
    } : {
      title: `About ${BRAND}`, updated: UPDATED,
      intro: <>{BRAND} checks the invoices a company receives from suppliers through e-Factura and flags what is worth checking: possible duplicates, price increases, unusual amounts, VAT patterns and supplier changes.</>,
      sections: [
        { h: "A free test project", p: [
          <>{BRAND} is in its test phase. It is free and non-commercial: no payments, subscriptions or ads.</>,
          <>The point of this phase is to learn whether the tool is useful to accountants and companies. Your feedback decides what comes next.</>] },
        { h: "Your invoices stay with you", p: [
          <>Invoices are read and checked in your browser and kept only there. They are not sent to us or to any other server.</>] },
        { h: "Who runs it", p: [<>{BRAND} is a personal, non-commercial project run by a private person{named()}. Contact: {mail}.</>] },
        { h: "Feedback", p: [
          <>Every remark helps: what worked, what didn't, what is missing, and whether you would use it for your clients or your company. Write to {mail}.</>] },
      ],
    },
    privacy: ro ? {
      title: "Confidențialitate", updated: UPDATED,
      intro: <>Pe scurt: facturile dumneavoastră nu ajung la noi. Colectăm doar foarte puține date, descrise mai jos.</>,
      sections: [
        { h: "Cine răspunde de date", p: [<>Operatorul datelor este persoana fizică ce administrează proiectul {BRAND}{named()}. Contact: {mail}.</>] },
        { h: "Facturile și rezultatele", p: [
          <>Facturile pe care le importați, rezultatele verificărilor și revizuirile dumneavoastră sunt prelucrate și păstrate doar în browserul dumneavoastră (spațiul privat de stocare al site-ului). Nu le primim, nu le vedem și nu le putem recupera.</>,
          <>Le puteți șterge oricând: Import → „Începeți de la zero”, sau ștergând datele site-ului din setările browserului.</>] },
        { h: "Ce colectăm", p: [
          <><b>Jurnalele serverului.</b> Furnizorul de găzduire înregistrează, ca orice site, adresa IP, data și ora, pagina cerută și tipul de browser, pentru funcționarea și securitatea site-ului. Le păstrează conform propriilor reguli.</>,
          <><b>Mesajele pe care ni le trimiteți</b> (feedback, întrebări): adresa de e-mail și conținutul mesajului, folosite doar pentru a vă răspunde și pentru a îmbunătăți proiectul. Le ștergem la cerere.</>,
          <>Dacă vom adăuga o listă de înscriere, vom actualiza această pagină înainte.</>] },
        { h: "Ce nu folosim", p: [
          <>Nu folosim cookie-uri, instrumente de analiză a traficului, reclame sau profilare.</>,
          <>Site-ul păstrează în browser doar ce este necesar pentru a funcționa: baza de date cu facturile importate și preferințele de limbă și temă.</>] },
        { h: "Alți furnizori", p: [
          <>Motorul de analiză (Pyodide) se descarcă la prima vizită de la serviciul jsDelivr, care vede astfel adresa IP a browserului. Urmează să îl servim de pe domeniul propriu.</>,
          <>Asistentul AI nu este activ. Dacă va fi activat, această pagină va spune exact ce i se trimite și cui.</>] },
        { h: "Drepturile dumneavoastră", p: [
          <>Aveți dreptul de acces, rectificare, ștergere, restricționare și opoziție privind datele pe care le deținem (în practică, mesajele trimise nouă). Scrieți la {mail}. Puteți depune și o plângere la Autoritatea Națională de Supraveghere a Prelucrării Datelor cu Caracter Personal (ANSPDCP, dataprotection.ro).</>] },
      ],
    } : {
      title: "Privacy", updated: UPDATED,
      intro: <>In short: your invoices never reach us. We collect very little, as described below.</>,
      sections: [
        { h: "Who is responsible", p: [<>The data controller is the private person who runs the {BRAND} project{named()}. Contact: {mail}.</>] },
        { h: "Invoices and results", p: [
          <>The invoices you import, the check results and your reviews are processed and kept only in your browser (the site's private storage). We do not receive them, cannot see them and cannot recover them.</>,
          <>You can delete them at any time: Import → "Start fresh", or by clearing the site's data in your browser settings.</>] },
        { h: "What we collect", p: [
          <><b>Server logs.</b> Like any website, the hosting provider records the IP address, date and time, page requested and browser type, to run and secure the site. It keeps them under its own rules.</>,
          <><b>Messages you send us</b> (feedback, questions): your e-mail address and the message, used only to reply and to improve the project. Deleted on request.</>,
          <>If we add a sign-up list, this page changes first.</>] },
        { h: "What we don't use", p: [
          <>No cookies, no traffic analytics, no ads, no profiling.</>,
          <>The site keeps in your browser only what it needs to work: the database of imported invoices and your language and theme preferences.</>] },
        { h: "Other providers", p: [
          <>The analysis engine (Pyodide) is downloaded on the first visit from the jsDelivr service, which therefore sees your browser's IP address. We will serve it from our own domain.</>,
          <>The AI assistant is not active. If it is turned on, this page will say exactly what is sent to it and to whom.</>] },
        { h: "Your rights", p: [
          <>You have the right of access, rectification, erasure, restriction and objection regarding the data we hold (in practice, the messages you send us). Write to {mail}. You can also complain to the Romanian data protection authority (ANSPDCP, dataprotection.ro).</>] },
      ],
    },
    terms: ro ? {
      title: "Termeni de utilizare", updated: UPDATED,
      intro: <>Folosind {BRAND} acceptați acești termeni.</>,
      sections: [
        { h: "Versiune de test, gratuită", p: [
          <>{BRAND} este o versiune de test, gratuită și necomercială, oferită „ca atare”, fără garanții privind funcționarea, disponibilitatea sau exactitatea rezultatelor. Poate fi modificată sau oprită oricând.</>] },
        { h: "Ce sunt semnalările", p: [
          <>Semnalările sunt indicii de verificat, nu concluzii. Pot exista semnalări greșite și probleme nesemnalate. Verificați fiecare semnalare cu documentele (contracte, avize, comenzi) și cu furnizorul înainte de a acționa.</>] },
        { h: "Ce nu este", p: [
          <>{BRAND} nu oferă consultanță fiscală, contabilă sau juridică și nu este un audit financiar. Nu are nicio legătură cu ANAF; „e-Factura” descrie doar sistemul prin care primiți facturile.</>] },
        { h: "Responsabilitatea dumneavoastră", p: [
          <>Importați doar facturi pe care aveți dreptul să le prelucrați (ale firmei dumneavoastră sau ale clienților care v-au mandatat).</>,
          <>Datele stau doar în browserul dumneavoastră: păstrați copiile originale ale facturilor. Ștergerea datelor site-ului din browser șterge și datele importate.</>,
          <>Deciziile luate pe baza rezultatelor vă aparțin.</>] },
        { h: "Răspundere", p: [
          <>În limitele permise de lege, administratorul proiectului nu răspunde pentru pierderi rezultate din folosirea sau imposibilitatea folosirii instrumentului. Limitarea nu se aplică răspunderii pentru intenție sau culpă gravă.</>] },
        { h: "Altele", p: [
          <>Se aplică legea română. Întrebări: {mail}.</>] },
      ],
    } : {
      title: "Terms of use", updated: UPDATED,
      intro: <>By using {BRAND} you accept these terms.</>,
      sections: [
        { h: "Free test version", p: [
          <>{BRAND} is a free, non-commercial test version, provided "as is", without warranties as to operation, availability or the accuracy of results. It may change or stop at any time.</>] },
        { h: "What flags are", p: [
          <>Flags are prompts to check, not conclusions. Some flags may be wrong and some problems may go unflagged. Check each flag against the documents (contracts, delivery notes, orders) and with the supplier before acting.</>] },
        { h: "What it is not", p: [
          <>{BRAND} gives no tax, accounting or legal advice and is not a financial audit. It has no connection with ANAF; "e-Factura" only describes the system through which you receive invoices.</>] },
        { h: "Your responsibility", p: [
          <>Import only invoices you are entitled to process (your company's, or those of clients who have mandated you).</>,
          <>The data lives only in your browser: keep the original invoice files. Clearing the site's data in your browser also deletes the imported data.</>,
          <>Decisions taken on the basis of the results are yours.</>] },
        { h: "Liability", p: [
          <>To the extent permitted by law, the person running the project is not liable for losses resulting from the use of, or inability to use, the tool. This limitation does not apply to liability for intent or gross negligence.</>] },
        { h: "Other", p: [<>Romanian law applies. Questions: {mail}.</>] },
      ],
    },
  };
}

export function LegalPage({ page }: { page: Page }) {
  const { lang } = useApp();
  const d = docs(lang)[page];
  return (
    <div className="landing">
      <SiteBar />
      <article className="legal" data-testid={`page-${page}`}>
        <h1>{d.title}</h1>
        <div className="hint">{lang === "ro" ? "Actualizat" : "Updated"}: {d.updated}</div>
        <p className="lead">{d.intro}</p>
        {d.sections.map((s) => (
          <section key={s.h}>
            <h2>{s.h}</h2>
            {s.p.map((x, i) => <p key={i}>{x}</p>)}
          </section>
        ))}
      </article>
      <SiteFooter />
    </div>
  );
}
