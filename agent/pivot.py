"""Any language through English: name it, translate in, run the turn, translate back.

The agent's routing, card ordinals and filter clean-up are word lists in six
languages (lang.py, skills.py, ordinals.py, normalize.py). A message in any other
language is translated to English first, so all of that keeps working, and the
answer and its buttons are translated back. Cubi's connector also serves Russian
(`CUBI_I18N`), so a Russian conversation asks it for lang=ru as well.

Every call is fail-safe: if naming or translating fails, the turn runs on the
original text, or the answer is shown in English with a one-line note.
"""
from __future__ import annotations

import json
import re

from . import llm
from .lang import LANGS

# Languages Cubi's connector serves beyond the agent's six (property_mcp: en/pt/es/fr/de/nl/ru).
CUBI_I18N = {"ru"}
ROLE = "super"

IDENTIFY = (
    "Identify the language of the user's message to a home-search assistant and translate it to "
    "English. Reply with JSON only: {\"lang\": ISO 639-1 code, \"name\": the language's English name, "
    "\"english\": the translation}. Keep place names as the user wrote them, and keep numbers, prices, "
    "currencies, '#2'-style references and T2/T3 typologies exactly. A room count that includes the living "
    "room (Italian bilocale/trilocale, Russian двухкомнатная, Polish dwupokojowe) is N rooms = N-1 "
    "bedrooms: write it as bedrooms. If the message is already English, "
    "\"english\" is the message unchanged."
)

BACK = (
    "Translate every string in the JSON below from English to {name}, for a home-search assistant's user. "
    "Reply with the same JSON shape only. Keep exactly as they are: URLs, markdown link targets and "
    "formatting, citation marks like [1], [S1] or [X1], '#2'-style references, numbers, prices, currencies, "
    "units, place names and listing titles in quotation marks. A bedroom count stays a bedroom count "
    "('2-bed' is two bedrooms, not a two-room flat such as двухкомнатная or bilocale). Keep the meaning, "
    "including any caveat "
    "(asking prices are not a valuation; nothing was sent)."
)

# Languages whose usual flat size is a room count including the living room: the
# general rule alone lost to habit (two-bedroom → двухкомнатная, live 2026-10-24).
ROOM_HINTS = {
    "ru": "say bedrooms as спальни ('one-bedroom' = 'с одной спальней', 'two-bedroom' = 'с двумя спальнями'), "
          "never однокомнатная/двухкомнатная/трёхкомнатная, which count the living room too",
    "uk": "say bedrooms as спальні ('one-bedroom' = 'з однією спальнею', 'two-bedroom' = 'з двома спальнями'), "
          "never однокімнатна/двокімнатна/трикімнатна, which count the living room too",
    "pl": "say bedrooms as sypialnie ('one-bedroom' = 'z jedną sypialnią', 'two-bedroom' = 'z dwiema sypialniami'), "
          "never kawalerka/dwupokojowe/trzypokojowe, which count the living room too",
    "cs": "say bedrooms as ložnice ('one-bedroom' = 's jednou ložnicí', 'two-bedroom' = 'se dvěma ložnicemi'), "
          "never 1+kk/2+kk/2+1, which count the living room too",
    "it": "say bedrooms as camere da letto ('one-bedroom' = 'con una camera da letto', 'two-bedroom' = "
          "'con due camere da letto'), never monolocale/bilocale/trilocale, which count the living room too",
}

NOTE = "(Translation unavailable right now, so this answer is in English.)"

_URL = re.compile(r"https?://[^\s)\]>]+")
_BED = re.compile(r"\b(\d+)[-\u2011 ]bed\b")


def _json(cli, system: str, user: str, max_tokens: int) -> dict:
    r = cli.chat.completions.create(
        model=llm.model(ROLE), temperature=0, max_tokens=max_tokens, extra_body=llm.NO_THINK,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    text = (r.choices[0].message.content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    out = json.loads(text)
    if not isinstance(out, dict):
        raise ValueError("not a JSON object")
    return out


def identify(cli, text: str) -> tuple[str, str, str] | None:
    """(lang code, English name, English text), or None if the call failed."""
    try:
        out = _json(cli, IDENTIFY, text, 600)
    except Exception:  # noqa: BLE001 - the turn falls back to the six-language path
        return None
    code = str(out.get("lang") or "").strip().lower()[:3]
    english = str(out.get("english") or "").strip()
    if not re.fullmatch(r"[a-z]{2,3}", code) or not english:
        return None
    return code, str(out.get("name") or code).strip()[:40], english


def back(cli, name: str, answer: str, suggestions: list[str], code: str = "") -> tuple[str, list[str]] | None:
    """The answer and buttons in `name`, or None if the call failed or changed a URL."""
    # "2‑bed" read as a room count became двухкомнатные (one bedroom fewer) in Russian.
    payload = {"answer": _BED.sub(r"\1-bedroom", answer), "suggestions": suggestions}
    try:
        system = BACK.replace("{name}", name) + (f" In {name}, {ROOM_HINTS[code]}." if code in ROOM_HINTS else "")
        out = _json(cli, system, json.dumps(payload, ensure_ascii=False),
                    max(800, len(answer)))
    except Exception:  # noqa: BLE001 - shown in English instead
        return None
    text = out.get("answer")
    chips = out.get("suggestions")
    if not isinstance(text, str) or not text.strip():
        return None
    # The guards checked the English answer's links; a translation that changes
    # one (or drops or adds one) would bypass them.
    if sorted(_URL.findall(text)) != sorted(_URL.findall(answer)):
        return None
    if not (isinstance(chips, list) and len(chips) == len(suggestions) and all(isinstance(c, str) for c in chips)):
        chips = list(suggestions)
    return text, [c.strip() or s for c, s in zip(chips, suggestions)]


def native(code: str) -> bool:
    return code in LANGS
