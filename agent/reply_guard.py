"""Both directions of the agent <-> Cubi message path (incident 2026-10-27,
docs/incidents.md): what a Cubi search reply IS, and what the answer may say
about it.

Incoming — classify(): a search reply is one of
  results   listing cards came back;
  zero      a GENUINE zero, no cards: Cubi's summary says so ("Your search:
            … — no matches found.") or the reply is only "No properties
            matched…" with no question (filter_listings' zero);
  clarify   Cubi asked a question instead of searching (no summary, no cards,
            a question after the rule) — "anywhere in Europe" did this, and the
            reply still opened with "No properties matched", which the agent
            relayed as "no listings";
  error     the call failed;
  other     anything else (a detail, a comparison…).
Keyed on the reply's SHAPE, not on the "No properties matched" prefix: the
connector is dropping that prefix on clarify replies.

Outgoing — guard_answer(): a claim that nothing was found is cut unless some
reply this turn was a genuine zero; under a clarify reply it is replaced by
Cubi's own question. Raw markers ("<!-- CUBI_… -->", our "[searched with …]"
headers) and bare portal ids outside links are stripped. Tool names are
guards.scrub_tool_names' job, which runs after this.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RESULTS, ZERO, CLARIFY, ERROR, OTHER = "results", "zero", "clarify", "error", "other"

_CARD = re.compile(r"^\s*(?:\*\*\d+\.\s+.*\*\*\s*$|ID:\s*\S)", re.M)
_SUMMARY = re.compile(r"^\s*Your search:.*$", re.M | re.I)
_GENUINE_ZERO = re.compile(r"no matches found", re.I)
_NO_MATCH_PREFIX = re.compile(r"^\s*No properties matched[^\n]*\n?", re.I)


@dataclass(frozen=True)
class Reply:
    kind: str
    question: str = ""      # Cubi's clarifying question (clarify only)
    count: int | None = None


def _question(text: str) -> str:
    """The clarifying question: what follows the last '---' rule (or the whole
    text), minus the no-match boilerplate, when it reads as a question."""
    tail = text.rsplit("\n---", 1)[-1] if "\n---" in text else text
    tail = _NO_MATCH_PREFIX.sub("", tail.strip()).strip()
    return tail if "?" in tail else ""


def classify(res: dict) -> Reply:
    """What a Cubi tool reply is. `res` is mcp_client.call_tool's dict."""
    if not isinstance(res, dict):
        return Reply(OTHER)
    if res.get("is_error"):
        return Reply(ERROR)
    text = res.get("text") or ""
    st = res.get("structured") if isinstance(res.get("structured"), dict) else {}
    listings = st.get("listings") if isinstance(st.get("listings"), list) else None
    count = st.get("count") if isinstance(st.get("count"), int) else None
    summary = (st.get("summary") or "") if st else ""
    m = _SUMMARY.search(text)
    if not summary and m:
        summary = m.group(0)
    has_cards = bool(listings) if listings is not None else bool(_CARD.search(text))
    if has_cards:
        return Reply(RESULTS, count=count)
    if summary:
        if _GENUINE_ZERO.search(summary) or count == 0:
            return Reply(ZERO, count=0)
        return Reply(OTHER, count=count)
    q = _question(text)
    if q:
        return Reply(CLARIFY, question=q)
    # No summary, no question: filter_listings' "No properties matched these
    # filters." and the free-text "No properties matched. Suggest…" line are
    # genuine zeros.
    if _NO_MATCH_PREFIX.match(text):
        return Reply(ZERO, count=0)
    return Reply(OTHER, count=count)


# --- outgoing ---------------------------------------------------------------

