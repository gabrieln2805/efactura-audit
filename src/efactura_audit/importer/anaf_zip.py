"""Read invoices from what companies download from ANAF's SPV portal.

Each SPV download is a ZIP named ``<id>.zip`` holding ``<id>.xml`` (the invoice) and
``semnatura_<id>.xml`` (ANAF's signature). Users often keep folders of these ZIPs, or ZIPs of
ZIPs exported from their accounting software, so we walk folders and nested archives and accept
bare XML files too.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

MAX_MEMBER_BYTES = 50 * 1024 * 1024  # guard against zip bombs
MAX_DEPTH = 3


@dataclass
class XmlSource:
    name: str          # human-readable path, e.g. "archive.zip/4123456789.xml"
    data: bytes
    anaf_id: str       # upload/download id from the file name, when present


def _anaf_id(filename: str) -> str:
    stem = Path(filename).stem
    return stem if stem.isdigit() else ""


def _is_signature(filename: str) -> bool:
    base = Path(filename).name.lower()
    return base.startswith("semnatura") or base.startswith("signature")


def _iter_zip(data: bytes, label: str, depth: int, zip_id: str = "") -> Iterator[XmlSource]:
    if depth > MAX_DEPTH:
        return
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.file_size > MAX_MEMBER_BYTES:
                continue
            name = info.filename
            lower = name.lower()
            if lower.endswith(".zip"):
                yield from _iter_zip(zf.read(info), f"{label}/{name}", depth + 1, _anaf_id(name))
            elif lower.endswith(".xml") and not _is_signature(name):
                yield XmlSource(f"{label}/{name}", zf.read(info), _anaf_id(name) or zip_id)


def iter_sources(paths: list[str | Path]) -> Iterator[XmlSource]:
    """Yield every candidate invoice XML under the given files/folders."""
    for p in paths:
        path = Path(p)
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for f in files:
            if not f.is_file():
                continue
            lower = f.name.lower()
            if lower.endswith(".zip"):
                try:
                    yield from _iter_zip(f.read_bytes(), str(f), 0, _anaf_id(f.name))
                except zipfile.BadZipFile:
                    yield XmlSource(str(f), b"", "")  # reported as a failed import
            elif lower.endswith(".xml") and not _is_signature(f.name):
                yield XmlSource(str(f), f.read_bytes(), _anaf_id(f.name))


def iter_uploaded(name: str, data: bytes) -> Iterator[XmlSource]:
    """Same as iter_sources, for a file uploaded through the app (bytes in memory)."""
    lower = name.lower()
    if lower.endswith(".zip"):
        yield from _iter_zip(data, name, 0, _anaf_id(name))
    elif lower.endswith(".xml") and not _is_signature(name):
        yield XmlSource(name, data, _anaf_id(name))
