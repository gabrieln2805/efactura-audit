# 10-minute demo on the test pack

**Before the call:** load the demo data into its own workspace so nothing real is on screen.

```powershell
.venv\Scripts\efactura-audit -w $env:USERPROFILE\efactura-demo demo
scripts\start_app.bat -w $env:USERPROFILE\efactura-demo
```

Keep the app in Romanian. Say once, up front: *"Datele sunt fictive — firme, persoane și conturi inventate."*

| Min | Where | Show | Say (in essence) |
|---|---|---|---|
| 0–1 | Prezentare | KPI row, flags by check | "964 de facturi de la 22 de furnizori, 18 luni. Auditul a durat câteva secunde și a găsit 37 de lucruri de verificat." |
| 1–3 | Semnalări → filter *Posibil duplicat* | **EST/7831 vs EST-7831** (Eurosteel, same number with different punctuation, 9 days later, 32,842 lei) and **BTX-21551 vs BTX-2155** (same day, one digit added) | "ANAF respinge duplicatele exacte, dar nu și pe cele cu număr schimbat. Aici ar fi fost plătiți de două ori ~33.000 de lei." Open the invoices involved to show identical lines. |
| 3–4 | same table, last row | **TLT-6950** (low severity) | "Aceasta seamănă tot a duplicat, dar există o notă de credit pentru aceeași sumă: factură anulată și reemisă. Instrumentul o marchează ca risc scăzut." |
| 4–5 | filter *Modificare furnizor* | **Betonex: one invoice to a different bank account, then back** | "Tiparul clasic de fraudă prin redirecționarea plății. Se verifică telefonic la un număr cunoscut." |
| 5–6 | filter *Creștere de preț* | **Toner +34 %** (price history chart) and **A4 paper 32 % more expensive than another supplier** | "Creșterea apare pe grafic, cu costul suplimentar plătit de atunci." |
| 6–7 | filter *Tipar TVA* | **19 % after 1 Aug 2025**, **AE reverse charge with VAT**, **VAT that doesn't add up** | "Nu dăm verdicte fiscale, doar arătăm ce trebuie verificat." |
| 7–8 | Semnalări → review form | Mark one flag *Respinsă* with a note | "Controlorul decide. Ce respingeți nu mai apare la rularea următoare." |
| 8–9 | Raport | Generate the PDF, open it | "Acesta e livrabilul: lista ordonată, cu dovezi și ce e de verificat." |
| 9–10 | Asistent AI (only if a model is approved) | Ask *"Care furnizori au crescut prețurile cel mai mult?"* and open the sources | "Răspunsul vine din interogări pe baza locală, iar modelul rulează pe calculator." Otherwise skip and mention it. |

**Then stop and go back to the questions** in part 3 of the interview script. Don't continue demoing features.

## If they ask

- *Unde sunt datele?* On their computer only; the app runs locally and doesn't need internet.
- *Cât costă?* "Stabilim prețul după pilot, în funcție de ce găsim." Then ask what they would consider reasonable.
- *Funcționează cu programul nostru?* It reads the XML from SPV or the archive; it doesn't need their ERP.
- *Cât de precis e?* "Pe date sintetice găsește aproape tot; pe date reale aflăm în pilot, iar dumneavoastră
  marcați fiecare semnalare ca reală sau nu."
