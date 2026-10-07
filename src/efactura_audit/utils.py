"""Small helpers: Romanian CUI/IBAN validation, text normalisation, hashing."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_CUI_KEY = "753217532"


def clean_cui(value: str | None) -> str:
    """Strip the RO prefix, spaces and punctuation from a fiscal code."""
    if not value:
        return ""
    v = re.sub(r"[^0-9A-Za-z]", "", str(value)).upper()
    if v.startswith("RO"):
        v = v[2:]
    return v


def is_valid_cui(value: str | None) -> bool:
    """Validate a Romanian CUI/CIF control digit (2-10 digits)."""
    v = clean_cui(value)
    if not v.isdigit() or not (2 <= len(v) <= 10):
        return False
    body, control = v[:-1], int(v[-1])
    body = body.zfill(9)
    total = sum(int(d) * int(k) for d, k in zip(body, _CUI_KEY))
    check = (total * 10) % 11
    if check == 10:
        check = 0
    return check == control


def cui_control_digit(body: str) -> int:
    body = body.zfill(9)
    total = sum(int(d) * int(k) for d, k in zip(body, _CUI_KEY))
    check = (total * 10) % 11
    return 0 if check == 10 else check


def looks_like_cnp(value: str | None) -> bool:
    """A 13-digit personal numeric code used instead of a CUI (individuals)."""
    v = clean_cui(value)
    return v.isdigit() and len(v) == 13 and v[0] in "123456789"


def clean_iban(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def is_valid_iban(value: str | None) -> bool:
    v = clean_iban(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", v):
        return False
    if v.startswith("RO") and len(v) != 24:
        return False
    rearranged = v[4:] + v[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def iban_check_digits(country: str, bban: str) -> str:
    digits = "".join(str(int(ch, 36)) for ch in (bban + country + "00"))
    return f"{98 - int(digits) % 97:02d}"


def mask_iban(value: str | None) -> str:
    v = clean_iban(value)
    if len(v) < 8:
        return v
    return f"{v[:4]}{'*' * (len(v) - 8)}{v[-4:]}"


def strip_diacritics(text: str) -> str:
    text = text.replace("ş", "ș").replace("ţ", "ț").replace("Ş", "Ș").replace("Ţ", "Ț")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_UNIT_WORDS = {
    "buc", "bucata", "bucati", "pcs", "pc", "set", "kg", "g", "gr", "l", "litri", "litru", "ml",
    "m", "ml.", "mp", "m2", "mc", "m3", "to", "tona", "tone", "ora", "ore", "h", "luna", "lunar",
}
_STOP = {"de", "si", "cu", "pentru", "la", "din", "the", "and", "for", "of", "tip", "model"}
# common Romanian trade synonyms, mapped to one spelling (extend as clients' data shows new ones)
_SYNONYMS = {"xerox": "copiator", "copiere": "copiator", "motorina": "motorina", "diesel": "motorina",
             "benzina95": "benzina", "manopera": "manopera", "servicii": "serviciu", "abonamente": "abonament"}


def normalize_item_name(name: str | None) -> str:
    """Lower-case, remove diacritics/punctuation, join number+unit (``25 kg`` -> ``25kg``)."""
    if not name:
        return ""
    t = strip_diacritics(name).lower()
    t = re.sub(r"(\d)[,.](\d)", r"\1.\2", t)
    t = re.sub(r"[^a-z0-9.]+", " ", t)
    t = re.sub(r"(\d(?:\.\d+)?)\s+(" + "|".join(sorted(_UNIT_WORDS, key=len, reverse=True)) + r")\b", r"\1\2", t)
    tokens = [tok.strip(".") for tok in t.split()]
    tokens = [_SYNONYMS.get(tok, tok) for tok in tokens if tok and tok not in _STOP]
    return " ".join(tokens)


def normalize_invoice_number(num: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (num or "").upper())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(*parts: object, n: int = 16) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return h[:n]


_PERSON_MARKERS = re.compile(
    r"\b(PFA|P\.F\.A\.|I\.?I\.?|INTREPRINDERE INDIVIDUALA|ÎNTREPRINDERE INDIVIDUALĂ|PERSOANA FIZICA|"
    r"PERSOANĂ FIZICĂ|CABINET INDIVIDUAL|I\.F\.|INTREPRINDERE FAMILIALA)\b",
    re.IGNORECASE,
)


def is_sole_trader(name: str | None, cui: str | None = None) -> bool:
    """Heuristic: sole traders' names are personal data under GDPR."""
    if looks_like_cnp(cui):
        return True
    return bool(name and _PERSON_MARKERS.search(name))
