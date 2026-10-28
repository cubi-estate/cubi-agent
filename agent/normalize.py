"""Deterministic clean-up after Nemotron extracts a filter.

Each rule fixes an error the 60-query eval showed was systematic rather than
random (reports/eval_20261014T131844Z.md), and each is decidable from the
words the user actually typed:

  * sale vs rent  — models chose 'rent' for requests that never mention renting
                    (13-14 of Nano's/Lightning's misses, mostly fr/de/nl);
  * features      — left in the user's language ('piscina', 'dakterras');
  * property type — 'penthouse'/'villa'/'land' flattened to apartment/house;
  * route         — moods and proximity ('quiet', 'near the beach') and whole
                    countries need the free-text search; towns, cities and
                    regions go to the structured filter.
"""
from __future__ import annotations

import re
import unicodedata

from .schema import SearchFilter


def _plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


RENT = (r"\b(rent|rental|to let|lease|arrend\w*|alug\w*|alquil\w*|louer|a louer|location d\w*|en location|"
        r"miete\w*|mieten|huur\w*|huren|per month|a month|por mes|al mes|par mois|im monat|"
        r"pro monat|per maand|/month|/mes|/mois)\b")
SALE = r"\b(buy|purchase|compr\w*|achet\w*|kauf\w*|kopen|koop)\b"

# Canonical English feature names → patterns in the six languages (ascii-folded).
FEATURES = {
    "Pool": r"\b(pool|piscin\w*|zwembad|schwimmbad|swimming)\b",
    "Terrace": r"(terrace|terrac\w*|terraz\w*|terrass\w*|terras\b|dakterras|dachterrass\w*)",
    "Balcony": r"\b(balcon\w*|balcony|varanda\w*|balkon\w*)\b",
    "Garden": r"\b(garden|jardi\w*|garten|tuin)\b",
    "Elevator": r"\b(lift|elevator|elevador|ascensor|ascenseur|aufzug|fahrstuhl)\b",
    "Sea View": r"(sea view|vista\w* (para o |al |ao )?mar|vue (sur la )?mer|meerblick|zeezicht)",
    # Condition words. The wizard puts them before the noun ("Renovated houses…"); the
    # chip line dropped them though Cubi filtered on them (live 2026-10-25, 237 of the
    # Portuguese rental houses). "to renovate" is not "renovated": no \w* on the stem.
    "Renovated": r"\b(renovated|refurbished|remodel+ed|renovad[ao]s?|reformad[ao]s?|remodelad[ao]s?|renove[es]?|"
                 r"renoviert\w*|saniert\w*|gerenoveerd)\b",
    "Furnished": r"\b(furnished|mobilad[ao]s?|amueblad[ao]s?|meuble[es]?|mobliert\w*|gemeubileerd)\b",
    "Fixer-Upper": r"\b(fixer[- ]upper|to renovate|needs? (renovation|work)|para (renovar|reformar|recuperar|restaurar)|"
                   r"a (renover|restaurer)|renovierungsbedurftig\w*|sanierungsbedurftig\w*|opknapper|op te knappen)\b",
}
PARKING = r"\b(garage|garag\w*|garaj\w*|parking|parkeer\w*|tiefgarage|stellplatz|estacionamento|aparcamiento)\b"

