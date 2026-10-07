"""Pure-Python string similarity (fuzzy.py) must score exactly like rapidfuzz, which it replaces so the
engine runs in a browser: a score off by one bit can flip a >= threshold and change item groups."""
import random

import pytest

from efactura_audit import fuzzy


@pytest.mark.parametrize("a,b,expected", [
    ("", "", 100.0), ("abc", "", 0.0), ("abc", "abc", 100.0), ("pix", "pixuri", 66.66666666666667),
    ("hartie a4 80g", "a4 hartie 80g", 76.92307692307692),
])
def test_known_scores(a, b, expected):
    assert fuzzy.ratio(a, b) == expected


def test_token_sort_ignores_word_order_and_spacing():
    assert fuzzy.token_sort_ratio("hartie a4 80g", "a4  hartie 80g") == 100.0


def test_identical_to_rapidfuzz():
    rf = pytest.importorskip("rapidfuzz.fuzz")
    rnd = random.Random(1)
    alphabet = "abcde ăîșț0123456789/.-"
    for _ in range(20_000):
        a = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
        b = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
        assert fuzzy.ratio(a, b) == rf.ratio(a, b), (a, b)
        assert fuzzy.token_sort_ratio(a, b) == rf.token_sort_ratio(a, b), (a, b)
