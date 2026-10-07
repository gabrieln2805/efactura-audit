"""Item-name matching.

Suppliers describe the same product differently over time ("Hartie copiator A4 80g/mp, top 500
coli" vs "HARTIE A4 80G 500 COLI/TOP"), and different suppliers use different names for the same
product. We group lines into *item groups* per supplier (seller item code when present, otherwise
fuzzy clustering of normalised names), then link groups across suppliers for price benchmarking.

Two names only match when their numbers agree (``315/70`` must never merge with ``295/80``) and
their unit codes agree.
"""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz

from .utils import short_hash

_NUM = re.compile(r"\d+(?:\.\d+)?")


def numeric_signature(norm: str) -> tuple[str, ...]:
    return tuple(sorted(_NUM.findall(norm)))


# packaging/filler words that may differ between descriptions of the same product
GENERIC = {"top", "set", "buc", "bax", "sac", "rola", "pachet", "pack", "cutie", "bucata", "bucati", "produs",
           "cod", "art", "nr", "x", "tip", "marca", "original", "compatibil"}


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _paired(tok: str, pool: set[str]) -> bool:
    """Spelling/inflection variants share a stem: pix/pixuri, albastru/albastre (not activa/reactiva)."""
    for o in pool:
        if o.startswith(tok) or tok.startswith(o):
            return True
        if _common_prefix(tok, o) >= max(3, int(0.6 * min(len(tok), len(o)))) and fuzz.ratio(tok, o) >= 80:
            return True
    return False


def names_match(a: str, b: str, threshold: float = 88) -> bool:
    """Same product? Strict on purpose: a wrong merge invents price increases, a missed merge only
    thins an item's history.

    Match when numbers agree and either one description is a more detailed version of the other
    (its words are a superset), or every differing word pairs with a spelling variant on the other
    side (``pix``/``pixuri``, ``albastru``/``albastre``) or is a generic packaging word.
    "Transport Bucuresti - Cluj" vs "Transport Bucuresti - Iasi" never match.
    """
    if a == b:
        return True
    if not a or not b or numeric_signature(a) != numeric_signature(b):
        return False
    A, B = set(a.split()), set(b.split())
    common = A & B
    extra_a, extra_b = A - B, B - A
    if not extra_a or not extra_b:
        return len(common) >= max(2, 0.6 * max(len(A), len(B)))
    unpaired = [t for t in extra_a if t not in GENERIC and not _paired(t, extra_b)]
    unpaired += [t for t in extra_b if t not in GENERIC and not _paired(t, extra_a)]
    if not unpaired and len(common) >= 2:
        return True
    return fuzz.token_sort_ratio(a, b) >= max(threshold, 95)   # near-identical strings (typos)


def _cluster(names: list[tuple[str, int]], threshold: float) -> dict[str, str]:
    """Greedy clustering; most frequent names become representatives. Returns name -> rep."""
    reps: list[str] = []
    out: dict[str, str] = {}
    for name, _count in sorted(names, key=lambda t: (-t[1], t[0])):
        for rep in reps:
            if names_match(name, rep, threshold):
                out[name] = rep
                break
        else:
            reps.append(name)
            out[name] = name
    return out


def assign_item_groups(lines: pd.DataFrame, threshold: float = 88) -> pd.DataFrame:
    """Add ``item_group`` and ``item_label`` columns (per supplier)."""
    if lines.empty:
        return lines.assign(item_group=pd.Series(dtype=str), item_label=pd.Series(dtype=str))
    lines = lines.copy()
    lines["unit_code"] = lines["unit_code"].fillna("")
    groups = pd.Series(index=lines.index, dtype=object)
    has_id = lines["seller_item_id"].fillna("").str.len() > 0
    groups[has_id] = ("id:" + lines.loc[has_id, "supplier_cui"] + ":" + lines.loc[has_id, "seller_item_id"])

    rest = lines[~has_id]
    for (cui, unit), part in rest.groupby(["supplier_cui", "unit_code"]):
        counts = part["item_norm"].value_counts()
        mapping = _cluster(list(counts.items()), threshold)
        groups[part.index] = part["item_norm"].map(lambda n: f"n:{cui}:{short_hash(mapping[n], unit, n=10)}")
    lines["item_group"] = groups
    labels = lines.groupby("item_group")["item_name"].agg(lambda s: s.value_counts().index[0])
    lines["item_label"] = lines["item_group"].map(labels)
    return lines


def link_across_suppliers(lines: pd.DataFrame, threshold: float = 90) -> pd.DataFrame:
    """Map item_group -> cross-supplier group id (``xgroup``) for groups naming the same product.

    Groups are compared on all their description variants, not only the most common one.
    """
    if lines.empty:
        return pd.DataFrame(columns=["item_group", "xgroup"])
    info = (lines.groupby("item_group")
            .agg(norms=("item_norm", lambda s: list(s.value_counts().index[:5])), unit=("unit_code", "first"),
                 n=("item_norm", "size"))
            .reset_index()
            .sort_values("n", ascending=False))
    clusters: list[tuple[str, str, list[str]]] = []   # (xgroup id, unit, norms)
    out: dict[str, str] = {}
    for g, norms, unit in zip(info["item_group"], info["norms"], info["unit"]):
        for xid, cunit, cnorms in clusters:
            if cunit == unit and any(names_match(a, b, threshold) for a in norms for b in cnorms):
                out[g] = xid
                cnorms.extend(norms)
                break
        else:
            xid = f"x:{short_hash(norms[0], unit, n=10)}"
            clusters.append((xid, unit, list(norms)))
            out[g] = xid
    return pd.DataFrame({"item_group": list(out), "xgroup": list(out.values())})
