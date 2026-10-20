"""Deterministic post-checks on the model's answer. No model is trusted with these."""
from __future__ import annotations

import re

URL_RE = re.compile(r"https?://[^\s<>\"'\])]+")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")

ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")
NUMBERED_RE = re.compile(r"^(\s*)\d+([.)])(\s+)")

_UNVERIFIED_NOTE = {
    "en": "Something that did not come from Cubi's results was removed.",
    "pt": "Foi removido algo que não veio dos resultados da Cubi.",
    "es": "Se ha eliminado algo que no procedía de los resultados de Cubi.",
    "fr": "Un élément qui ne provenait pas des résultats de Cubi a été supprimé.",
    "de": "Etwas, das nicht aus den Cubi-Ergebnissen stammt, wurde entfernt.",
    "nl": "Iets dat niet uit de resultaten van Cubi kwam, is verwijderd.",
}
NOT_A_VALUATION = {
    "en": "These are asking prices of similar active listings, not a valuation.",
    "pt": "São preços pedidos de anúncios semelhantes ativos, não uma avaliação.",
    "es": "Son precios de oferta de anuncios similares activos, no una tasación.",
    "fr": "Ce sont des prix demandés d'annonces similaires actives, pas une estimation.",
    "de": "Das sind Angebotspreise ähnlicher aktiver Inserate, keine Bewertung.",
    "nl": "Dit zijn vraagprijzen van vergelijkbare actieve advertenties, geen taxatie.",
}


def _clean(url: str) -> str:
    return url.rstrip(".,;:!?*_")


def _items(answer: str) -> list[list[str]]:
    """Split into blocks: each list item (with its continuation lines) is one block,
    every other line is a block of its own."""
    blocks: list[list[str]] = []
    in_item = False
    for line in answer.splitlines():
        if ITEM_RE.match(line):
            blocks.append([line])
            in_item = True
        elif in_item and line.strip() and line[:1].isspace():
            blocks[-1].append(line)
        else:
            blocks.append([line])
            in_item = False
    return blocks


def verify_urls(answer: str, tool_text: str, lang: str = "en") -> tuple[str, list[str], int]:
    """Every URL must appear verbatim in the tools' output.

    A list item carrying an unverified link is dropped whole — when the model
    invents a listing, its price and place are invented too, so stripping only
    the link would leave a fake home on screen. Elsewhere only the link goes.
    Returns (answer, removed URLs, list items dropped).
    """
    removed: list[str] = []

    def bad(text: str) -> list[str]:
        return [u for u in (_clean(m.group(0)) for m in URL_RE.finditer(text)) if u not in tool_text]

    kept: list[str] = []
    dropped = 0
    n = 0
    for block in _items(answer):
        text = "\n".join(block)
        b = bad(text)
        if b and ITEM_RE.match(block[0]):
            removed += b
            dropped += 1
            continue
        if ITEM_RE.match(block[0]) and NUMBERED_RE.match(block[0]):
            n += 1
            text = NUMBERED_RE.sub(lambda m: f"{m.group(1)}{n}{m.group(2)}{m.group(3)}", text, count=1)
        elif not ITEM_RE.match(block[0]) and block[0].strip():
            n = 0  # prose between lists starts a new numbering
        kept.append(text)
    out = "\n".join(kept)

    def repl(m: re.Match) -> str:
        url = _clean(m.group(0))
        if url in tool_text:
            return m.group(0)
        removed.append(url)
        return ""

    out = URL_RE.sub(repl, out)
    # Markdown links whose target was stripped: [text]() → text
    out = re.sub(r"\[([^\]]+)\]\(\s*\)", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    if removed:
        out = out.rstrip() + "\n\n_" + _UNVERIFIED_NOTE.get(lang, _UNVERIFIED_NOTE["en"]) + "_"
    return out, removed, dropped


def scrub_contacts(answer: str) -> tuple[str, int]:
    """Agents' emails/phones are never returned by the connector; belt and braces."""
    n = 0

    def drop(_m: re.Match) -> str:
        nonlocal n
        n += 1
        return "[contact details removed]"

    out = EMAIL_RE.sub(lambda m: m.group(0) if m.group(0).endswith(("cubi.estate",)) else drop(m), answer)
    out = PHONE_RE.sub(drop, out)
    return out, n


# The model usually says it already, in its own words; only add the line when
# no "valuation" word in the answer's language appears.
_VALUATION_WORDS = {
    "en": ("valuation", "appraisal"), "pt": ("avaliação",), "es": ("tasación", "valoración"),
    "fr": ("estimation", "évaluation", "expertise"), "de": ("bewertung", "gutachten", "wertermittlung"),
    "nl": ("taxatie", "waardebepaling"),
}


def ensure_not_a_valuation(answer: str, lang: str) -> str:
    low = answer.lower()
    if any(w in low for w in _VALUATION_WORDS.get(lang, ()) + _VALUATION_WORDS["en"]):
        return answer
    return answer.rstrip() + "\n\n" + NOT_A_VALUATION.get(lang, NOT_A_VALUATION["en"])


# A price comparison may say below / within / above the range. It must not turn that
# into a verdict ("a good deal", "overpriced"). Sentences carrying one are removed —
# except where the verdict word is negated or quoted back as the user's question.
_VERDICT = re.compile(
    r"(good deal|great deal|bargain|great value|good value|fairly priced|fair price|overpriced|underpriced|"
    r"worth (buying|it)|bom neg[oó]cio|pechincha|sobrevalorizad|caro demais|buen negocio|ganga|chollo|"
    r"sobrevalorad|bonne affaire|surévalu|trop cher|gutes geschäft|schnäppchen|überteuert|"
    r"goede deal|koopje|te duur|overgewaardeerd)", re.I)
_VERDICT_NOTE = {
    "en": "Whether it is a good buy depends on condition, view and exact location — get an independent valuation before deciding.",
    "pt": "Se é uma boa compra depende do estado, da vista e da localização exata — peça uma avaliação independente antes de decidir.",
    "es": "Si es una buena compra depende del estado, las vistas y la ubicación exacta: pida una tasación independiente antes de decidir.",
    "fr": "Savoir si c'est un bon achat dépend de l'état, de la vue et de l'emplacement exact : demandez une estimation indépendante avant de décider.",
    "de": "Ob sich der Kauf lohnt, hängt von Zustand, Aussicht und genauer Lage ab – holen Sie vor einer Entscheidung ein unabhängiges Gutachten ein.",
    "nl": "Of het een goede koop is, hangt af van staat, uitzicht en exacte ligging — laat vóór een beslissing een onafhankelijke taxatie doen.",
}


def _drop_sentences(answer: str, pattern: re.Pattern, keep_questions: bool = False) -> tuple[str, int]:
    """Remove matching sentences, line by line, keeping the answer's layout."""
    n, lines = 0, []
    for line in answer.split("\n"):
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [x for x in parts if not pattern.search(x) or (keep_questions and x.rstrip().endswith("?"))]
        n += len(parts) - len(kept)
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), n


