"""What leaves the machine when a cloud model is used.

Local models see tool results as they are. For cloud models (client's own key, off by default),
tool results pass through `Redactor` first:
- bank accounts are masked (RO49****************1234),
- 13-digit personal numeric codes (CNP) are masked,
- sole traders' names (PFA, II, IF — personal data under GDPR) are replaced by stable pseudonyms
  such as "Furnizor persoană fizică #1"; the answer is mapped back locally before display,
- long row lists are capped, so totals and flags go out rather than whole invoice tables.
"""
from __future__ import annotations

import re
from typing import Any

from ..utils import is_sole_trader, mask_iban

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){12,30}\b")
CNP_RE = re.compile(r"\b[1-9]\d{12}\b")
NAME_KEYS = {"supplier_name", "supplier", "name", "cheapest_supplier", "compared_with", "buyer_name", "company"}
MAX_ROWS = 25


class Redactor:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.pseudonyms: dict[str, str] = {}

    def _pseudo(self, name: str) -> str:
        if name not in self.pseudonyms:
            self.pseudonyms[name] = f"Furnizor persoană fizică #{len(self.pseudonyms) + 1}"
        return self.pseudonyms[name]

    def _text(self, s: str) -> str:
        s = IBAN_RE.sub(lambda m: mask_iban(m.group(0)) if "*" not in m.group(0) else m.group(0), s)
        s = CNP_RE.sub(lambda m: m.group(0)[:1] + "*" * 8 + m.group(0)[-4:], s)
        for real, alias in self.pseudonyms.items():
            s = s.replace(real, alias)
        return s

    def _collect_names(self, obj: Any, key: str | None = None) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._collect_names(v, k)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_names(v, key)
        elif isinstance(obj, str) and key in NAME_KEYS:
            for part in obj.split(" / "):
                if is_sole_trader(part):
                    self._pseudo(part)

    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            items = [self._walk(v) for v in obj[:MAX_ROWS]]
            if len(obj) > MAX_ROWS:
                items.append({"note": f"{len(obj) - MAX_ROWS} more rows not sent to the cloud model"})
            return items
        if isinstance(obj, str):
            return self._text(obj)
        return obj

    def outgoing(self, obj: Any) -> Any:
        """Redact a tool result before it is sent to a cloud model."""
        if not self.enabled:
            return obj
        self._collect_names(obj)
        return self._walk(obj)

    def incoming(self, text: str) -> str:
        """Map pseudonyms in the model's answer back to real names (locally, for display)."""
        if not self.enabled:
            return text
        for real, alias in self.pseudonyms.items():
            text = text.replace(alias, real)
        return text
