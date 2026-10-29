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

import re
import unicodedata

MAX = 3

T = {
    "en": {"forsale": "Homes for sale in {a}", "news": "Has #{n}'s price dropped, and what's new in {city}?", "leaders": "Compare #{n} and #{m} feature by feature", "price": "Is #{n}'s price in line with similar homes?", "contact": "How do I contact the agent for #{n}?",
           "similar": "Show me homes like #{n} in {city}", "budget": "What does {p} buy in {a} vs {b}?",
           "more": "And up to {p}?", "areas": "Compare schools and public transport in {a} and {b}",
           "search": "Homes in {a} or {b} up to {p}",
           "simpair": "Compare #{n} with its similar homes feature by feature", "drops": "Has #{n}'s price dropped, and have its similar homes' prices dropped?", "placenews": "What's new in {city}?"},
    "pt": {"forsale": "Casas à venda em {a}", "news": "O preço da #{n} baixou, e que novidades há em {city}?", "leaders": "Compara a #{n} e a #{m} característica a característica", "price": "O preço do #{n} está em linha com casas semelhantes?", "contact": "Como contacto o agente do #{n}?",
           "similar": "Mostra casas parecidas com a #{n} em {city}", "budget": "O que se compra com {p} em {a} e {b}?",
           "more": "E até {p}?", "areas": "Compara escolas e transportes públicos em {a} e {b}",
           "search": "Casas em {a} ou {b} até {p}",
           "simpair": "Compara a #{n} com as casas semelhantes característica a característica", "drops": "O preço da #{n} baixou, e o das casas semelhantes?", "placenews": "Que novidades há em {city}?"},
    "es": {"forsale": "Viviendas en venta en {a}", "news": "¿Ha bajado el precio de la #{n} y qué hay de nuevo en {city}?", "leaders": "Compara la #{n} y la #{m} característica por característica", "price": "¿El precio del #{n} está en línea con viviendas similares?",
           "contact": "¿Cómo contacto con el agente del #{n}?",
           "similar": "Muéstrame viviendas parecidas a la #{n} en {city}", "budget": "¿Qué se compra con {p} en {a} y {b}?",
           "more": "¿Y hasta {p}?", "areas": "Compara colegios y transporte público en {a} y {b}",
           "search": "Viviendas en {a} o {b} hasta {p}",
           "simpair": "Compara la #{n} con las viviendas similares característica por característica", "drops": "¿Ha bajado el precio de la #{n}, y el de las viviendas similares?", "placenews": "¿Qué hay de nuevo en {city}?"},
    "fr": {"forsale": "Logements à vendre à {a}", "news": "Le prix du n°{n} a-t-il baissé, et quoi de neuf à {city} ?", "leaders": "Compare le n°{n} et le n°{m} point par point", "price": "Le prix du n°{n} est-il cohérent avec des biens similaires ?",
           "contact": "Comment contacter l'agent du n°{n} ?",
           "similar": "Montre des biens semblables au n°{n} à {city}", "budget": "Que peut-on acheter avec {p} à {a} et {b} ?",
           "more": "Et jusqu'à {p} ?", "areas": "Compare les écoles et les transports en commun à {a} et {b}",
           "search": "Logements à {a} ou {b} jusqu'à {p}",
           "simpair": "Compare le n°{n} avec les biens semblables point par point", "drops": "Le prix du n°{n} a-t-il baissé, et celui des biens semblables ?", "placenews": "Quoi de neuf à {city} ?"},
    "de": {"forsale": "Wohnungen und Häuser zum Kauf in {a}", "news": "Ist der Preis von #{n} gesunken, und was gibt es Neues in {city}?", "leaders": "Vergleiche #{n} und #{m} Merkmal für Merkmal", "price": "Liegt der Preis von #{n} im Rahmen ähnlicher Objekte?", "contact": "Wie erreiche ich den Makler von #{n}?",
           "similar": "Zeig mir ähnliche Wohnungen wie #{n} in {city}", "budget": "Was bekommt man für {p} in {a} und {b}?",
           "more": "Und bis {p}?", "areas": "Vergleiche Schulen und öffentlichen Verkehr in {a} und {b}",
           "search": "Wohnungen in {a} oder {b} bis {p}",
           "simpair": "Vergleiche #{n} mit den ähnlichen Objekten Merkmal für Merkmal", "drops": "Ist der Preis von #{n} gesunken, und der der ähnlichen Objekte?", "placenews": "Was gibt es Neues in {city}?"},
    "nl": {"forsale": "Woningen te koop in {a}", "news": "Is de prijs van #{n} gedaald, en wat is er nieuw in {city}?", "leaders": "Vergelijk #{n} en #{m} kenmerk voor kenmerk", "price": "Ligt de prijs van #{n} in lijn met vergelijkbare woningen?", "contact": "Hoe bereik ik de makelaar van #{n}?",
           "similar": "Toon vergelijkbare woningen als #{n} in {city}", "budget": "Wat koop je voor {p} in {a} en {b}?",
           "more": "En tot {p}?", "areas": "Vergelijk scholen en openbaar vervoer in {a} en {b}",
           "search": "Woningen in {a} of {b} tot {p}",
           "simpair": "Vergelijk #{n} met de vergelijkbare woningen kenmerk voor kenmerk", "drops": "Is de prijs van #{n} gedaald, en die van de vergelijkbare woningen?", "placenews": "Wat is er nieuw in {city}?"},
}

