"""The step log in the user's language.

The agent writes its steps in English (agent/loop.py, and the tests read them
there). `localize` maps each one onto a template below and rewrites it in the
user's language, keeping the variable parts — places, card numbers, ids, error
text — as they were. The five other native languages are written here by hand;
any other language is translated once by Nemotron (`warm`), all templates in one
call, checked to keep every {placeholder}, and cached for the life of the process.
A step that matches no template, or a language not yet warmed, stays English.
"""
from __future__ import annotations

import json
import os
import re
import threading

from . import llm

# key → English. Must produce exactly what loop.py yields.
EN = {
    "relaxed": "No exact matches — searching again without: {features}",
    "search_place": "Searching listings in {place} (structured filter)",
    "understood": "Understood: {filter}",
    "search": "Searching listings (structured filter)",
    "fallback": "Structured search could not finish — retrying with Cubi's free-text search (runs Cubi's own "
                "server-side language model)",
    "free_text": "Request needs free-text search (no place, a whole country, or something like 'near the beach') "
                 "— using Cubi's free-text search (runs Cubi's own server-side language model)",
    "budget_cities": "A budget comparison needs two or three cities",
    "budget_budget": "A budget comparison needs a budget",
    "counting": "Counting listings within budget in {places} (Cubi compare_inventory)",
    "research": "Researching {places} on the web (Tavily): {topics}",
    "research_na": "Area research unavailable: {error}",
    "news": "Searching recent news about {city} (Tavily, last {days} days)",
    "news_na": "News search unavailable: {error}",
    "x": "Reading recent posts about housing in {city} on X (last 7 days)",
    "x_na": "Posts on X unavailable: {error}",
    "pair": "Comparing #{a} and #{b} feature by feature",
    "matches": "{n} matching home(s) in {city}, matched on features and surroundings, not price",
    "tool_error": "Tool error: {error}",
    # Composite steps: {label} and {how} are themselves localized (LABELS, HOWS).
    "which": "{label}: which home? (no card number or known id)",
    "na": "{label}: not available right now",
    "with_ref": "{label} — {how} ({ref})",
    # labels
    "l_listing": "Opening the listing",
    "l_prices": "Comparing asking prices nearby",
    "l_contact": "Looking up contact options",
    "l_two": "Comparing two homes feature by feature",
    "l_like": "Finding homes like it in {city}",
    "l_history": "Price history",
    "l_check_history": "Checking the price history",
    "l_budget": "Budget comparison",
    "l_similar": "Similar homes",
    # how a home was resolved
    "h_card": "card #{n}",
    "h_earlier": "id from an earlier result",
    "h_last": "the home discussed last",
    "h_only": "the only card on screen",
}
LABELS = [k for k in EN if k.startswith("l_")]
HOWS = [k for k in EN if k.startswith("h_")]
STEPS = [k for k in EN if not k.startswith(("l_", "h_"))]
_NESTED = {"label": LABELS, "how": HOWS}