# Concepts a card tag can be matched to: the features above, parking, and the
# landscapes and comforts the wizard writes ("near a lake", "with a fireplace").
# A tag lights up on the card when the request names the concept it belongs to.
CONCEPTS = {
    **FEATURES,
    "Parking": PARKING,
    "Lake": r"\b(lake\w*|jezior\w*|jezer\w*|lago|lac|seeblick|am see|meerzicht)\b",
    "Mountain": r"\b(mountain\w*|montanh\w*|montan\w*|montagn\w*|berg\w*|gory|gorski\w*|alpin\w*)\b",
    "Countryside": r"\b(countryside|rural|campo|campagne|landlich\w*|platteland|wiejsk\w*|quiet|sossegad\w*|tranquil\w*|calme|ruhig\w*|rustig\w*)\b",
    "Fireplace": r"\b(fireplace|lareira|chimenea|cheminee|kamin\w*|kominek|open haard)\b",
    "Sauna": r"\b(sauna)\b",
    "Air Conditioning": r"\b(air[- ]?con\w*|ac|ar condicionado|aire acondicionado|climatis\w*|klimaanlage|airco|klimatyzacj\w*)\b",
    "Family": r"\b(family|famil\w*|school\w*|escola\w*|colegio\w*|ecole\w*|schule\w*|school|szko\w*)\b",
    "Transport": r"\b(transport\w*|metro|tram|bus|station|estacao|estacion|gare|bahnhof|komunikacj\w*)\b",
}


def wanted(request: str) -> list[str]:
    """The concept patterns the request names."""
    text = _plain(request)
    return [pat for pat in CONCEPTS.values() if _has(pat, text)]


def hits(request: str, tags: list[str]) -> list[str]:
    """The tags that belong to a concept the request names."""
    want = wanted(request)
    return [t for t in tags if any(_has(pat, _plain(t)) for pat in want)]


def missing(request: str, tags: list[str]) -> list[str]:
    """The named concepts none of these tags cover."""
    return [pat for pat in wanted(request) if not any(_has(pat, _plain(t)) for t in tags)]

# Specific types the user named → they win over a generic apartment/house.
TYPES = {
    "penthouse": r"\b(penthouse|atico|cobertura|attique)\b",
    "villa": r"\b(villa|vivenda)\b",
    "studio": r"\b(studio|estudio)\b",
    "land": r"\b(plot|land|terreno|terrain|grundstuck|bouwgrond|kavel)\b",
}

# Things no filter field can hold → free-text search.
FREE_TEXT = (r"\b(near|close to|perto|junto|cerca|pres|nahe|am see|bij|"
             r"beach|praia|playa|plage|strand|"
             r"quiet|sossegad\w*|tranquil\w*|calme|ruhig\w*|rustig\w*|charming|charmant\w*|"
             r"countryside|campagne|platteland|landlich|no campo|en el campo|"
             r"somewhere|algures|algun sitio|quelque part|irgendwo|ergens|algo)\b")


# "with some land", "com muito terreno": land as an extra, not the property type.
LAND_AS_EXTRA = r"\b(with (some |a lot of |lots of )?land|com (muito )?terreno|con terreno|avec terrain|mit grundstuck|met grond)\b"
HOUSE_WORDS = r"\b(house|home|casa|moradia|quinta|maison|haus|hauschen|huis|huisje|woning|chalet|villa|farmhouse|property)\b"

# From here on the user is wishing, not requiring: "…, ideally with a sea view and
# furnished". The wizard writes its nice-to-haves this way; Cubi's free-text search
# ranks on them. Nemotron still listed them as features ("sea_view",
# "quiet_countryside", live 2026-10-25), which a later structured follow-up would
# have applied as hard filters.
SOFT = (r"\b(ideally|preferably|nice to have|would be nice|if possible|idealmente|de preferencia|"
        r"preferiblemente|idealement|de preference|idealerweise|am liebsten|liefst|bij voorkeur)\b")


# "A large plot" names no size, and Cubi's search cannot rank on the bare word
# ("the large plot preference couldn't be applied", live 2026-10-28). With a
# number Cubi filters on the plot ("plot 1,000+ m2"). 1,000 m2 is the oracle's
# band for a large villa plot on the Spanish and Algarve coasts, coastal Italy
# and France (2026-10-28); in Cubi 43% of the villas that report a plot have one.
LARGE_PLOT_M2 = 1000
LARGE_PLOT = (r"\b(?:a |an )?(?:large|big|huge|generous|good[- ]sized|spacious|lots of|plenty of)\s+"
              r"(?:plot|plot of land|land|grounds|parcel)s?\b"
              r"|\b(?:grande|amplo|amplio|gran|grand|vaste)s?\s+(?:terreno|parcela|terrain)s?\b"
              r"|\b(?:terreno|parcela|terrain)s?\s+(?:grande|amplo|amplio|grand|vaste)s?\b"
              r"|\b(?:gro(?:ss|ß)e[smn]?|weitl[aä]ufige[smn]?)\s+grundst[uü]ck\w*"
              r"|\bgro(?:te|ot)\s+(?:kavel|perceel|grond)\b")


