"""A Europe-wide search: "anywhere in Europe" runs the whole corpus (live 2026-10-26:
lakeside houses 104, Italy/Spain/Finland). The cards then sit in different countries,
so the compare button pairs two of them, the pair table names the countries, and a
refinement stays Europe-wide instead of making Cubi ask where."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import listings, similar, suggest  # noqa: E402
from agent.loop import ANYWHERE, _describe  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402


def _f(**kw):
    base = dict(transaction_type="sale", type=[], location=[], min_price=None, max_price=None, min_bedrooms=None,
                max_bedrooms=None, min_living_area=None, has_parking=None, features=[], lang="en",
                needs_free_text_search=False)
    return SearchFilter(**{**base, **kw})


def test_a_reduced_price_is_the_one_after_the_arrow():
    out = {}
    listings._facts_line("Detached house | 3 bd | 2 ba | 187 m2 living | 495 000 → 395 000 EUR 🔻20%", out)
    assert out["price"] == 395000.0 and "495 000" in out["price_text"]


def test_a_repeated_region_is_dropped_from_the_location():
    cards = listings.parse("**1. Villa**\n   Location: Italy, Lombardy, Gittana, Lombardy\n   ID: ev:1\n")
    assert cards[0]["location"] == "Italy, Lombardy, Gittana"


EUROPE = [{"n": 1, "id": "it:1", "location": "Italy, Lombardy, Gittana"},
          {"n": 2, "id": "it:2", "location": "Italy, Umbria, San Fatucchio"},
          {"n": 3, "id": "es:3", "location": "Alcaucín, Malaga, Andalucia, Spain"},
          {"n": 4, "id": "pt:4", "location": "Pedrógão Grande, Leiria, Portugal"}]


def test_the_country_is_the_country_wherever_it_is_written():
    assert [suggest.country_of(c) for c in EUROPE] == ["italy", "italy", "spain", "portugal"]
    assert suggest.country_of({"location": "Somewhere, Nowhere District"}) == "nowhere district"
    assert suggest._cross_country(EUROPE) and not suggest._cross_country(EUROPE[:2])


def test_a_europe_wide_search_offers_to_compare_two_countries():
    assert suggest.leaders(EUROPE, []) == (1, 3)
    assert suggest.leaders(EUROPE[:2], []) is None  # one country on screen: nothing to cross
    qs = suggest.next_questions("find-homes", "en", places=[], max_price=400000, shown=EUROPE)
    assert qs[0] == "Compare #1 and #3 feature by feature"


def test_the_pair_text_names_the_countries_only_across_borders():
    seed = {"id": "it:1", "city": "Gittana", "country": "Italy", "price": 395000,
            "features": {"balcony": "stated"}}
    match = {"id": "es:3", "city": "Alcaucín", "country": "Spain", "price": 369000,
             "features": {"terrace": "stated"}}
    text = similar.tool_text({"seed": seed, "matches": [match], "mode": "pair"}, [], "#1", match_labels=["#3"])
    assert "This home, #1 (Gittana, Italy)" in text and "Home #3 (Alcaucín, Spain)" in text
    assert "the Gittana, Italy home (#1) mentions balcony" in text
    same = similar.tool_text({"seed": seed, "matches": [{**match, "country": "Italy"}], "mode": "pair"}, [], "#1",
                             match_labels=["#3"])
    assert "(Gittana):" in same and "Italy" not in same
    assert similar.table({"seed": seed, "matches": [match]})["columns"][1]["country"] == "Spain"


def test_the_chip_line_says_europe_wide_in_the_users_language():
    f = _f(type=["house"], max_price=400000, features=["Fireplace"])
    assert _describe(f, "en", anywhere=True) == "for sale · house · ≤ €400,000 · Fireplace · anywhere in Europe"
    assert _describe(f, "pt", anywhere=True).endswith("em toda a Europa")
    assert _describe(f, "en") == "for sale · house · ≤ €400,000 · Fireplace"
    assert _describe(f.model_copy(update={"location": ["Lisbon"]}), "en", anywhere=True).endswith("in Lisbon")


def test_the_words_that_mean_every_country():
    yes = ["Houses near a lake, anywhere in Europe", "across the whole of Europe", "Everywhere in the EU",
           "casas em toda a Europa", "partout en Europe", "überall in Europa", "in any country"]
    no = ["Houses in Europe Street, Lisbon", "anywhere in Portugal", "a European-style villa"]
    assert all(ANYWHERE.search(suggest.norm(q)) for q in yes), [q for q in yes if not ANYWHERE.search(suggest.norm(q))]
    assert not any(ANYWHERE.search(suggest.norm(q)) for q in no)