NATIVE: dict[str, dict[str, str]] = {
    "pt": {
        "relaxed": "Sem resultados exatos — a pesquisar de novo sem: {features}",
        "search_place": "A pesquisar anúncios em {place} (filtro estruturado)",
        "understood": "Entendido: {filter}",
        "search": "A pesquisar anúncios (filtro estruturado)",
        "fallback": "A pesquisa estruturada não terminou — a tentar a pesquisa em texto livre da Cubi (usa o "
                    "modelo de linguagem da própria Cubi)",
        "free_text": "O pedido precisa de pesquisa em texto livre (sem local, um país inteiro ou algo como 'perto "
                     "da praia') — a usar a pesquisa em texto livre da Cubi (usa o modelo de linguagem da própria Cubi)",
        "budget_cities": "Uma comparação de orçamento precisa de duas ou três cidades",
        "budget_budget": "Uma comparação de orçamento precisa de um orçamento",
        "counting": "A contar anúncios dentro do orçamento em {places} (Cubi compare_inventory)",
        "research": "A pesquisar {places} na web (Tavily): {topics}",
        "research_na": "Pesquisa da zona indisponível: {error}",
        "news": "A procurar notícias recentes sobre {city} (Tavily, últimos {days} dias)",
        "news_na": "Pesquisa de notícias indisponível: {error}",
        "x": "A ler publicações recentes sobre habitação em {city} no X (últimos 7 dias)",
        "x_na": "Publicações do X indisponíveis: {error}",
        "pair": "A comparar a #{a} e a #{b} característica a característica",
        "matches": "{n} casa(s) semelhante(s) em {city}, por características e envolvente, não por preço",
        "tool_error": "Erro da ferramenta: {error}",
        "which": "{label}: que casa? (sem número de cartão nem id conhecido)",
        "na": "{label}: indisponível de momento",
        "with_ref": "{label} — {how} ({ref})",
        "l_listing": "A abrir o anúncio",
        "l_prices": "A comparar preços pedidos na zona",
        "l_contact": "A procurar formas de contacto",
        "l_two": "A comparar duas casas característica a característica",
        "l_like": "A procurar casas parecidas em {city}",
        "l_history": "Histórico de preços",
        "l_check_history": "A verificar o histórico de preços",
        "l_budget": "Comparação de orçamento",
        "l_similar": "Casas semelhantes",
        "h_card": "cartão #{n}",
        "h_earlier": "id de um resultado anterior",
        "h_last": "a casa de que se falou por último",
        "h_only": "o único cartão no ecrã",
    },
    "es": {
        "relaxed": "Sin resultados exactos — buscando de nuevo sin: {features}",
        "search_place": "Buscando anuncios en {place} (filtro estructurado)",
        "understood": "Entendido: {filter}",
        "search": "Buscando anuncios (filtro estructurado)",
        "fallback": "La búsqueda estructurada no terminó — reintentando con la búsqueda en texto libre de Cubi "
                    "(usa el propio modelo de lenguaje de Cubi)",
        "free_text": "La petición necesita búsqueda en texto libre (sin lugar, un país entero o algo como 'cerca "
                     "de la playa') — usando la búsqueda en texto libre de Cubi (usa el propio modelo de lenguaje de Cubi)",
        "budget_cities": "Una comparación de presupuesto necesita dos o tres ciudades",
        "budget_budget": "Una comparación de presupuesto necesita un presupuesto",
        "counting": "Contando anuncios dentro del presupuesto en {places} (Cubi compare_inventory)",
        "research": "Investigando {places} en la web (Tavily): {topics}",
        "research_na": "Investigación de la zona no disponible: {error}",
        "news": "Buscando noticias recientes sobre {city} (Tavily, últimos {days} días)",
        "news_na": "Búsqueda de noticias no disponible: {error}",
        "x": "Leyendo publicaciones recientes sobre vivienda en {city} en X (últimos 7 días)",
        "x_na": "Publicaciones de X no disponibles: {error}",
        "pair": "Comparando la #{a} y la #{b} característica por característica",
        "matches": "{n} vivienda(s) parecida(s) en {city}, por características y entorno, no por precio",
        "tool_error": "Error de la herramienta: {error}",
        "which": "{label}: ¿qué vivienda? (sin número de tarjeta ni id conocido)",
        "na": "{label}: no disponible ahora mismo",
        "with_ref": "{label} — {how} ({ref})",
        "l_listing": "Abriendo el anuncio",
        "l_prices": "Comparando precios de oferta en la zona",
        "l_contact": "Buscando formas de contacto",
        "l_two": "Comparando dos viviendas característica por característica",
        "l_like": "Buscando viviendas parecidas en {city}",
        "l_history": "Historial de precios",
        "l_check_history": "Comprobando el historial de precios",
        "l_budget": "Comparación de presupuesto",
        "l_similar": "Viviendas parecidas",
        "h_card": "tarjeta #{n}",
        "h_earlier": "id de un resultado anterior",
        "h_last": "la vivienda de la que se habló por última vez",
        "h_only": "la única tarjeta en pantalla",
    },
    "fr": {
        "relaxed": "Aucun résultat exact — nouvelle recherche sans : {features}",
        "search_place": "Recherche d'annonces à {place} (filtre structuré)",
        "understood": "Compris : {filter}",
        "search": "Recherche d'annonces (filtre structuré)",
        "fallback": "La recherche structurée n'a pas abouti — nouvel essai avec la recherche en texte libre de "
                    "Cubi (son propre modèle de langage)",
        "free_text": "La demande nécessite une recherche en texte libre (pas de lieu, un pays entier ou quelque "
                     "chose comme « près de la plage ») — recherche en texte libre de Cubi (son propre modèle de langage)",
        "budget_cities": "Une comparaison de budget nécessite deux ou trois villes",
        "budget_budget": "Une comparaison de budget nécessite un budget",
        "counting": "Comptage des annonces dans le budget à {places} (Cubi compare_inventory)",
        "research": "Recherche sur {places} sur le web (Tavily) : {topics}",
        "research_na": "Recherche sur le quartier indisponible : {error}",
        "news": "Recherche d'actualités récentes sur {city} (Tavily, {days} derniers jours)",
        "news_na": "Recherche d'actualités indisponible : {error}",
        "x": "Lecture des publications récentes sur le logement à {city} sur X (7 derniers jours)",
        "x_na": "Publications X indisponibles : {error}",
        "pair": "Comparaison du n° {a} et du n° {b} critère par critère",
        "matches": "{n} bien(s) similaire(s) à {city}, par caractéristiques et environnement, pas par prix",
        "tool_error": "Erreur de l'outil : {error}",
        "which": "{label} : quel bien ? (pas de numéro de carte ni d'id connu)",
        "na": "{label} : indisponible pour le moment",
        "with_ref": "{label} — {how} ({ref})",
        "l_listing": "Ouverture de l'annonce",
        "l_prices": "Comparaison des prix demandés à proximité",
        "l_contact": "Recherche des moyens de contact",
        "l_two": "Comparaison de deux biens critère par critère",
        "l_like": "Recherche de biens similaires à {city}",
        "l_history": "Historique des prix",
        "l_check_history": "Vérification de l'historique des prix",
        "l_budget": "Comparaison de budget",
        "l_similar": "Biens similaires",
        "h_card": "carte n° {n}",
        "h_earlier": "id d'un résultat précédent",
        "h_last": "le bien évoqué en dernier",
        "h_only": "la seule carte à l'écran",
    },
    "de": {
        "relaxed": "Keine exakten Treffer — neue Suche ohne: {features}",
        "search_place": "Suche nach Angeboten in {place} (strukturierter Filter)",
        "understood": "Verstanden: {filter}",
        "search": "Suche nach Angeboten (strukturierter Filter)",
        "fallback": "Die strukturierte Suche wurde nicht fertig — neuer Versuch mit Cubis Freitextsuche (Cubis "
                    "eigenes Sprachmodell)",
        "free_text": "Die Anfrage braucht eine Freitextsuche (kein Ort, ein ganzes Land oder etwas wie „nahe am "
                     "Strand“) — mit Cubis Freitextsuche (Cubis eigenes Sprachmodell)",
        "budget_cities": "Ein Budgetvergleich braucht zwei oder drei Städte",
        "budget_budget": "Ein Budgetvergleich braucht ein Budget",
        "counting": "Zähle Angebote im Budget in {places} (Cubi compare_inventory)",
        "research": "Recherche zu {places} im Web (Tavily): {topics}",
        "research_na": "Gebietsrecherche nicht verfügbar: {error}",
        "news": "Suche aktuelle Nachrichten zu {city} (Tavily, letzte {days} Tage)",
        "news_na": "Nachrichtensuche nicht verfügbar: {error}",
        "x": "Lese aktuelle Beiträge zum Wohnen in {city} auf X (letzte 7 Tage)",
        "x_na": "Beiträge auf X nicht verfügbar: {error}",
        "pair": "Vergleiche #{a} und #{b} Merkmal für Merkmal",
        "matches": "{n} passende(s) Objekt(e) in {city}, nach Merkmalen und Umgebung, nicht nach Preis",
        "tool_error": "Werkzeugfehler: {error}",
        "which": "{label}: welches Objekt? (keine Kartennummer und keine bekannte ID)",
        "na": "{label}: gerade nicht verfügbar",
        "with_ref": "{label} — {how} ({ref})",
        "l_listing": "Öffne das Angebot",
        "l_prices": "Vergleiche Angebotspreise in der Nähe",
        "l_contact": "Suche Kontaktmöglichkeiten",
        "l_two": "Vergleiche zwei Objekte Merkmal für Merkmal",
        "l_like": "Suche ähnliche Objekte in {city}",
        "l_history": "Preisverlauf",
        "l_check_history": "Prüfe den Preisverlauf",
        "l_budget": "Budgetvergleich",
        "l_similar": "Ähnliche Objekte",
        "h_card": "Karte #{n}",
        "h_earlier": "ID aus einem früheren Ergebnis",
        "h_last": "das zuletzt besprochene Objekt",
        "h_only": "die einzige Karte auf dem Bildschirm",
    },
    "nl": {
        "relaxed": "Geen exacte treffers — opnieuw zoeken zonder: {features}",
        "search_place": "Woningen zoeken in {place} (gestructureerd filter)",
        "understood": "Begrepen: {filter}",
        "search": "Woningen zoeken (gestructureerd filter)",
        "fallback": "De gestructureerde zoekopdracht liep niet af — opnieuw met Cubi's vrije-tekstzoeker (Cubi's "
                    "eigen taalmodel)",
        "free_text": "De vraag vraagt om vrij zoeken (geen plaats, een heel land of iets als 'bij het strand') — "
                     "met Cubi's vrije-tekstzoeker (Cubi's eigen taalmodel)",
        "budget_cities": "Een budgetvergelijking heeft twee of drie steden nodig",
        "budget_budget": "Een budgetvergelijking heeft een budget nodig",
        "counting": "Woningen binnen budget tellen in {places} (Cubi compare_inventory)",
        "research": "{places} onderzoeken op het web (Tavily): {topics}",
        "research_na": "Buurtonderzoek niet beschikbaar: {error}",
        "news": "Recent nieuws over {city} zoeken (Tavily, laatste {days} dagen)",
        "news_na": "Nieuws zoeken niet beschikbaar: {error}",
        "x": "Recente berichten over wonen in {city} op X lezen (laatste 7 dagen)",
        "x_na": "Berichten op X niet beschikbaar: {error}",
        "pair": "#{a} en #{b} kenmerk voor kenmerk vergelijken",
        "matches": "{n} vergelijkbare woning(en) in {city}, op kenmerken en omgeving, niet op prijs",
        "tool_error": "Fout in hulpmiddel: {error}",
        "which": "{label}: welke woning? (geen kaartnummer of bekende id)",
        "na": "{label}: nu niet beschikbaar",
        "with_ref": "{label} — {how} ({ref})",
        "l_listing": "De advertentie openen",
        "l_prices": "Vraagprijzen in de buurt vergelijken",
        "l_contact": "Contactmogelijkheden opzoeken",
        "l_two": "Twee woningen kenmerk voor kenmerk vergelijken",
        "l_like": "Vergelijkbare woningen zoeken in {city}",
        "l_history": "Prijsgeschiedenis",
        "l_check_history": "De prijsgeschiedenis bekijken",
        "l_budget": "Budgetvergelijking",
        "l_similar": "Vergelijkbare woningen",
        "h_card": "kaart #{n}",
        "h_earlier": "id uit een eerder resultaat",
        "h_last": "de laatst besproken woning",
        "h_only": "de enige kaart op het scherm",
    },
}