# Which kinds to offer after each skill, in order of preference.
AFTER = {
    "find-homes": ["leaders", "news", "price", "budget", "similar", "areas", "contact"],
    "check-asking-price": ["news", "similar", "contact", "leaders", "areas", "budget"],
    "contact-agent": ["similar", "budget", "areas", "news", "leaders", "price"],
    "home-news": ["similar", "contact", "price", "leaders", "budget", "areas"],
    "compare-areas": ["budget", "search", "leaders", "news", "price", "similar"],
    "compare-budget": ["more", "leaders", "areas", "news", "similar"],
    "similar-elsewhere": ["news", "price", "contact", "budget", "areas"],
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
           "valència": "valencia", "seville": "sevilla", "munich": "munchen", "warsaw": "warszawa",
           "athens": "athina", "vienna": "wien", "milan": "milano", "rome": "roma", "cracow": "krakow"}

# Where "homes like this one" goes after a one-city search: the country's other big
# markets, the first that isn't the card's own city (Lisbon → Porto, Marbella → Madrid).
BIG_CITIES = {"portugal": ["Lisboa", "Porto", "Faro"], "spain": ["Madrid", "Barcelona", "Valencia", "Málaga"],
              "espana": ["Madrid", "Barcelona", "Valencia", "Málaga"], "italy": ["Milano", "Roma", "Torino"],
              "italia": ["Milano", "Roma", "Torino"], "germany": ["Berlin", "München", "Hamburg"],
              "deutschland": ["Berlin", "München", "Hamburg"], "france": ["Paris", "Lyon", "Marseille"],
              "netherlands": ["Amsterdam", "Rotterdam", "Utrecht"], "nederland": ["Amsterdam", "Rotterdam", "Utrecht"],
              "poland": ["Warszawa", "Kraków", "Gdańsk"], "polska": ["Warszawa", "Kraków", "Gdańsk"],
              "greece": ["Athina", "Thessaloniki"], "bulgaria": ["Sofia", "Varna"], "austria": ["Wien", "Graz"],
              "croatia": ["Zagreb", "Split"], "belgium": ["Brussel", "Antwerpen"]}


_COUNTRIES = {"portugal", "spain", "espana", "france", "germany", "deutschland", "italy", "italia",
              "netherlands", "nederland", "belgium", "greece", "croatia", "poland", "austria"}


def english_city(name: str) -> str:
    """One spelling per city for keys: "Lisbon"/"Lisboa" are the same search."""
    f = _fold(name)
    return ALIASES.get(f, f)


def _same_place(a: str, b: str) -> bool:
    fa, fb = _fold(a), _fold(b)
    return ALIASES.get(fa, fa) == ALIASES.get(fb, fb)


def other_city(card: dict | None, places: list[str]) -> str | None:
    """A searched place the card is not in — the city a "homes like this" goes to."""
    if not card:
        return None
    where = [p.strip() for p in (card.get("location") or "").split(",")]
    if len(places) >= 2:
        for place in places:
            if not any(_same_place(place, w) for w in where):
                return place
        return None
    for city in BIG_CITIES.get(country_of(card), []):
        if not any(_same_place(city, w) for w in where):
            return city
    return None


def country_of(card: dict) -> str:
    """The country of a card, folded: the last place name that is a country, else the
    last name ("Italy, Lombardy, Gittana" puts the country first, live 2026-10-26)."""
    from . import normalize
    parts = [w.strip() for w in (card.get("location") or "").split(",") if w.strip()]
    for w in reversed(parts):
        if normalize.is_country(w):
            return _fold(w)
    return _fold(parts[-1]) if parts else ""


def across(shown: list[dict]) -> tuple[int, int] | None:
    """After a Europe-wide search: the first home and the first one in another country."""
    first = next((c for c in shown if c.get("location") and c.get("n")), None)
    if not first:
        return None
    other = next((c for c in shown if c.get("location") and c.get("n")
                  and country_of(c) != country_of(first)), None)
    return (first["n"], other["n"]) if other else None


def leaders(shown: list[dict], places: list[str]) -> tuple[int, int] | None:
    """Card numbers of the first home on screen in each of the first two places;
    with fewer than two places searched, the first two homes in different countries."""
    if len(places) < 2:
        return across(shown)
    firsts = []
    for place in places[:2]:
        n = next((c["n"] for c in shown
                  if any(_same_place(place, w.strip()) for w in (c.get("location") or "").split(","))), None)
        if n is None:
            return None
        firsts.append(n)
    return (firsts[0], firsts[1]) if firsts[0] != firsts[1] else None