# "no listings / nothing matched" in the 7 languages, as a claim about results.
_ZERO_CLAIM = re.compile(
    r"(?i)\b(?:"
    r"no (?:listings?|properties|homes|results|matches|houses|apartments)\b|"
    r"(?:no|zero) (?:properties|listings|homes) (?:matched|were found|found)|"
    r"(?:couldn't|could not|did not|didn't) find (?:any )?(?:listings?|properties|homes|matches)|"
    r"nothing (?:matched|was found|came up)|there are no (?:listings|properties|homes)|"
    r"nenhum (?:im[oó]vel|an[uú]ncio|resultado|casa)|n[aã]o (?:encontr\w+|h[aá]) (?:nenhum|im[oó]veis|an[uú]ncios)|"
    r"ning[uú]n (?:inmueble|anuncio|resultado|piso)|no (?:hay|encontr\w+) (?:inmuebles|anuncios|resultados|viviendas)|"
    r"aucun(?:e)? (?:bien|annonce|r[ée]sultat|logement)|"
    r"keine (?:immobilien|inserate|ergebnisse|treffer|angebote|objekte)|"
    r"geen (?:woningen|resultaten|aanbod|objecten)|"
    r"nessun (?:immobile|annuncio|risultato)|"
    r"(?:нет|не найдено) (?:объявлений|объектов|результатов)"
    r")")
_SENTENCE = re.compile(r"[^.!?\n]*[.!?]?")
_MARKER = re.compile(r"<!--\s*CUBI_[A-Z_]+:.*?-->", re.S)
_HEADER = re.compile(r"^\s*\[(?:searched with|filter_listings failed|the user's)[^\]]*\]\s*$", re.M | re.I)
_URL = re.compile(r"https?://\S+")
_PORTAL_ID = re.compile(r"(?<![\w/%:-])[a-z][a-z0-9]*(?:_[a-z]{2})?:[A-Za-z0-9][\w-]{2,}(?![\w/])")

_ASK_WHERE = {
    "en": "Which country or region should I search?",
    "pt": "Em que país ou região devo procurar?",
    "es": "¿En qué país o región busco?",
    "fr": "Dans quel pays ou quelle région dois-je chercher ?",
    "de": "In welchem Land oder welcher Region soll ich suchen?",
    "nl": "In welk land of welke regio zal ik zoeken?",
    "it": "In quale paese o regione devo cercare?",
    "ru": "В какой стране или регионе искать?",
}


def _strip_ids(text: str) -> tuple[str, int]:
    """Bare portal ids (idealista:12345) outside links: internal, not for users."""
    parts, n, pos = [], 0, 0
    for u in _URL.finditer(text):
        seg, k = _PORTAL_ID.subn("", text[pos:u.start()])
        parts += [seg, u.group()]
        n += k
        pos = u.end()
    seg, k = _PORTAL_ID.subn("", text[pos:])
    parts.append(seg)
    return "".join(parts), n + k


def guard_answer(answer: str, replies: list[Reply], lang: str = "en") -> tuple[str, dict]:
    """The answer with unbacked zero claims, raw markers and bare ids removed.
    Returns (answer, report) — report counts what was changed."""
    report = {"zero_claims_cut": 0, "markers_stripped": 0, "ids_stripped": 0}
    out, n = _MARKER.subn("", answer or "")
    out, k = _HEADER.subn("", out)
    report["markers_stripped"] = n + k
    out, report["ids_stripped"] = _strip_ids(out)

    kinds = {r.kind for r in replies}
    # Only a turn that searched: with no Cubi reply, "no homes on screen yet" is
    # the agent's own state, not a claim about search results.
    if replies and ZERO not in kinds and _ZERO_CLAIM.search(out):
        kept, cut = [], 0
        for line in out.split("\n"):
            sents = [s for s in _SENTENCE.findall(line) if s.strip()]
            keep = [s for s in sents if not _ZERO_CLAIM.search(s)]
            cut += len(sents) - len(keep)
            kept.append("".join(keep).strip() if len(keep) != len(sents) else line)
        out = "\n".join(kept)
        report["zero_claims_cut"] = cut
        clar = next((r.question for r in replies if r.kind == CLARIFY and r.question), "")
        if cut and CLARIFY in kinds and "?" not in out:
            out = (out.rstrip() + "\n\n" + (clar or _ASK_WHERE.get(lang[:2], _ASK_WHERE["en"]))).strip()
    out = re.sub(r"\s*\(\s*\)", "", out)          # "#1 (idealista:123)" → "#1"
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, report
