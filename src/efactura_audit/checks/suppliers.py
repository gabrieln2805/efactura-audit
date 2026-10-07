"""Supplier master-data changes.

- iban_one_off: one or a few invoices pay to a different account, then the usual one returns —
  the classic pattern of payment-redirection fraud (high).
- iban_changed: the supplier's bank account changes and stays changed (medium: verify by phone
  on a known number, never via the contact details on the invoice).
- shared_iban: two suppliers with different CUIs use the same bank account (high).
- iban_invalid / invalid_cui: control digits do not check out.
- new_supplier: a supplier first seen after the start of the data with significant spend.
- name_changed: the same CUI appears under a different name.
"""
from __future__ import annotations

import pandas as pd

from ..utils import is_valid_cui, is_valid_iban, mask_iban, normalize_item_name
from .base import AuditContext, lei, make_flag


def run(ctx: AuditContext) -> list[dict]:
    cfg = ctx.cfg("suppliers")
    grace = pd.Timedelta(days=int(cfg.get("new_supplier_grace_days", 60)))
    new_min = float(cfg.get("new_supplier_min_amount_ron", 5000))
    inv = ctx.invoices.sort_values(["issue_date", "number"])
    flags: list[dict] = []

    shared = (inv[inv["supplier_iban"].fillna("") != ""]
              .groupby("supplier_iban")["supplier_cui"].nunique())
    shared_ibans = set(shared[shared > 1].index)
    bad_cuis: set[str] = set()

    for cui, part in inv.groupby("supplier_cui"):
        name = part["supplier_name"].iloc[-1]
        first = part.iloc[0]

        # --- IBAN sequence -------------------------------------------------------------------
        with_iban = part[part["supplier_iban"].fillna("") != ""]
        if not with_iban.empty:
            seq = with_iban["supplier_iban"].tolist()
            usual = None
            i = 0
            while i < len(seq):
                if usual is None:
                    usual = seq[i]
                    i += 1
                    continue
                if seq[i] == usual:
                    i += 1
                    continue
                j = i
                while j < len(seq) and seq[j] == seq[i]:
                    j += 1
                block = with_iban.iloc[i:j]
                returns = j < len(seq) and seq[j] == usual
                new_iban = seq[i]
                if returns and len(block) <= 3:
                    rule, sev, score = "iban_one_off", "high", 0.9
                    at_risk = float(block["amt"].sum())
                    t_en = f"{name}: {len(block)} invoice(s) paid to a different bank account, then back to the usual one"
                    t_ro = f"{name}: {len(block)} factur(i) cu alt cont bancar, apoi revenire la contul obișnuit"
                else:
                    rule, sev, score = "iban_changed", "medium", 0.7
                    at_risk = float(block.iloc[0]["amt"])
                    t_en = f"{name}: bank account changed from invoice {block.iloc[0]['number']}"
                    t_ro = f"{name}: cont bancar schimbat începând cu factura {block.iloc[0]['number']}"
                flags.append(make_flag(
                    check="supplier", rule=rule, severity=sev, score=score, supplier_cui=cui, supplier_name=name,
                    invoice_keys=block["invoice_key"].tolist(), invoice_numbers=block["number"].tolist(),
                    issue_date=block.iloc[0]["issue_date"], amount_at_risk=at_risk, title_en=t_en, title_ro=t_ro,
                    evidence={
                        "usual_iban": mask_iban(usual), "new_iban": mask_iban(new_iban),
                        "usual_iban_full": usual, "new_iban_full": new_iban,
                        "invoices_with_new_iban": int(len(block)),
                        "first_date": str(block.iloc[0]["issue_date"].date()),
                        "returned_to_usual": bool(returns),
                        "new_iban_valid": is_valid_iban(new_iban),
                        "what_to_check_en": "Confirm the account with the supplier by phone on a number you already have — not one from the invoice or email.",
                        "what_to_check_ro": "Confirmați contul cu furnizorul telefonic, la un număr pe care îl aveți deja — nu cel din factură sau e-mail.",
                    },
                ))
                if not returns:
                    usual = new_iban
                i = j

            for iban in set(seq):
                if not is_valid_iban(iban):
                    rows = with_iban[with_iban["supplier_iban"] == iban]
                    flags.append(make_flag(
                        check="supplier", rule="iban_invalid", severity="medium", score=0.6, supplier_cui=cui,
                        supplier_name=name, invoice_keys=rows["invoice_key"].tolist()[:20],
                        invoice_numbers=rows["number"].tolist()[:20], issue_date=rows.iloc[0]["issue_date"],
                        amount_at_risk=None, id_extra=iban,
                        title_en=f"{name}: bank account {mask_iban(iban)} fails the IBAN check",
                        title_ro=f"{name}: contul {mask_iban(iban)} nu trece verificarea IBAN",
                        evidence={"iban": mask_iban(iban), "iban_full": iban, "invoices": int(len(rows))},
                    ))

        # --- CUI checksum ------------------------------------------------------------------------
        if cui and not is_valid_cui(cui):
            bad_cuis.add(cui)
            flags.append(make_flag(
                check="supplier", rule="invalid_cui", severity="medium", score=0.65, supplier_cui=cui, supplier_name=name,
                invoice_keys=[first["invoice_key"]], invoice_numbers=[first["number"]], issue_date=first["issue_date"],
                amount_at_risk=float(part["amt"].sum()),
                title_en=f"{name}: fiscal code {cui} fails the CUI control digit",
                title_ro=f"{name}: codul fiscal {cui} nu trece verificarea cifrei de control",
                evidence={"cui": cui, "invoices": int(len(part)), "total_ron": round(float(part["amt"].sum()), 2),
                          "what_to_check_en": "Look the company up on ANAF's public register before paying.",
                          "what_to_check_ro": "Verificați firma în registrul public ANAF înainte de plată."},
            ))

        # --- name changes -----------------------------------------------------------------------
        names = part["supplier_name"].dropna().map(normalize_item_name).unique()
        if len(names) > 1:
            flags.append(make_flag(
                check="supplier", rule="name_changed", severity="low", score=0.3, supplier_cui=cui, supplier_name=name,
                invoice_keys=[part.iloc[-1]["invoice_key"]], invoice_numbers=[part.iloc[-1]["number"]],
                issue_date=part.iloc[-1]["issue_date"], amount_at_risk=None,
                title_en=f"CUI {cui} appears under {len(names)} different names",
                title_ro=f"CUI {cui} apare sub {len(names)} denumiri diferite",
                evidence={"names": part["supplier_name"].dropna().unique().tolist()},
            ))

        # --- new supplier -------------------------------------------------------------------------
        if first["issue_date"] > ctx.data_start + grace:
            early = part[part["issue_date"] <= first["issue_date"] + pd.Timedelta(days=60)]
            spend = float(early["amt"].sum())
            if spend >= new_min:
                risky = any(ib in shared_ibans for ib in part["supplier_iban"].dropna()) or cui in bad_cuis
                # sparse suppliers also "appear" late in the data, so size alone is only medium
                sev = "high" if risky else ("medium" if spend >= 20_000 else "low")
                flags.append(make_flag(
                    check="supplier", rule="new_supplier", severity=sev, score=0.6 + (0.2 if risky else 0),
                    supplier_cui=cui, supplier_name=name, invoice_keys=early["invoice_key"].tolist(),
                    invoice_numbers=early["number"].tolist(), issue_date=first["issue_date"], amount_at_risk=spend,
                    title_en=f"New supplier {name}: {lei(spend)} in its first 60 days",
                    title_ro=f"Furnizor nou {name}: {lei(spend, 'ro')} în primele 60 de zile",
                    evidence={
                        "first_invoice": first["number"], "first_date": str(first["issue_date"].date()),
                        "spend_first_60_days_ron": round(spend, 2), "invoices_first_60_days": int(len(early)),
                        "shares_bank_account_with_other_supplier": bool(risky and cui not in bad_cuis),
                        "invalid_cui": cui in bad_cuis,
                        "what_to_check_en": "Check who approved the supplier, that a contract or order exists and that the goods or services were received.",
                        "what_to_check_ro": "Verificați cine a aprobat furnizorul, existența unui contract sau a unei comenzi și recepția bunurilor sau serviciilor.",
                    },
                ))

    # --- shared bank accounts ---------------------------------------------------------------------
    for iban in shared_ibans:
        rows = inv[inv["supplier_iban"] == iban]
        sups = rows.groupby("supplier_cui")["supplier_name"].last()
        flags.append(make_flag(
            check="supplier", rule="shared_iban", severity="high", score=0.85, supplier_cui=",".join(sups.index),
            supplier_name=" / ".join(sups.values), invoice_keys=rows["invoice_key"].tolist()[:30],
            invoice_numbers=rows["number"].tolist()[:30], issue_date=rows["issue_date"].max(),
            amount_at_risk=float(rows["amt"].sum()), id_extra=iban,
            title_en=f"{len(sups)} different suppliers use the same bank account {mask_iban(iban)}",
            title_ro=f"{len(sups)} furnizori diferiți folosesc același cont bancar {mask_iban(iban)}",
            evidence={"iban": mask_iban(iban), "iban_full": iban,
                      "suppliers": [{"cui": c, "name": n} for c, n in sups.items()],
                      "total_ron": round(float(rows["amt"].sum()), 2),
                      "what_to_check_en": "Unrelated companies rarely share an account; check ownership and approvals.",
                      "what_to_check_ro": "Firme neafiliate rareori au cont comun; verificați acționariatul și aprobările."},
        ))
    return flags
