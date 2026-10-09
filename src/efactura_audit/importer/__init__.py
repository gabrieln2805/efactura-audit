"""Import RO e-Factura XML (bare or in ANAF ZIPs) into the local store."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from ..store import Store
from ..utils import clean_cui
from .anaf_zip import XmlSource, iter_sources, iter_uploaded
from .parser import NotAnInvoice, ParsedInvoice, parse_invoice_xml

__all__ = ["ImportResult", "import_paths", "import_sources", "iter_uploaded", "parse_invoice_xml", "ParsedInvoice"]


@dataclass
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0          # not an invoice (ANAF messages, other XML)
    other_buyer: int = 0      # issued to a different company than the audited one
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    import_id: str = ""

    def summary(self) -> str:
        return (f"{self.imported} imported, {self.duplicates} already stored, {self.skipped} not invoices, "
                f"{self.other_buyer} for another buyer, {self.failed} failed")


def import_sources(store: Store, sources: Iterable[XmlSource], buyer_cui: str = "",
                   progress: Callable[[int], None] | None = None, label: str = "") -> ImportResult:
    """Import invoices as one tracked import (``label``: the files it came from), so it can be removed later."""
    started = datetime.now()
    res = ImportResult(import_id=f"imp-{started:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}")
    buyer = clean_cui(buyer_cui)
    heads: list[list] = []
    lines: list[list] = []
    vat: list[list] = []
    logs: list[list] = []

    def log(source: str, status: str, message: str = "") -> None:
        logs.append([datetime.now(), source, status, message[:500]])

    with store.connect() as con:
        keys, shas = store.existing_keys(con)
        for i, src in enumerate(sources, 1):
            if progress and i % 100 == 0:
                progress(i)
            if not src.data:
                res.failed += 1
                res.errors.append(f"{src.name}: unreadable archive")
                log(src.name, "failed", "unreadable archive")
                continue
            try:
                inv = parse_invoice_xml(src.data)
            except NotAnInvoice as exc:
                res.skipped += 1
                log(src.name, "skipped", str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the import
                res.failed += 1
                res.errors.append(f"{src.name}: {exc}")
                log(src.name, "failed", str(exc))
                continue
            if buyer and inv.buyer_cui and inv.buyer_cui != buyer:
                res.other_buyer += 1
                log(src.name, "other_buyer", inv.buyer_cui)
                continue
            if inv.invoice_key in keys or inv.xml_sha256 in shas:
                res.duplicates += 1
                continue
            keys.add(inv.invoice_key)
            shas.add(inv.xml_sha256)
            h, ls, vs = store.invoice_rows(inv, src.name, src.anaf_id, res.import_id)
            heads.append(h)
            lines.extend(ls)
            vat.extend(vs)
            res.imported += 1
        log("import", "summary", res.summary())
        con.execute("BEGIN")
        store.bulk_insert(con, heads, lines, vat, logs)
        store.record_import(con, [res.import_id, started, label, buyer, res.imported, res.duplicates, res.skipped,
                                  res.other_buyer, res.failed])
        con.execute("COMMIT")
    return res


def import_paths(store: Store, paths: list[str | Path], buyer_cui: str = "",
                 progress: Callable[[int], None] | None = None) -> ImportResult:
    return import_sources(store, iter_sources(paths), buyer_cui, progress,
                          label=", ".join(Path(p).name for p in paths))
