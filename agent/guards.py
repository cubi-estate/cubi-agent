"""Deterministic post-checks on the model's answer. No model is trusted with these."""
from __future__ import annotations

import json
import re

from .suggest import money

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


def _drop_sentences(answer: str, pattern: re.Pattern, keep_questions: bool = False,
                    keep: re.Pattern | None = None) -> tuple[str, int]:
    """Remove matching sentences, line by line, keeping the answer's layout. `keep` exempts a sentence."""
    n, lines = 0, []
    for line in answer.split("\n"):
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [x for x in parts if not pattern.search(x) or (keep_questions and x.rstrip().endswith("?"))
                or (keep is not None and keep.search(x))]
        n += len(parts) - len(kept)
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), n


# "Is #1 a good deal? Just answer yes or no." → "No." is a verdict without the word.
_BARE_YES_NO = re.compile(r"^\W*(yes|no|sim|n[ãa]o|s[ií]|oui|non|ja|nein|nee)\W*$", re.I)


def drop_price_verdicts(answer: str, lang: str) -> tuple[str, int]:
    out, n = _drop_sentences(answer, _VERDICT, keep_questions=True)
    out, bare = _drop_sentences(out, _BARE_YES_NO)
    n += bare
    if not n:
        return answer, 0
    low = out.lower()
    if any(w in low for w in _VALUATION_WORDS.get(lang, ()) + _VALUATION_WORDS["en"]):
        return out, n   # already points to a valuation: the note would say it twice (rehearsal 2026-10-22)
    return (out + "\n\n" + _VERDICT_NOTE.get(lang, _VERDICT_NOTE["en"])).strip(), n


_BAND_LINE = {
    "en": "Comparable homes in {city} ask {low}–{high} (middle half of {n}); this one asks {price}.",
    "pt": "Casas comparáveis em {city} pedem {low}–{high} (metade central de {n}); esta pede {price}.",
    "es": "Viviendas comparables en {city} piden {low}–{high} (la mitad central de {n}); esta pide {price}.",
    "fr": "Des biens comparables à {city} demandent {low}–{high} (moitié centrale de {n}) ; celui-ci demande {price}.",
    "de": "Vergleichbare Objekte in {city} verlangen {low}–{high} (mittlere Hälfte von {n}); dieses verlangt {price}.",
    "nl": "Vergelijkbare woningen in {city} vragen {low}–{high} (middelste helft van {n}); deze vraagt {price}.",
}


def _comparison(tool_text: str) -> dict | None:
    """The last asking-price comparison in this turn's tool output."""
    i = tool_text.rfind('{"listing_id"')
    while i >= 0:
        try:
            body = json.JSONDecoder().raw_decode(tool_text[i:])[0]
        except json.JSONDecodeError:
            body = None
        if isinstance(body, dict) and body.get("kind") == "asking_price_comparison":
            return body
        i = tool_text.rfind('{"listing_id"', 0, i)
    return None


def ensure_band_stated(answer: str, tool_text: str, lang: str) -> tuple[str, int]:
    """A price answer without a single figure lost the range (a one-word verdict was
    dropped and nothing was left): state it from Cubi's numbers."""
    body = _comparison(tool_text)
    band = (body or {}).get("band") or {}
    if re.search(r"\d", answer) or not band.get("low") or not band.get("high") or body.get("currency") != "EUR":
        return answer, 0
    line = _BAND_LINE.get(lang, _BAND_LINE["en"]).format(
        city=body.get("city") or "the same city", n=body.get("n_comps") or "?",
        low=money(band["low"], lang), high=money(band["high"], lang),
        price=money(body["asking_price"], lang) if body.get("asking_price") else "?")
    return (line + "\n\n" + answer).strip(), 1


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


# "There is no similar home in Porto" is about the search, not a home, and is
# the honest opening of a no-match answer: dropping it left replies starting
# "Therefore, …" (tester F3). Kept when the absent thing is homes/matches.
_NO_MATCH = re.compile(
    r"\b(?:no|zero|nenhu\w*|ningu\w*|aucun\w*|kein\w*|geen)\s+(?:[\w-]+\s+){0,2}"
    r"(?:homes?|match(?:es)?|listings?|propert(?:y|ies)|results?|alternatives?|comparables|options?|"
    r"im[óo]ve(?:l|is)|casas?|viviendas?|pisos?|inmuebles?|resultados?|logements?|biens?|r[ée]sultats?|"
    r"treffer|wohnungen|immobilien|ergebniss?e?|woningen|resultaten|objecten)\b|"
    # "their listings lack enough data to compare": a gap in Cubi's data, not the home (tester F2)
    r"\b(?:lack\w*|enough|sufficient)\b.{0,40}\b(?:data|details|information|readings)\b", re.I)


