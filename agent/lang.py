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


# ---- languages beyond the six ------------------------------------------------
# Any other language is read through English (agent/pivot.py): the model names it
# and translates, the turn runs in English, the answer is translated back. That
# costs a model call, so it is asked only when the text gives a reason: a letter
# none of the six languages uses (Cyrillic, Greek, ł, å, ő, ş …), or words from
# another language scoring at least as high as the best of the six. Italian and
# Polish share words with Spanish and Portuguese ("con", "piscina", "do"), so their
# lists include the shared ones on purpose; another language must then score higher
# than the best of the six (a tie on "a", "e" is the Portuguese button text).
_SIX_LETTERS = set("abcdefghijklmnopqrstuvwxyzàáâãäçèéêëìíîïñòóôõöœùúûüýÿßĳ")
_OTHER_WORDS = {
    "it": "il lo gli della delle degli dello del nel nella nei con per una un a e di da in al alla sono vorrei "
          "cerco cerchiamo affitto affittare vendita comprare camere camera letto appartamento appartamenti villetta "
          "casa case giardino terrazzo terrazza piscina mare vicino zona al mese fino massimo bilocale trilocale "
          "mostrami secondo seconda primo prima quanto costa solo",
    "pl": "mieszkanie mieszkania dom domy pokoje pokoj sprzedaz wynajem w z do na i za tys szukam chce blisko "
          "morza ogrod balkon basen miesiac kupic wynajac pokaz drugie pierwsze",
    "sv": "lagenhet hus till salu hyra rum med och i nara havet soker jag bostad villa tomt per manad visa",
    "da": "lejlighed hus til salg leje vaerelser med og i naer havet soger jeg bolig have pr maned vis",
    "no": "leilighet hus til salgs leie soverom med og i naer sjoen soker jeg bolig hage per maned vis",
    "cs": "byt dum prodej pronajem pokoje se s v u blizko hledam koupit mesic zahrada",
    "ro": "apartament casa vanzare inchiriere camere cu si in langa caut cumpar gradina luna",
    "hu": "lakas haz elado kiado szobas szoba es keresek kert honap",
    "tr": "daire ev satilik kiralik oda ile ve yakin ariyorum bahce havuz ay",
    "fi": "asunto talo myytavana vuokra huone ja lahella etsin piha kuukausi",
}
_OTHER_VOCAB = {lang: set(words.split()) for lang, words in _OTHER_WORDS.items()}


def _word_hits(tokens: list[str], vocab: set[str]) -> int:
    return sum(1 for t in tokens if t in vocab)


def needs_check(text: str) -> bool:
    """True when the text may be in a language outside the six (see above)."""
    low = text.lower()
    if any(c.isalpha() and c not in _SIX_LETTERS for c in low):
        return True
    tokens = re.findall(r"[a-zà-ÿĳ]+", low)
    # Folded, so "lägenhet" meets "lagenhet"; but not a folded single letter, or
    # French "à" would count as Italian "a".
    plain = [f for t in tokens
             if (f := unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()) == t or len(f) > 1]
    six = max(_word_hits(tokens, _VOCAB[lang]) for lang in LANGS)
    other = max(_word_hits(plain, v) for v in _OTHER_VOCAB.values())
    # Two words at least: one stray letter ("#2's" → "s", Czech "with") is not a language.
    return other >= 2 and other > six


def has_words(text: str) -> bool:
    """Any word at all (not just numbers, #2, prices or a lone place name)."""
    return len(re.findall(r"[^\W\d_]{2,}", text)) >= 2