def drop_price_verdicts(answer: str, lang: str) -> tuple[str, int]:
    out, n = _drop_sentences(answer, _VERDICT, keep_questions=True)
    if not n:
        return answer, 0
    return out + "\n\n" + _VERDICT_NOTE.get(lang, _VERDICT_NOTE["en"]), n


# Contact: nothing is sent until the user follows Cubi's link. A first-person claim
# of having sent, contacted or booked something is false by construction.
_SENT_CLAIM = re.compile(
    r"\b(i(?:'ve| have)? (?:sent|contacted|messaged|emailed|booked|scheduled|forwarded|reached out)|"
    r"(?:enviei|contactei|marquei|agendei|reservei)|"
    r"(?:he enviado|he contactado|envié|contacté|reservé|agendé)|"
    r"j'ai (?:envoyé|contacté|réservé|transmis)|"
    r"ich habe [^.]{0,40}(?:gesendet|geschickt|kontaktiert|gebucht|weitergeleitet)|"
    r"ik heb [^.]{0,40}(?:verstuurd|gestuurd|gecontacteerd|geboekt|doorgestuurd))", re.I)
_NOT_SENT = {
    "en": "Nothing has been sent yet: you send it yourself from the Cubi link above.",
    "pt": "Ainda não foi enviado nada: é você quem envia, a partir da ligação da Cubi acima.",
    "es": "Todavía no se ha enviado nada: lo envía usted desde el enlace de Cubi de arriba.",
    "fr": "Rien n'a encore été envoyé : c'est vous qui l'envoyez depuis le lien Cubi ci-dessus.",
    "de": "Es wurde noch nichts gesendet: Sie senden es selbst über den Cubi-Link oben.",
    "nl": "Er is nog niets verstuurd: u verstuurt het zelf via de Cubi-link hierboven.",
}


def drop_sent_claims(answer: str, lang: str) -> tuple[str, int]:
    out, n = _drop_sentences(answer, _SENT_CLAIM)
    if not n:
        return answer, 0
    return out + "\n\n" + _NOT_SENT.get(lang, _NOT_SENT["en"]), n


def apply(answer: str, tool_text: str, lang: str, used_tools: set[str]) -> tuple[str, dict]:
    answer, removed, dropped = verify_urls(answer, tool_text, lang)
    answer, scrubbed = scrub_contacts(answer)
    verdicts = sent = 0
    if "compare_asking_prices" in used_tools:
        answer, verdicts = drop_price_verdicts(answer, lang)
        answer = ensure_not_a_valuation(answer, lang)
    if "get_contact_options" in used_tools:
        answer, sent = drop_sent_claims(answer, lang)
    return answer, {"urls_removed": removed, "items_dropped": dropped, "contacts_scrubbed": scrubbed,
                    "verdicts_dropped": verdicts, "sent_claims_dropped": sent}