def fix_absence_wording(answer: str) -> tuple[str, int]:
    """Reword "absent from the listing", drop "the home lacks …". Returns (answer, changes)."""
    answer, reworded = _ABSENT_FROM.subn("not mentioned in", answer)
    answer, dropped = _drop_sentences(answer, _ABSENCE_CLAIM, keep=_NO_MATCH)
    return answer, reworded + dropped


# "since 15 September 15, 2026": handed "15 September 2026", the model once mixed in
# the US form on a filmed price-history line (tester F12). The same day on both sides
# of the month name is that garble, never a range ("15 to 20 September" has no repeat).
_DOUBLED_DAY = re.compile(r"\b(\d{1,2})(\.?\s+(?:de\s+)?)([^\W\d_]{3,})\s+\1(?:st|nd|rd|th)?,?\s+((?:de\s+)?\d{4})\b")


def fix_doubled_dates(answer: str) -> tuple[str, int]:
    def one(m: re.Match) -> str:
        year = m.group(4)
        if "de" in m.group(2) and not year.startswith("de"):
            year = "de " + year    # "15 de setembro de 2026"
        return f"{m.group(1)}{m.group(2)}{m.group(3)} {year}"
    return _DOUBLED_DAY.subn(one, answer)


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


# "#2 (afinest_pt:25505032)": a listing id is plumbing, not something a buyer can use,
# and a judge read it as a leak (2026-10-25). Ids are "<source>:<code>"; the lookbehind
# keeps "https://" and paths out. A card on screen becomes its number, any other id
# "this home"; "or the exact listing ID" offers the user something they can't see.
_ID = r"(?<![\w/.:@])[a-z][a-z0-9_]{2,}:[A-Za-z0-9][\w.-]{3,}"
_ID_PAREN = re.compile(rf"\s*\(\s*(?:listing\s+)?(?:id\s*:?\s*)?{_ID}\s*\)", re.I)
_ID_BARE = re.compile(rf"(?:\blisting\s+)?(?:\bid\s*:?\s*)?({_ID})", re.I)
_ID_OFFER = re.compile(r",?\s+or\s+(?:the\s+)?(?:exact\s+)?(?:listing\s+)?id\b", re.I)


def scrub_ids(answer: str, cards: list[str] = ()) -> tuple[str, int]:
    n = len(re.findall(_ID, answer)) + len(_ID_OFFER.findall(answer))
    if not n:
        return answer, 0
    out = _ID_PAREN.sub("", answer)
    out = _ID_BARE.sub(lambda m: f"#{cards.index(m.group(1)) + 1}" if m.group(1) in cards else "this home", out)
    return _ID_OFFER.sub("", out), n


# "All include a private pool": a wish ranks the results, it doesn't filter them, so a
# claim about every home is unchecked (live 2026-10-24, three of twelve wizard searches).
_ALL = (r"\b(all|every|each of|both|todos|todas|tous|toutes|alle|allemaal|ambos|ambas|cada)\b")
_WISH = (r"(pool|piscina|piscine|schwimmbad|zwembad|sea[- ]view|views?|vista|vue|blick|uitzicht|terrace|terra[çc]|"
         r"terrasse|terras|balcon|balc[oó]n|balkon|lift|elevator|elevador|ascensor|ascenseur|aufzug|garden|jardim|"
         r"jard[ií]n|garten|tuin|garage|garagem|parking|parque|stellplatz|parkeer|air[- ]condition|\bac\b|"
         r"ar condicionado|aire acondicionado|climati|klima|airco|sauna|fireplace|lareira|chimenea|chemin[ée]e|"
         r"kamin|open haard|renovat|reformad|r[ée]nov|saniert|furnish\w*|mobilad|amueblad|meubl|m[öo]bliert|gemeubileerd|"
         # Setting and size wishes ("…ideally with a large plot, in quiet countryside"):
         # "showing six examples—all include notes about tranquil settings and
         # good-sized parcels" (live 2026-10-27) was a claim nothing checked.
         r"quiet|tranquil\w*|peaceful|secluded|countryside|sossegad\w*|calme|ruhig\w*|rustig\w*|"
         r"good[- ]sized|spacious|large plots?|big plots?|parcels?)")
