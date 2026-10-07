"""Scripted stand-ins for real models, used to test the assistant loop and the model test harness."""
from __future__ import annotations

import json

from efactura_audit.assistant.providers import ScriptedProvider, Turn


def ro(x: float) -> str:
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


ROUTES = [
    ("Câte facturi", "audit_overview", {}),
    ("cheltuit cel mai mult și ce sumă", "top_suppliers", {"limit": 3}),
    ("duplicate", "list_flags", {"check": "near_duplicate", "severity": "high"}),
    ("crescut prețurile", "price_changes", {}),
    ("peste 10.000", "search_invoices", {"flagged_only": True, "min_amount": 10000, "order_by": "amount"}),
    ("contul bancar", "list_flags", {"check": "supplier"}),
    ("Betonex", "supplier_summary", {"supplier": "Betonex"}),
    ("Explică semnalarea", "get_flag", None),
    ("furnizori noi", "list_flags", {"check": "supplier", "severity": "high"}),
    ("ultimul trimestru", "spend_over_time", {"granularity": "quarter"}),
    ("obiect JSON", "top_suppliers", {"limit": 1}),
    ("listă JSON", "list_flags", {"check": "vat", "limit": 50}),
    ("most open flags", "run_sql", {"query": "SELECT supplier_name, COUNT(*) n FROM fct_flags WHERE status <> 'dismissed' "
                                             "AND supplier_cui NOT LIKE '%,%' GROUP BY 1 ORDER BY n DESC, 1 LIMIT 1"}),
]


def _answer(question: str, res: dict) -> str:
    if "Câte facturi" in question:
        return f"Avem {res['invoices']} facturi, din {res['first_date']} până la {res['last_date']}."
    if "obiect JSON" in question:
        s = res["suppliers"][0]
        return json.dumps({"furnizor": s["supplier_name"], "suma_totala": s["spend_ron"]}, ensure_ascii=False)
    if "cheltuit cel mai mult" in question:
        s = res["suppliers"][0]
        return f"Cel mai mult ați cheltuit la {s['supplier_name']}: {ro(s['spend_ron'])} lei."
    if "listă JSON" in question:
        nums = sorted({n for f in res["flags"] for n in f["invoice_numbers"]})
        return json.dumps(nums)
    if "crescut prețurile" in question:
        top = res["suppliers_ranked_by_increase"][0]
        return f"Cea mai mare creștere este la {top['supplier']}, de până la {top['max_increase_pct']}%."
    if "peste 10.000" in question:
        return "Facturile semnalate: " + ", ".join(i["number"] for i in res["invoices"][:5]) + "."
    if "Betonex" in question:
        s = res["suppliers"][0]
        return f"Total cheltuit cu {s['supplier_name']}: {ro(s['total_spend_ron'])} lei."
    if "Explică semnalarea" in question:
        return f"Semnalarea privește facturile {', '.join(res['invoice_numbers'])}: {res['title']}"
    if "ultimul trimestru" in question:
        last = res["series"][-1]
        return f"În trimestrul {last['period']} ați cheltuit {ro(last['spend_ron'])} lei."
    if "most open flags" in question:
        r = res["rows"][0]
        return f"The supplier with the most open flags is {r['supplier_name']} ({r['n']} flags)."
    if "flags" in res:
        parts = [f"{f['flag_id']} – {f['supplier_name']} ({', '.join(f['invoice_numbers'][:3])})" for f in res["flags"][:6]]
        return "Am găsit aceste semnalări pentru furnizori: " + "; ".join(parts) + "."
    return "Nu am găsit informația."


def oracle_provider() -> ScriptedProvider:
    def script(messages: list[dict]) -> Turn:
        question = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if messages[-1]["role"] == "user":
            if "deduce" in question:
                return Turn(text="Nu pot oferi consultanță fiscală; întrebați contabilul sau consultantul fiscal. "
                                 "Pot să vă arăt ce semnalări are factura.")
            for key, tool, args in ROUTES:
                if key in question:
                    if tool == "get_flag":
                        args = {"flag_id": question.split()[-1].rstrip(".")}
                    return Turn(tool_calls=[{"id": "t1", "name": tool, "arguments": args}])
            return Turn(text="Nu știu.")
        return Turn(text=_answer(question, json.loads(messages[-1]["content"])))
    return ScriptedProvider(script, model="oracle")


def careless_provider() -> ScriptedProvider:
    """Answers from 'memory' in English with invented numbers, never calls tools."""
    return ScriptedProvider(lambda messages: Turn(text="The total is about 1,000 invoices and 5 million lei. "
                                                      "Yes, you can deduct the VAT."), model="careless")
