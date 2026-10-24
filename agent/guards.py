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
    low = out.lower()
    if any(w in low for w in _VALUATION_WORDS.get(lang, ()) + _VALUATION_WORDS["en"]):
        return out, n   # already points to a valuation: the note would say it twice (rehearsal 2026-10-22)
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


PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")
# Figures derived from two shares: a ratio or a difference in points. Never in
# the tool output, so any of them is the model's own arithmetic.
DERIVED_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:x|×|times|fold|vezes|veces|mal|fois|keer)\b|"
                        r"percentage points?|pontos percentuais|puntos porcentuales|prozentpunkte|"
                        r"points de pourcentage|procentpunten", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=\S)")


def _pct_key(x: str) -> str:
    v = float(x.replace(",", "."))
    return f"{v:g}"


def drop_unbacked_percentages(answer: str, tool_text: str) -> tuple[str, int]:
    """Drop every sentence carrying a percentage the tool output doesn't give.

    The budget comparison's figures are the point of the answer, so a share the
    model worked out itself ("Porto's share is 3x Lisbon's", "21 points higher")
    reads as Cubi's number. Differences and ratios ("3.4 times", "21 points")
    are left out by the skill; this catches the ones that slip through."""
    allowed = {_pct_key(m) for m in PCT_RE.findall(tool_text)}
    dropped = 0
    out_lines = []
    for line in answer.split("\n"):
        kept = []
        for sent in _SENTENCE_END.split(line):
            if DERIVED_RE.search(sent) or any(_pct_key(m) not in allowed for m in PCT_RE.findall(sent)):
                dropped += 1
                continue
            kept.append(sent)
        if kept or not line.strip():
            out_lines.append(" ".join(kept))
    return "\n".join(out_lines).strip(), dropped


# "a saving of €40k", "a Lisbon premium": a difference in asking prices is
# neither (find_similar_elsewhere).
_SAVING = re.compile(r"\b(sav(e|es|ing|ings)|premium|poupa|poupan[çc]a|ahorr|[ée]conomi|spar(en|st|t)\b|ersparnis|"
                     r"bespa(ar|ring)|aufpreis|surco[uû]t|sobreprecio|sobrecusto)", re.I)


# find_similar_elsewhere reports a feature as "stated" or "not stated": a
# listing that doesn't mention parking says nothing about whether the flat has
# it. "absent from"/"missing from the listing" is true of the listing but reads
# as the flat lacking it (live 2026-10-22), so it is reworded; a sentence that
# says the home lacks something is dropped. "does not mention" stays.
_ABSENT_FROM = re.compile(r"\b(absent|missing) from\b", re.I)
_ABSENCE_CLAIM = re.compile(
    r"\b(lacks?|lacking|does(?:n't| not) (?:have|include|offer|come with)|(?:has|have) no|there is no|"
    r"comes? without|without (?:a |an )?(?:balcony|terrace|lift|elevator|parking|garage|garden|pool|air)|"
    r"n[ãa]o (?:tem|possui|disp[õo]e)|sem (?:varanda|terra[çc]o|elevador|estacionamento|garagem|jardim|piscina)|"
    r"no (?:tiene|dispone|cuenta con)|carece|sin (?:balc[óo]n|terraza|ascensor|garaje|parking|jard[íi]n|piscina)|"
    r"hat (?:kein|keine)|verf[üu]gt (?:nicht|über kein)|ohne (?:balkon|terrasse|aufzug|stellplatz|garage|garten|pool)|"
    r"n'a pas|ne (?:dispose|poss[èe]de) pas|sans (?:balcon|terrasse|ascenseur|parking|garage|jardin|piscine)|"
    r"heeft geen|beschikt niet|zonder (?:balkon|terras|lift|parkeer|garage|tuin|zwembad))", re.I)


def fix_absence_wording(answer: str) -> tuple[str, int]:
    """Reword "absent from the listing", drop "the home lacks …". Returns (answer, changes)."""
    answer, reworded = _ABSENT_FROM.subn("not mentioned in", answer)
    answer, dropped = _drop_sentences(answer, _ABSENCE_CLAIM)
    return answer, reworded + dropped


# Area research: "No source indicated a lack of school information" — filler about
# a gap there isn't (rehearsal 2026-10-22). "No source covered healthcare in
# Porto" is a real gap and stays: only sources reporting a lack/missing go.
_NO_SOURCE_FILLER = re.compile(
    r"\b(?:no|neither|none of the)(?: \w+){0,2} sources?\b.{0,60}\b(?:lack|missing|absence|gap)|"
    r"\bnenhuma (?:das )?fontes?\b.{0,60}\b(?:falta|aus[êe]ncia|lacuna)|"
    r"\bninguna (?:de las )?fuentes?\b.{0,60}\b(?:falta|ausencia|carencia)|"
    r"\baucune (?:des )?sources?\b.{0,60}\b(?:manque|absence|lacune)|"
    r"\bkeine (?:der )?quellen?\b.{0,60}(?:fehlend|mangel|l[üu]cke)|"
    r"\bgeen (?:van de )?bron(?:nen)?\b.{0,60}(?:gebrek|ontbre)", re.I)

