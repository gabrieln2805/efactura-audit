"""String similarity used by item matching, in pure Python so the engine also runs in a browser (Pyodide).

Same scores as rapidfuzz's ``fuzz.ratio`` and ``fuzz.token_sort_ratio`` (normalised InDel similarity,
0-100): ratio = 2 * LCS / (len(a) + len(b)) * 100. The longest common subsequence uses the
bit-parallel algorithm of Hyyrö (2004), one big-integer step per character.
"""
from __future__ import annotations


def lcs_length(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return 0
    masks: dict[str, int] = {}
    for i, ch in enumerate(a):
        masks[ch] = masks.get(ch, 0) | (1 << i)
    full = (1 << len(a)) - 1
    v = full
    for ch in b:
        u = v & masks.get(ch, 0)
        v = ((v + u) | (v - u)) & full
    return len(a) - bin(v).count("1")


def ratio(a: str, b: str) -> float:
    total = len(a) + len(b)
    if total == 0:
        return 100.0
    # same arithmetic order as rapidfuzz, so scores match to the last bit (thresholds compare with >=)
    distance = total - 2 * lcs_length(a, b)
    return (1.0 - distance / total) * 100


def token_sort_ratio(a: str, b: str) -> float:
    return ratio(" ".join(sorted(a.split())), " ".join(sorted(b.split())))