_ALL_WISH = re.compile(_ALL + r"[^.!?]{0,80}" + _WISH + r"|" + _WISH + r"[^.!?]{0,40}\b(in all|for all|em todos|en todos|"
                       r"dans tous|bei allen|bij alle)\b", re.I)


# "I found five flats in Lisbon—all in Beato and needing renovation": the claim is
# a clause; dropping the sentence lost the count with it, and a pivoted answer
# opened mid-thought ("Wszystkie są…", tester F25 runs, 27 Oct).
_CLAUSE_CUT = re.compile(r"\s*(?:[—–;:]|,|\s-\s)\s*(?=" + _ALL + r")", re.I)


def drop_all_have_claims(answer: str) -> tuple[str, int]:
    n, lines = 0, []
    for line in answer.split("\n"):
        kept = []
        for x in re.split(r"(?<=[.!?])\s+", line):
            m = _ALL_WISH.search(x)
            if not m:
                kept.append(x)
                continue
            n += 1
            cuts = [c for c in _CLAUSE_CUT.finditer(x) if 20 <= c.start() <= m.start()]
            if cuts and not _ALL_WISH.search(x[:cuts[-1].start()]):
                kept.append(x[:cuts[-1].start()].rstrip(" ,;:—–-") + ".")
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), n


# "Many exceed the budget … #2 … though above the limit": the model compared złoty
# prices with a euro budget (live 2026-10-25: cap 1,757,800 PLN, every card under
# it, #2 at 999,999 PLN called over the limit). Cubi states the cap in the cards'
# currency; when every priced card is within it, an over-budget sentence is false.
_CAP = re.compile(r"budget up to ([\d][\d,.\u202f ]*?)\s*([A-Z]{3})\b")
_OVER_BUDGET = re.compile(
    r"\b(exceed\w*|above|over|beyond|outside|higher than|more than|past)\s+(the |your |that |this )?"
    r"(stated |price |budget |set )?(budget|limit|cap|ceiling|maximum|max)\b|\bover budget\b|"
    r"\b(acima|al[ée]m) do (or[çc]amento|limite)\b|\b(supera\w*|por encima d)el? (presupuesto|l[ií]mite)\b|"
    r"\b(au-dessus|au-del[àa]) (du|de la) (budget|limite)\b|\b[üu]ber (dem|das) (budget|limit)\b|"
    r"\bboven (het|de) (budget|limiet)\b", re.I)


def drop_false_over_budget(answer: str, tool_text: str) -> tuple[str, int]:
    caps = _CAP.findall(tool_text)
    if not caps:
        return answer, 0
    amount, currency = caps[-1]
    try:
        cap = float(re.sub(r"[^\d.]", "", amount.replace(",", "")))
    except ValueError:
        return answer, 0
    from agent import listings  # listings imports no guards; imported here to keep the module light
    prices = [(c.get("price"), (c.get("price_text") or "").upper()) for c in listings.parse(tool_text)]
    priced = [p for p, txt in prices if p is not None and currency in txt]
    if not priced or any(p > cap for p in priced):
        return answer, 0
    return _drop_sentences(answer, _OVER_BUDGET)


_THINK_BLOCK = re.compile(r"(?s)<think>.*?(?:</think>|$)")


# A home in a list item: a price, a size or a bedroom count. The cards below the
# answer already show each home; the model sometimes lists all six again (the
# Lyon "for sale" button, tester F22; the injection turn, F8).
_HOME_FACT = re.compile(r"[€$£]\s?\d|\d\s?(?:€|eur\b|euros?\b|chf\b|pln\b|z[łl]|kr\b)|\d\s?m[²2]|"
                        r"\b\d+\s?(?:bd|bed\w*|quartos?|dormitorios?|chambres?|schlafzimmer|slaapkamers?|"
                        r"camere|sypialni\w*|soverom|спал\w*)\b|\bT\d\b", re.I)
MIN_LISTED = 3


