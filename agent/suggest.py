"""The next questions offered under each answer, as buttons.

Built in code from the conversation's state — the card numbers on screen, the
cities and the budget of the current search — so a button always names a real
card and a real city, and always routes to the skill it advertises
(tests/test_suggest.py checks every template in every language through
skills.select). Each turn offers at most three, leading to what the user has
not just seen: after a search, the price check, a similar home in the other
city and the budget comparison; after a budget comparison, the next budget up.
"""
from __future__ import annotations

import unicodedata

MAX = 3

T = {
    "en": {"leaders": "Compare #{n} and #{m} feature by feature", "price": "Is #{n}'s price in line with similar homes?", "contact": "How do I contact the agent for #{n}?",
           "similar": "Show me homes like #{n} in {city}", "budget": "What does {p} buy in {a} vs {b}?",
           "more": "And up to {p}?", "areas": "Compare schools and public transport in {a} and {b}",
           "search": "Homes in {a} or {b} up to {p}"},
    "pt": {"leaders": "Compara a #{n} e a #{m} característica a característica", "price": "O preço do #{n} está em linha com casas semelhantes?", "contact": "Como contacto o agente do #{n}?",
           "similar": "Mostra casas parecidas com a #{n} em {city}", "budget": "O que se compra com {p} em {a} e {b}?",
           "more": "E até {p}?", "areas": "Compara escolas e transportes públicos em {a} e {b}",
           "search": "Casas em {a} ou {b} até {p}"},
    "es": {"leaders": "Compara la #{n} y la #{m} característica por característica", "price": "¿El precio del #{n} está en línea con viviendas similares?",
           "contact": "¿Cómo contacto con el agente del #{n}?",
           "similar": "Muéstrame viviendas parecidas a la #{n} en {city}", "budget": "¿Qué se compra con {p} en {a} y {b}?",
           "more": "¿Y hasta {p}?", "areas": "Compara colegios y transporte público en {a} y {b}",
           "search": "Viviendas en {a} o {b} hasta {p}"},
    "fr": {"leaders": "Compare le n°{n} et le n°{m} point par point", "price": "Le prix du n°{n} est-il cohérent avec des biens similaires ?",
           "contact": "Comment contacter l'agent du n°{n} ?",
           "similar": "Montre des biens semblables au n°{n} à {city}", "budget": "Que peut-on acheter avec {p} à {a} et {b} ?",
           "more": "Et jusqu'à {p} ?", "areas": "Compare les écoles et les transports en commun à {a} et {b}",
           "search": "Logements à {a} ou {b} jusqu'à {p}"},
    "de": {"leaders": "Vergleiche #{n} und #{m} Merkmal für Merkmal", "price": "Liegt der Preis von #{n} im Rahmen ähnlicher Objekte?", "contact": "Wie erreiche ich den Makler von #{n}?",
           "similar": "Zeig mir ähnliche Wohnungen wie #{n} in {city}", "budget": "Was bekommt man für {p} in {a} und {b}?",
           "more": "Und bis {p}?", "areas": "Vergleiche Schulen und öffentlichen Verkehr in {a} und {b}",
           "search": "Wohnungen in {a} oder {b} bis {p}"},
    "nl": {"leaders": "Vergelijk #{n} en #{m} kenmerk voor kenmerk", "price": "Ligt de prijs van #{n} in lijn met vergelijkbare woningen?", "contact": "Hoe bereik ik de makelaar van #{n}?",
           "similar": "Toon vergelijkbare woningen als #{n} in {city}", "budget": "Wat koop je voor {p} in {a} en {b}?",
           "more": "En tot {p}?", "areas": "Vergelijk scholen en openbaar vervoer in {a} en {b}",
           "search": "Woningen in {a} of {b} tot {p}"},
}

# Which kinds to offer after each skill, in order of preference.
AFTER = {
    "find-homes": ["leaders", "price", "budget", "similar", "areas"],
    "check-asking-price": ["similar", "contact", "areas"],
    "contact-agent": ["similar", "budget", "areas"],
    "compare-areas": ["budget", "search"],
    "compare-budget": ["more", "leaders", "areas"],
    "similar-elsewhere": ["price", "contact", "budget"],
}


def money(p: float, lang: str) -> str:
    n = f"{p:,.0f}"
    if lang == "en":
        return "€" + n
    if lang == "de":
        return n.replace(",", ".") + " €"
    return n.replace(",", " ") + " €"


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


ALIASES = {"lisbon": "lisboa", "lisbonne": "lisboa", "lissabon": "lisboa", "oporto": "porto",
           "valència": "valencia", "seville": "sevilla", "munich": "munchen"}


def _same_place(a: str, b: str) -> bool:
    fa, fb = _fold(a), _fold(b)
    return ALIASES.get(fa, fa) == ALIASES.get(fb, fb)


def other_city(card: dict | None, places: list[str]) -> str | None:
    """A searched place the card is not in — the city a "homes like this" goes to."""
    if not card or len(places) < 2:
        return None
    where = [p.strip() for p in (card.get("location") or "").split(",")]
    for place in places:
        if not any(_same_place(place, w) for w in where):
            return place
    return None


def leaders(shown: list[dict], places: list[str]) -> tuple[int, int] | None:
    """Card numbers of the first home on screen in each of the first two places."""
    if len(places) < 2:
        return None
    firsts = []
    for place in places[:2]:
        n = next((c["n"] for c in shown
                  if any(_same_place(place, w.strip()) for w in (c.get("location") or "").split(","))), None)
        if n is None:
            return None
        firsts.append(n)
    return (firsts[0], firsts[1]) if firsts[0] != firsts[1] else None


def _cross_country(shown: list[dict]) -> bool:
    """True when the cards on screen sit in more than one country."""
    countries = {_fold((c.get("location") or "").split(",")[-1].strip()) for c in shown if c.get("location")}
    return len(countries) > 1


def next_questions(skill: str, lang: str, *, places: list[str], max_price: float | None,
                   shown: list[dict], focus_n: int | None = None, budget_cap: float | None = None) -> list[str]:
    t = T.get(lang, T["en"])
    a, b = (places + [None, None])[:2]
    n = focus_n or (1 if shown else None)
    card = next((c for c in shown if c.get("n") == n), None) if n else None
    out: list[str] = []
    for kind in AFTER.get(skill, []):
        q = None
        if kind == "leaders":
            pair = leaders(shown, places)
            if pair:
                q = t["leaders"].format(n=pair[0], m=pair[1])
        elif kind in ("price", "contact") and n and shown:
            q = t[kind].format(n=n)
        elif kind == "similar" and card:
            city = other_city(card, places)
            if city:
                q = t["similar"].format(n=n, city=city)
        elif kind == "budget" and a and b and max_price and not _cross_country(shown):
            # Across countries the shares mostly measure which agencies Cubi
            # covers in each (Porto vs Valencia did, 2026-10-22): not offered.
            q = t["budget"].format(p=money(max_price, lang), a=a, b=b)
        elif kind == "more" and budget_cap:
            q = t["more"].format(p=money(budget_cap + 100_000, lang))
        elif kind == "areas" and a and b:
            q = t["areas"].format(a=a, b=b)
        elif kind == "search" and a and b and max_price:
            q = t["search"].format(a=a, b=b, p=money(max_price, lang))
        if q and q not in out:
            out.append(q)
        if len(out) == MAX:
            break
    return out