_RUNTIME: dict[str, dict[str, str]] = {}  # languages translated by Nemotron, this process
_PENDING: set[str] = set()
_LOCK = threading.Lock()
_FIELD = re.compile(r"\{(\w+)\}")


def _fields(t: str) -> list[str]:
    return sorted(_FIELD.findall(t))


def _pattern(t: str) -> re.Pattern:
    parts = _FIELD.split(t)  # literal, name, literal, name, …
    rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(parts))
    return re.compile(f"^{rx}$", re.S)


_PATTERNS = {k: _pattern(v) for k, v in EN.items()}
# Literal steps first, then the specific patterns, the generic composites last.
_ORDER = sorted(STEPS, key=lambda k: (k in ("which", "na", "with_ref"), bool(_fields(EN[k]))))


def _neutral(key: str) -> bool:
    """No words to translate ("{label} — {how} ({ref})"): the English one serves every language."""
    return not re.search(r"[^\W\d_]", _FIELD.sub("", EN[key]))


NEUTRAL = {k for k in EN if _neutral(k)}


def table(lang: str) -> dict[str, str] | None:
    t = NATIVE.get(lang) or _RUNTIME.get(lang)
    return {**{k: EN[k] for k in NEUTRAL}, **t} if t else None


def _match(text: str, keys: list[str]) -> tuple[str, dict] | None:
    for k in keys:
        m = _PATTERNS[k].match(text)
        if m:
            return k, m.groupdict()
    return None


