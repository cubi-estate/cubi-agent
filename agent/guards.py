"""Deterministic post-checks on the model's answer. No model is trusted with these."""
from __future__ import annotations

import re

URL_RE = re.compile(r"https?://[^\s<>\"'\])]+")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")

_UNVERIFIED_NOTE = {
    "en": "A link that did not come from Cubi's results was removed.",
    "pt": "Foi removida uma ligação que não veio dos resultados da Cubi.",
    "es": "Se ha eliminado un enlace que no procedía de los resultados de Cubi.",
    "fr": "Un lien qui ne provenait pas des résultats de Cubi a été supprimé.",
    "de": "Ein Link, der nicht aus den Cubi-Ergebnissen stammt, wurde entfernt.",
    "nl": "Een link die niet uit de resultaten van Cubi kwam, is verwijderd.",
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


def verify_urls(answer: str, tool_text: str, lang: str = "en") -> tuple[str, list[str]]:
    """Strip every URL that does not appear verbatim in the tools' output."""
    removed: list[str] = []

    def repl(m: re.Match) -> str:
        url = _clean(m.group(0))
        if url in tool_text:
            return m.group(0)
        removed.append(url)
        return ""

    out = URL_RE.sub(repl, answer)
    # Markdown links whose target was stripped: [text]() → text
    out = re.sub(r"\[([^\]]+)\]\(\s*\)", r"\1", out)
    if removed:
        out = out.rstrip() + "\n\n_" + _UNVERIFIED_NOTE.get(lang, _UNVERIFIED_NOTE["en"]) + "_"
    return out, removed


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


def apply(answer: str, tool_text: str, lang: str, used_tools: set[str]) -> tuple[str, dict]:
    answer, removed = verify_urls(answer, tool_text, lang)
    answer, scrubbed = scrub_contacts(answer)
    if "compare_asking_prices" in used_tools:
        answer = ensure_not_a_valuation(answer, lang)
    return answer, {"urls_removed": removed, "contacts_scrubbed": scrubbed}
