"""Deterministic language detection for the six languages the connector serves.

The day-1 probe showed language is the field Nemotron gets wrong most often
(French read as pt/en by three of four models), and it is trivially decidable
from function words, so it is not left to the model.
"""
from __future__ import annotations

import re
import unicodedata

LANGS = ("en", "pt", "es", "fr", "de", "nl")

# Short, high-frequency function words and domain words per language.
_WORDS = {
    "en": "plot garden garage pool lift terrace sea view family cheap the a an in with under for and or of to near i want looking buy rent bedroom bedrooms flat house apartment home homes max up show what is how first second third one ones only",
    "pt": "quinta piscina garagem varanda jardim praia terreno sossegada construção o a os as um uma em com até para e ou de do da no na perto quero procuro comprar arrendar alugar quartos casa moradia apartamento por mês moradias imóveis é mostra mostrar primeira segunda terceiro primeiro segundo este esta quanto só",
    "es": "piscina garaje ascensor terraza ático alquiler estudio urbanizable vistas mar el la los las un una en con hasta para y o de del cerca quiero busco comprar alquilar habitaciones dormitorios piso casa chalet por mes menos más muestra muestrame enséñame primero segundo tercero cuánto solo",
    "fr": "terrain piscine jardin balcon terrasse location louer studio bâtir pièces le la les un une en avec pour et ou de du des près je cherche acheter louer chambres maison appartement par mois moins budget calme plage montre premier première deuxième troisième combien seulement",
    "de": "grundstück garten aufzug tiefgarage dachterrasse miete wohnung ferienwohnung meerblick häuschen see bis der die das ein eine in mit unter für und oder von zu nahe ich suche kaufen mieten zimmer schlafzimmer wohnung haus pro monat maximal mindestens zeig zeige erste zweite dritte wie teuer ist nur",
    "nl": "bouwgrond grond woning huisje kavel zwembad tuin balkon parkeerplaats dakterras tot onder de het een in met onder voor en of van te bij ik zoek kopen huren slaapkamers appartement huis woning per maand max minimaal laat zien eerste tweede derde hoeveel alleen",
}
_VOCAB = {lang: set(words.split()) for lang, words in _WORDS.items()}

# Characters that strongly indicate one language.
_CHARS = {"pt": "ãõç", "es": "ñ¿¡", "fr": "èêëàùûœç", "de": "äöüß", "nl": "ĳ"}
# Character n-grams that are distinctive.
_GRAMS = {
    "pt": ("ção", "ões", "nh", "lh"),
    "es": ("ción", "ll", "habitacion"),
    "fr": ("eau", "oux", "ais", "près"),
    "de": ("sch", "ung", "ei"),
    "nl": ("ij", "oo", "aa", "ee", "uur"),
}


def detect(text: str, default: str = "en") -> str:
    low = text.lower()
    tokens = re.findall(r"[a-zà-ÿĳ]+", low)
    scores = {lang: 0.0 for lang in LANGS}
    for tok in tokens:
        for lang in LANGS:
            if tok in _VOCAB[lang]:
                scores[lang] += 1.0
    for lang, chars in _CHARS.items():
        scores[lang] += 1.5 * sum(low.count(c) for c in chars)
    plain = unicodedata.normalize("NFKD", low)
    for lang, grams in _GRAMS.items():
        scores[lang] += 0.3 * sum(plain.count(g) for g in grams)
    # Portuguese "T1/T2" typology is a strong signal.
    if re.search(r"\bt[0-6]\b", low):
        scores["pt"] += 2.0
    top = max(scores.values())
    if top < 1.0:
        return default
    leaders = [lang for lang in LANGS if scores[lang] == top]
    # A tie keeps the conversation's language (short follow-ups share words).
    return default if default in leaders else leaders[0]
