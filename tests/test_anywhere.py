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


# ---- the whole-corpus pass times out → one search per big market, side by side ----
import json  # noqa: E402

from agent import fixtures  # noqa: E402
from agent.loop import BIG_MARKETS, Agent, _error_code  # noqa: E402

INCOMPLETE = json.dumps({"is_error": True, "code": "search_incomplete", "tool": "search_properties",
                         "message": "The search did not finish in time, so there is no result"})
CARD_ES = ("**1. House for rent Marbella**\n   Location: Marbella, Andalusia, Spain\n   4 bd | 11 000 EUR / month\n"
           "   URL: https://cubi.estate/r/es1\n   ID: rentola_es:1\n")
CARD_IT = ("**1. Casa Indipendente**\n   Location: Castel di Sangro, Abruzzo, Italy\n   3 bd | 500 EUR / month\n"
           "   URL: https://cubi.estate/r/it1\n   ID: gabetti_it:1\n")
NONE = "No properties matched these filters."


def _agent(tmp_path, reply):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    calls = []

    def call(name, args):
        calls.append((name, args))
        text = reply(args)
        return {"is_error": text.lstrip().startswith("{"), "text": text, "structured": None}  # as mcp_client reads it
    agent.mcp.call_tool = call
    agent.anywhere, agent.wish = True, "ideally in a quiet spot"
    return agent, calls


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def test_the_connectors_error_code_is_read():
    assert _error_code(INCOMPLETE) == "search_incomplete"
    assert _error_code(json.dumps({"is_error": True, "code": "query_timeout"})) == "query_timeout"
    assert _error_code(CARD_ES) == "" and _error_code("{not json") == "" and _error_code("[1]") == ""


def test_a_timed_out_europe_wide_search_runs_per_market_and_merges(tmp_path):
    """Live 2026-10-26: "Houses to rent with a mountain view and near a lake, anywhere in
    Europe, ideally in a quiet spot" timed out at Cubi's 22 s deadline and the model
    asked for a town. Spain and Italy answered in seconds each, side by side."""
    agent, calls = _agent(tmp_path, lambda a: CARD_ES if " in Spain" in a["query"]
                          else CARD_IT if " in Italy" in a["query"] else NONE)
    f = _f(type=["house"], transaction_type="rent", features=["mountain view", "near a lake"])
    res, header = _run(agent._per_market("Houses to rent …, anywhere in Europe", f))
    assert not res["is_error"] and agent.split
    cards = listings.parse(res["text"])
    assert [c["n"] for c in cards] == [1, 2]
    assert "Spain" in cards[0]["location"] and "Italy" in cards[1]["location"]
    queries = sorted(a["query"] for _, a in calls)
    assert len(queries) == len(BIG_MARKETS) and all(q.endswith(", ideally in a quiet spot") for q in queries)
    assert "Houses to rent in Spain with mountain view and near a lake, ideally in a quiet spot" in queries
    assert "Portugal: 0 shown (no matches)" in header and "Spain: 1 shown" in header
    assert "not from every country on Cubi" in header and "Do not ask for a town" in header


def test_when_no_market_finishes_the_model_is_told_not_to_ask_for_a_town(tmp_path):
    agent, calls = _agent(tmp_path, lambda a: INCOMPLETE)
    res, header = _run(agent._per_market("Houses to rent, anywhere in Europe", None))
    assert res["is_error"] and "do not ask for a town" in header
    assert len(calls) == len(BIG_MARKETS)
    assert sorted(a["query"] for _, a in calls) == sorted(f"Houses to rent, anywhere in Europe — only in {c}" for c in BIG_MARKETS)


ASKED_WHERE = ("No properties matched. Suggest the user broaden the budget, change location, or relax feature "
               "requirements.\n---\nEurope is a big place! Which country or region would you like to search?")


def test_a_europe_wide_search_cubi_answers_with_a_question_runs_per_market(tmp_path):
    """Live 2026-10-27 (docs/incidents.md): "Homes for sale, anywhere in Europe" → Cubi
    asked where, and the agent said there were no listings. Keyed on the reply being a
    question (reply_guard: clarify), so it holds once the connector drops the
    "No properties matched" prefix."""
    for asked in (ASKED_WHERE, ASKED_WHERE.split("---\n", 1)[1]):
        agent, calls = _agent(tmp_path, lambda a, asked=asked: CARD_ES if " in Spain" in a["query"]
                              else CARD_IT if " in Italy" in a["query"] else asked)
        agent.replies = []
        res, header = _run(agent._free_once("Homes for sale anywhere in Europe", "Homes for sale, anywhere in Europe", None))
        assert len(calls) == 1 + len(BIG_MARKETS), asked
        assert [c["n"] for c in listings.parse(res["text"])] == [1, 2]


def test_a_genuine_zero_is_not_retried_per_market(tmp_path):
    zero = "Your search: Europe · villa · budget up to 10,000 EUR — no matches found."
    agent, calls = _agent(tmp_path, lambda a: zero)
    agent.replies = []
    res, _ = _run(agent._free_once("Villas under 10k anywhere in Europe", "Villas under 10k anywhere in Europe", None))
    assert len(calls) == 1 and res["text"] == zero