def plot_wish(text: str) -> bool:
    return bool(re.search(LARGE_PLOT, text or "", re.I))


def with_plot_size(text: str) -> str:
    """"…ideally with a large plot" -> "…ideally with a plot of at least 1,000 m2"."""
    return re.sub(LARGE_PLOT, f"a plot of at least {LARGE_PLOT_M2:,} m2", text or "", flags=re.I)


# "As an investment": nothing in Cubi's filter or ranking means it, and the answer
# repeated it as if it had been searched (live 2026-10-28).
INVESTMENT = (r"\b(invest(?:ment|ing|or)?s?|buy[- ]to[- ]let|rental (?:income|yield)|yields?|"
              r"investimento|rentabilidad|inversi[oó]n|investissement|rendement|rendite|kapitalanlage|"
              r"belegging|investering)\b")


def investment(text: str) -> bool:
    return bool(re.search(INVESTMENT, text or "", re.I))


def same_place(f: SearchFilter, current: SearchFilter) -> bool:
    """The new filter searches where the current one did (or names no place at all)."""
    if not f.location:
        return True
    return {_plain(x).strip() for x in f.location} == {_plain(x).strip() for x in current.location}


ALSO = r"\b(also|too|as well|tambem|tambien|aussi|auch|ook|ainda)\b"


def _new_places(places: list[str], before: list[str], text: str) -> list[str]:
    """A follow-up naming a new place searches that place: the earlier places the
    model carried over go, unless the user names them again or says "also".
    Tester F1: after the wizard's "Portugal", "Faro, 2 bedrooms, under 300k"
    searched "Faro, Portugal" and half the cards were 280 km away."""
    old = {_plain(x).strip() for x in before}
    if not any(_plain(x).strip() not in old for x in places) or _has(ALSO, text):
        return places
    return [x for x in places if _plain(x).strip() not in old or _has(rf"\b{re.escape(_plain(x).strip())}\b", text)]