def drop_listed_homes(answer: str) -> tuple[str, int]:
    """Drop a list of three or more homes, and the line that leads into it
    ("Here are the six homes:"). Kept whole if nothing else would be left."""
    blocks = _items(answer)
    homes = [i for i, b in enumerate(blocks) if ITEM_RE.match(b[0]) and _HOME_FACT.search(" ".join(b))]
    if len(homes) < MIN_LISTED:
        return answer, 0
    drop = set(homes)
    for i in homes:  # the lead-in, past blank lines
        j = i - 1
        while j >= 0 and not blocks[j][0].strip():
            j -= 1
        if j >= 0 and j not in drop and blocks[j][0].rstrip().endswith(":"):
            # "I found 6 homes. Here they are:": only the last sentence leads in
            head = re.split(r"(?<=[.!?])\s+(?=\S[^.!?]*:\s*$)", blocks[j][0].rstrip(), maxsplit=1)
            if len(head) == 2:
                blocks[j] = [head[0]]
            else:
                drop.add(j)
    kept = "\n".join(line for i, b in enumerate(blocks) if i not in drop for line in b)
    kept = re.sub(r"\n{3,}", "\n\n", kept).strip()
    if len(re.sub(r"\W", "", kept)) < 20:
        return answer, 0
    return kept, len(homes)


def strip_reasoning(answer: str) -> tuple[str, int]:
    """The model's notes must never reach the user. With thinking off it still
    wrote them, ending in a bare "</think>" before the real answer (live, 'Is #9
    overpriced?' with six cards)."""
    out = _THINK_BLOCK.sub("", answer)
    if "</think>" in out:
        out = out.rsplit("</think>", 1)[1]
    out = out.strip()
    return out, int(out != answer.strip())


# "I ran a free-text search … using the search_properties tool, but no listings
# were found" (2026-10-27): a tool name is plumbing, not something a buyer can use.
_TOOLS = (r"search_properties|filter_listings|find_similar_elsewhere|compare_asking_prices|get_listing|"
          r"get_contact_options|get_price_history|compare_inventory|search_homes|home_news|research_area")
_TOOL_PHRASE = re.compile(rf"\s*,?\s*\b(?:using|with|via|through|by calling|by using)\s+(?:the\s+|Cubi's\s+)?`?(?:{_TOOLS})`?"
                          rf"(?:\s+(?:tool|function|endpoint))?\b", re.I)
_TOOL_BARE = re.compile(rf"(?:the\s+)?`?\b(?:{_TOOLS})\b`?(?:\s+(?:tool|function|endpoint))?", re.I)


def scrub_tool_names(answer: str) -> tuple[str, int]:
    out, n1 = _TOOL_PHRASE.subn("", answer)
    out, n2 = _TOOL_BARE.subn("Cubi's search", out)
    return out, n1 + n2


def apply(answer: str, tool_text: str, lang: str, used_tools: set[str],
          cards: list[str] = ()) -> tuple[str, dict]:
    answer, reasoning = strip_reasoning(answer)
    answer = _STRAY_HASH.sub(r"\1", answer)
    answer, ids = scrub_ids(answer, list(cards))
    answer, tools = scrub_tool_names(answer)
    answer, removed, dropped = verify_urls(answer, tool_text, lang)
    answer, scrubbed = scrub_contacts(answer)
    verdicts = sent = band_added = 0
    if "compare_asking_prices" in used_tools:
        answer, verdicts = drop_price_verdicts(answer, lang)
        answer, thin = drop_thin_hedge(answer, tool_text)
        verdicts += thin
        answer, band_added = ensure_band_stated(answer, tool_text, lang)
        if "asking_price_comparison" in tool_text:  # not under "which card do you mean?"
            answer = ensure_not_a_valuation(answer, lang)
    if "get_contact_options" in used_tools:
        answer, sent = drop_sent_claims(answer, lang)
    wishes = over = 0
    listed = 0
    if "search_homes" in used_tools:
        answer, listed = drop_listed_homes(answer)
        answer, wishes = drop_all_have_claims(answer)
        answer, over = drop_false_over_budget(answer, tool_text)
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
    dates = 0
    if "home_news" in used_tools:
        answer, v = drop_price_verdicts(answer, lang)   # "a bargain after the cut"
        verdicts += v
        answer, dates = fix_doubled_dates(answer)
    if "compare_inventory" in used_tools or "home_news" in used_tools:
        answer, pct = drop_unbacked_percentages(answer, tool_text)
    return answer, {"urls_removed": removed, "items_dropped": dropped, "contacts_scrubbed": scrubbed,
                    "verdicts_dropped": verdicts, "sent_claims_dropped": sent, "percentages_dropped": pct,
                    "absence_wording_fixed": absence, "source_filler_dropped": filler,
                    "all_have_claims_dropped": wishes, "over_budget_dropped": over, "reasoning_stripped": reasoning, "ids_scrubbed": ids,
                    "band_stated": band_added, "dates_fixed": dates, "tool_names_scrubbed": tools, "listed_homes_dropped": listed}