# Price band: "given the modest number of comparables, the comparison is thin"
# said of 19 comparables (rehearsal 2026-10-22). Dropped when the band rests on
# at least AMPLE_COMPS.
AMPLE_COMPS = 10
_THIN_HEDGE = re.compile(
    r"\b(?:thin|modest number|few comparables|limited number of comparables|small number of comparables)\b|"
    r"\b(?:poucos|pocos|peu de|wenige|weinig) (?:compar|vergleich|vergelijk)|\bd[üu]nn\b|\bescass", re.I)


def drop_thin_hedge(answer: str, tool_text: str) -> tuple[str, int]:
    m = re.search(r'"n_comps":\s*(\d+)', tool_text)
    if not m or int(m.group(1)) < AMPLE_COMPS or '"band": null' in tool_text:
        return answer, 0
    return _drop_sentences(answer, _THIN_HEDGE)


# "#Lisbon home #2": the model copies "the Lisbon home (#2)" and keeps the "#".
# Card references are "#" + digits, so a "#" glued to a capitalised word goes.
_STRAY_HASH = re.compile(r"(^|[\s(])#(?=[A-ZÀ-Ý][a-zà-ÿ])")


# "All include a private pool": a wish ranks the results, it doesn't filter them, so a
# claim about every home is unchecked (live 2026-10-24, three of twelve wizard searches).
_ALL = (r"\b(all|every|each of|both|todos|todas|tous|toutes|alle|allemaal|ambos|ambas|cada)\b")
_WISH = (r"(pool|piscina|piscine|schwimmbad|zwembad|sea[- ]view|views?|vista|vue|blick|uitzicht|terrace|terra[çc]|"
         r"terrasse|terras|balcon|balc[oó]n|balkon|lift|elevator|elevador|ascensor|ascenseur|aufzug|garden|jardim|"
         r"jard[ií]n|garten|tuin|garage|garagem|parking|parque|stellplatz|parkeer|air[- ]condition|\bac\b|"
         r"ar condicionado|aire acondicionado|climati|klima|airco|sauna|fireplace|lareira|chimenea|chemin[ée]e|"
         r"kamin|open haard|renovat|reformad|r[ée]nov|saniert|furnished|mobilad|amueblad|meubl|m[öo]bliert|gemeubileerd)")
_ALL_WISH = re.compile(_ALL + r"[^.!?]{0,80}" + _WISH + r"|" + _WISH + r"[^.!?]{0,40}\b(in all|for all|em todos|en todos|"
                       r"dans tous|bei allen|bij alle)\b", re.I)


def drop_all_have_claims(answer: str) -> tuple[str, int]:
    return _drop_sentences(answer, _ALL_WISH)


def apply(answer: str, tool_text: str, lang: str, used_tools: set[str]) -> tuple[str, dict]:
    answer = _STRAY_HASH.sub(r"\1", answer)
    answer, removed, dropped = verify_urls(answer, tool_text, lang)
    answer, scrubbed = scrub_contacts(answer)
    verdicts = sent = 0
    if "compare_asking_prices" in used_tools:
        answer, verdicts = drop_price_verdicts(answer, lang)
        answer, thin = drop_thin_hedge(answer, tool_text)
        verdicts += thin
        answer = ensure_not_a_valuation(answer, lang)
    if "get_contact_options" in used_tools:
        answer, sent = drop_sent_claims(answer, lang)
    wishes = 0
    if "search_homes" in used_tools:
        answer, wishes = drop_all_have_claims(answer)
    absence = 0
    if "find_similar_elsewhere" in used_tools:
        answer, v1 = drop_price_verdicts(answer, lang)
        answer, v2 = _drop_sentences(answer, _SAVING)
        verdicts += v1 + v2
        answer, absence = fix_absence_wording(answer)
    filler = 0
    if "research_area" in used_tools:
        answer, filler = _drop_sentences(answer, _NO_SOURCE_FILLER)
    pct = 0
    if "home_news" in used_tools:
        answer, v = drop_price_verdicts(answer, lang)   # "a bargain after the cut"
        verdicts += v
    if "compare_inventory" in used_tools or "home_news" in used_tools:
        answer, pct = drop_unbacked_percentages(answer, tool_text)
    return answer, {"urls_removed": removed, "items_dropped": dropped, "contacts_scrubbed": scrubbed,
                    "verdicts_dropped": verdicts, "sent_claims_dropped": sent, "percentages_dropped": pct,
                    "absence_wording_fixed": absence, "source_filler_dropped": filler,
                    "all_have_claims_dropped": wishes}