def localize(text: str, lang: str) -> str:
    """The English step `text` in `lang`; unchanged when it can't be done."""
    if lang == "en" or not text:
        return text
    t = table(lang)
    if not t:
        return text
    hit = _match(text, _ORDER)
    if not hit or hit[0] not in t:
        return text
    key, values = hit
    for name, keys in _NESTED.items():
        if name in values:
            sub = _match(values[name], keys)
            if sub and sub[0] in t:
                values[name] = t[sub[0]].format(**sub[1])
    try:
        return t[key].format(**values)
    except (KeyError, IndexError, ValueError):
        return text


PROMPT = (
    "Translate the values of this JSON object from English to {name}. They are short status lines a "
    "home-search app shows while it works; a 'card' is one result in the app's list of homes. Keep every "
    "{{placeholder}} exactly as written, keep product and tool names (Cubi, Tavily, X, compare_inventory) "
    "and '#'. Reply with the same keys, JSON only."
)


# What the model is given to translate, where the English word misleads: "card" came
# back as Italian "carta" (paper); "listing" gives "annuncio" (live 2026-10-24).
_SOURCE = {"h_card": "listing #{n}", "h_only": "the only listing on screen",
           "which": "{label}: which home? (no listing number or known id)"}


def translate(cli, lang: str, name: str) -> dict[str, str]:
    """All templates in one call; a template that loses or gains a placeholder is left out."""
    r = cli.chat.completions.create(
        model=llm.model("super"), temperature=0, max_tokens=3000, extra_body=llm.NO_THINK,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": PROMPT.replace("{name}", name)},
                  {"role": "user", "content": json.dumps({k: _SOURCE.get(k, v) for k, v in EN.items()
                                                          if k not in NEUTRAL}, ensure_ascii=False)}])
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (r.choices[0].message.content or "").strip())
    out = json.loads(text)
    return {k: v for k, v in out.items()
            if k in EN and isinstance(v, str) and v.strip() and _fields(v) == _fields(EN[k])}