def news_place(card: dict, places: list[str]) -> str | None:
    """The place a home's news is about: the searched city the card is in, else the
    card's first place name. Used by the button and by the news search alike, so
    they never disagree. ("what's new in Modivas?" — a parish of Vila do Conde,
    the first name on a Porto-search card — would find no news; live 2026-10-22.)"""
    parts = [w.strip() for w in (card.get("location") or "").split(",") if w.strip()]
    for place in places:
        # "Lyon 8th Arrondissement" is in Lyon (a button said "what's new in
        # Auvergne-Rhône-Alpes?", live 2026-10-22).
        if any(_same_place(place, w) or _fold(w).startswith(_fold(place) + " ") for w in parts):
            return place
    last_digit = max((i for i, w in enumerate(parts) if re.search(r"\d", w)), default=-1)
    names = [w for w in parts[last_digit + 1:] if _fold(w) not in _COUNTRIES and "district" not in w.lower()]
    return names[0] if names else None


def _cross_country(shown: list[dict]) -> bool:
    """True when the cards on screen sit in more than one country."""
    return len({country_of(c) for c in shown if c.get("location")}) > 1


def for_sale(lang: str, place: str) -> str:
    """After a rental search found nothing because Cubi has no rentals there."""
    return T.get(lang, T["en"])["forsale"].format(a=place)


def norm(text: str) -> str:
    """Question text as compared for "already asked": case, accents and punctuation folded."""
    return re.sub(r"[^a-z0-9#]+", " ", _fold(text)).strip()


def key(kind: str, card_id: str | None = None, other: str | None = None) -> str:
    """What a question does, independent of wording or card number — the agent
    records the same keys for what it actually did (agent/loop.py)."""
    return ":".join(x for x in (kind, card_id or "", _fold(other or "")) if x)


def next_questions(skill: str, lang: str, *, places: list[str], max_price: float | None,
                   shown: list[dict], focus_n: int | None = None, budget_cap: float | None = None,
                   done: set[str] | None = None) -> list[str]:
    """Up to MAX next questions. `done` holds what this conversation already did
    (keys from key()) and asked (norm() of each message): neither is offered again
    — after a price check on #1 the buttons offered news and contact for #1 that
    had already been asked (live 2026-10-22)."""
    done = done or set()
    t = T.get(lang, T["en"])
    ids = {c.get("n"): c.get("id") for c in shown}
    a, b = (places + [None, None])[:2]
    n = focus_n or (1 if shown else None)
    card = next((c for c in shown if c.get("n") == n), None) if n else None
    out: list[str] = []
    for kind in AFTER.get(skill, []):
        q, k = None, None
        if kind == "leaders":
            pair = leaders(shown, places)
            if pair:
                q = t["leaders"].format(n=pair[0], m=pair[1])
                k = key("pair", "+".join(sorted(str(ids.get(x)) for x in pair)))
        elif kind == "news" and card:
            town = news_place(card, places)
            if town:
                q = t["news"].format(n=n, city=town)
                k = key("news", ids.get(n))
        elif kind in ("price", "contact") and n and shown:
            q = t[kind].format(n=n)
            k = key(kind, ids.get(n))
        elif kind == "similar" and card:
            city = other_city(card, places)
            if city:
                q = t["similar"].format(n=n, city=city)
                k = key("similar", ids.get(n), english_city(city))
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
        if q and (k in done or norm(q) in done):
            continue  # already done or asked in this conversation
        if q and q not in out:
            out.append(q)
        if len(out) == MAX:
            break
    return out


# After a card is tapped: every question the app can answer about that one home,
# in the order a buyer tends to ask them. The first two need the home's similar
# homes (the pane read them); without them the plain price-and-news question stands.
FOCUS = ["simpair", "drops", "price", "similar", "placenews", "contact"]


def focus_questions(lang: str, n: int, card: dict, places: list[str], similar: bool,
                    done: set[str] | None = None) -> list[tuple[str, str]]:
    """(kind, question) for a tapped card #n — not capped at MAX: the tap is the
    user asking what they can do with this home."""
    done = done or set()
    t = T.get(lang, T["en"])
    cid = card.get("id")
    out: list[tuple[str, str]] = []
    news_used = False
    for kind in FOCUS:
        q, k = None, None
        if kind == "simpair" and similar:
            q, k = t["simpair"].format(n=n), key("simpair", cid)
        elif kind == "drops":
            if similar:
                q, k = t["drops"].format(n=n), key("drops", cid)
            else:
                town = news_place(card, places)
                if town:
                    q, k = t["news"].format(n=n, city=town), key("news", cid)
                    news_used = True
        elif kind in ("price", "contact"):
            q, k = t[kind].format(n=n), key(kind, cid)
        elif kind == "similar":
            city = other_city(card, places)
            if city:
                q, k = t["similar"].format(n=n, city=city), key("similar", cid, english_city(city))
        elif kind == "placenews":
            town = news_place(card, places)
            if town and not news_used:
                q, k = t["placenews"].format(city=town), key("placenews", english_city(town))
        if q and (k in done or norm(q) in done):
            continue
        if q and all(q != x for _, x in out):
            out.append((kind, q))
    return out
