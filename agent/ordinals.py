"""Which home on screen does the user mean? "#2", "the second one", "a segunda".

Resolved in code so a follow-up about a card never depends on the model
copying an id correctly: the card numbers are the app's, not the model's.
"""
from __future__ import annotations

import re
import unicodedata

_WORDS = {
    1: r"first|primeir[oa]|primer[oa]?|premi[eè]re?|erste[nrms]?|eerste",
    2: r"second|segund[oa]|deuxi[eè]me|second[e]?|zweite[nrms]?|tweede",
    3: r"third|terceir[oa]|tercer[oa]?|troisi[eè]me|dritte[nrms]?|derde",
    4: r"fourth|quart[oa]|cuart[oa]|quatri[eè]me|vierte[nrms]?|vierde",
    5: r"fifth|quint[oa]|cinqui[eè]me|f[uü]nfte[nrms]?|vijfde",
    6: r"sixth|sext[oa]|sixi[eè]me|sechste[nrms]?|zesde",
}
_LAST = r"last|[uú]ltim[oa]|derni[eè]re?|letzte[nrms]?|laatste"


def _plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def ordinal(message: str, n_shown: int = 6) -> int | None:
    """1-based card number the message points at, or None."""
    text = message.lower()
    m = re.search(r"(?:#|\bn[º°o]\.?\s*|\bnumber\s+|\bnr\.?\s*|\bnummer\s+|\bnum[eé]ro\s+)(\d{1,2})\b", text)
    if m:
        return int(m.group(1))
    plain = _plain(message)
    for n, pat in _WORDS.items():
        if re.search(rf"\b({_plain(pat)})\b", plain):
            return n
    if n_shown and re.search(rf"\b({_plain(_LAST)})\b", plain):
        return n_shown
    return None