def warm(cli, lang: str, name: str, background: bool = True) -> None:
    """Make `lang` available to localize(), once per process. Failures leave it English."""
    if lang == "en" or lang in NATIVE:
        return
    with _LOCK:
        if lang in _RUNTIME or lang in _PENDING:
            return
        _PENDING.add(lang)

    def run():
        try:
            got = translate(cli, lang, name)
            if got:
                _RUNTIME[lang] = got
        except Exception:  # noqa: BLE001 - steps stay English
            pass
        finally:
            with _LOCK:
                _PENDING.discard(lang)

    if background:
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


# Warmed at server start, so a conversation's first turn in one of these already
# shows its steps translated (the video's Italian turn is a first turn).
PREWARM = {"it": "Italian", "ru": "Russian", "pl": "Polish", "uk": "Ukrainian", "sv": "Swedish", "ro": "Romanian",
           "cs": "Czech", "el": "Greek", "tr": "Turkish", "da": "Danish"}


def prewarm(cli) -> None:
    langs = [x.strip() for x in os.environ.get("STEPS_PREWARM", ",".join(PREWARM)).split(",") if x.strip()]

    def run():
        for code in langs:
            warm(cli, code, PREWARM.get(code, code), background=False)

    threading.Thread(target=run, daemon=True).start()