def apply(f: SearchFilter, message: str, current: SearchFilter | None = None) -> SearchFilter:
    """Clean the model's filter using the user's own words.

    For a refinement (`current` given) a rule only fires when this message
    carries its cue; otherwise the conversation's value stands.
    """
    text = _plain(message)
    if current is not None:
        f = f.model_copy(update={"location": _new_places(f.location, current.location, text)})
    data = f.model_dump()
    # A refinement keeps the conversation's sale/rent and parking; a search for a
    # different place starts fresh. Live test 2026-10-20: after a Lisbon rental,
    # "piso … en Valencia hasta 300.000 €" ran as a rental.
    if current is not None and not same_place(f, current):
        current = None

    rent, sale = _has(RENT, text), _has(SALE, text)
    if rent and not sale:
        data["transaction_type"] = "rent"
    elif sale or current is None:
        data["transaction_type"] = "sale"
    else:
        data["transaction_type"] = current.transaction_type

    soft = re.search(SOFT, text)
    hard, wish = (text[:soft.start()], text[soft.start():]) if soft else (text, "")
    canon: list[str] = []
    for name, pattern in FEATURES.items():
        in_text = _has(pattern, hard)
        # With a wish in the message, the model's features need the user's own words before it.
        in_model = soft is None and any(_has(pattern, _plain(x)) for x in data["features"])
        if in_text or in_model:
            canon.append(name)
    # Keep any other feature the model found (e.g. 'Fireplace'), minus parking words —
    # but not a token it coined for a wish ("quiet_countryside") or a wish's own words.
    for x in data["features"]:
        px = _plain(x)
        if any(_has(p, px) for p in FEATURES.values()) or _has(PARKING, px) or px in TYPES:
            continue
        words = r"\b" + re.escape(px.replace("_", " ")) + r"\b"
        if ("_" in px or _has(words, wish)) and not _has(words, hard):
            continue
        canon.append(x)
    data["features"] = canon
    # Parking is a requirement only when asked for. Models fill `false` for "not
    # mentioned", which the connector reads as "must have no parking" and which
    # emptied studio searches in Lisbon and Granada (reports/compare_20261020T152335Z.md).
    if _has(PARKING, text):
        data["has_parking"] = True
    elif current is not None and current.has_parking:
        data["has_parking"] = True
    else:
        data["has_parking"] = None

    for name, pattern in TYPES.items():
        if not _has(pattern, text):
            continue
        if name == "land" and (_has(LAND_AS_EXTRA, text) or _has(HOUSE_WORDS, text)):
            continue
        generic = {"apartment", "house"}
        data["type"] = [t for t in data["type"] if t not in generic and t != name] + [name]
        break
    if data["type"] == ["land"] and (_has(LAND_AS_EXTRA, text) or _has(HOUSE_WORDS, text)):
        data["type"] = []  # model mistook "with land" for a plot
    elif "land" in data["type"] and len(data["type"]) > 1 and (
            _has(HOUSE_WORDS, text) or _has(LAND_AS_EXTRA, text) or plot_wish(text)):
        # "Villas …, ideally with a large plot" came back as villa/land (live
        # 2026-10-28): the plot is the villa's, not a second type.
        data["type"] = [t for t in data["type"] if t != "land"]

    free = bool(_has(FREE_TEXT, text))
    data["needs_free_text_search"] = free or bool(current and current.needs_free_text_search)
    return SearchFilter.model_validate(data)


# Covered countries in the six languages (ascii-folded). The connector resolves
# regions ('Algarve', 'Toscana', 'Costa Brava') fine, but a whole country is too
# broad for the structured filter (it times out with search_incomplete).
COUNTRIES = {
    "portugal", "spain", "espana", "espanha", "espagne", "spanien", "spanje",
    "italy", "italia", "italie", "italien", "italie",
    "france", "franca", "francia", "frankreich", "frankrijk",
    "germany", "alemanha", "alemania", "allemagne", "deutschland", "duitsland",
    "belgium", "belgica", "belgique", "belgien", "belgie",
    "austria", "autriche", "osterreich", "oostenrijk",
    "finland", "finlandia", "finlande", "finnland",
    "cyprus", "chipre", "chypre", "zypern", "cyprus",
    "croatia", "croacia", "croatie", "kroatien", "kroatie",
    "slovakia", "eslovaquia", "slovaquie", "slowakei", "slowakije",
    "malta", "malte",
    "greece", "grecia", "grece", "griechenland", "griekenland",
    "czech republic", "czechia", "chequia", "republica checa", "tchequie", "tschechien", "tsjechie",
    "poland", "polonia", "pologne", "polen",
    "netherlands", "paises baixos", "paises bajos", "pays-bas", "niederlande", "nederland", "holland",
    "bulgaria", "bulgarie", "bulgarien", "bulgarije",
    # Also on Cubi (the home wizard offers every country with listings).
    "united kingdom", "uk", "reino unido", "royaume-uni", "vereinigtes konigreich", "verenigd koninkrijk",
    "estonia", "estonie", "estland",
    "slovenia", "eslovenia", "eslovenia", "slovenie", "slowenien", "slovenie",
}


def is_country(place: str) -> bool:
    return _plain(place).strip() in COUNTRIES


def route_for(f: SearchFilter | None) -> str:
    """Structured filter when a town, city or region is named and nothing needs free text."""
    if f is None or not f.location or f.needs_free_text_search:
        return "search"
    if all(is_country(p) for p in f.location):
        return "search"
    return "filter"
