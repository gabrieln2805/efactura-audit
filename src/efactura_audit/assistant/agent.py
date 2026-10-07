"""The assistant: a tool-calling loop over the audit tools.

Figures come from tool results (SQL), not from the model; every answer carries the list of tool
calls and results it was built from, so the user can check it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .privacy import Redactor
from .providers import Provider, ProviderError

SYSTEM_PROMPT = """You are the e-Factura audit assistant for {company}. You help a finance controller explore
supplier invoices and the audit flags found in them. The data is stored locally; you reach it only through tools.

Rules:
1. Every number, name, date and invoice number in your answer must come from a tool result in this conversation.
   Never estimate or invent figures. If the tools do not return something, say you could not find it.
2. Reply in the user's language: Romanian if they write in Romanian, English if they write in English.
   In Romanian use Romanian number format (1.234,56 lei).
3. Descriptive only. Do not give tax, legal or accounting advice or conclusions (for example whether VAT is
   deductible or whether a supplier committed fraud). Flags are prompts to check, not conclusions; if asked for
   advice, say you cannot give it and suggest asking their accountant or tax adviser, then offer the facts you have.
4. Mention the flag IDs and invoice numbers your answer relies on.
5. Be brief: a short answer, then a compact list if useful.

Data: {n_invoices} invoices from {first_date} to {last_date}. Today is {today}.
"This quarter", "this month" and similar mean the latest period in the data unless the user says otherwise.
Amounts are in lei (RON) including VAT unless stated."""


@dataclass
class ToolTrace:
    name: str
    arguments: dict
    result: Any
    sent_to_model: Any = None


@dataclass
class Answer:
    text: str
    trace: list[ToolTrace] = field(default_factory=list)
    error: str | None = None
    rounds: int = 0
    model: str = ""
    provider: str = ""


class Assistant:
    def __init__(self, provider: Provider, backend, overview: dict | None = None, max_rounds: int = 6):
        self.provider = provider
        self.backend = backend
        self.max_rounds = max_rounds
        self.redactor = Redactor(enabled=provider.is_cloud)
        ov = overview or {}
        self.system = SYSTEM_PROMPT.format(
            company=ov.get("company") or "the company", n_invoices=ov.get("invoices", "?"),
            first_date=ov.get("first_date", "?"), last_date=ov.get("last_date", "?"), today=date.today().isoformat())
        if provider.is_cloud:
            self.system += ("\nSome supplier names are pseudonymised (\"Furnizor persoană fizică #n\") and bank accounts "
                            "are masked for privacy; use them as given.")

    def ask(self, question: str, history: list[dict] | None = None) -> Answer:
        messages = list(history or []) + [{"role": "user", "content": question}]
        tools = self.backend.tool_specs()
        trace: list[ToolTrace] = []
        for rnd in range(1, self.max_rounds + 1):
            try:
                turn = self.provider.chat(self.system, messages, tools)
            except ProviderError as exc:
                return Answer(text="", trace=trace, error=str(exc), rounds=rnd,
                              model=self.provider.model, provider=self.provider.name)
            if not turn.tool_calls:
                return Answer(text=self.redactor.incoming(turn.text.strip()), trace=trace, rounds=rnd,
                              model=self.provider.model, provider=self.provider.name)
            messages.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
            for call in turn.tool_calls:
                try:
                    result = self.backend.call(call["name"], call.get("arguments") or {})
                except Exception as exc:  # noqa: BLE001 - report tool errors to the model
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                sent = self.redactor.outgoing(result)
                content = json.dumps(sent, ensure_ascii=False, default=str)
                if len(content) > 12000:
                    content = content[:12000] + ' …"(truncated)"'
                trace.append(ToolTrace(call["name"], call.get("arguments") or {}, result, sent))
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": content})
        return Answer(text="", trace=trace, error="The assistant did not finish within the allowed number of steps.",
                      rounds=self.max_rounds, model=self.provider.model, provider=self.provider.name)
