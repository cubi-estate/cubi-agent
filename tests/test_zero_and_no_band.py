"""A search that finds nothing says why (measured, not guessed), and a price
check without a range gives one ready sentence instead of a verdict."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures  # noqa: E402
from agent.loop import Agent  # noqa: E402

CARD = "**1. Flat for sale Lyon**\n   Location: Lyon, France\n   2 bd | 238 000 EUR\n   URL: https://cubi.estate/r/x\n   ID: era_fr:1\n"
NONE = "No properties matched these filters."


def _agent(tmp_path, reply):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    calls = []

    def call(name, args):
        calls.append(args)
        return {"is_error": False, "text": reply(args), "structured": None}
    agent.mcp.call_tool = call
    return agent, calls


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


RENT = {"location": ["Lyon"], "type": ["apartment"], "transaction_type": "rent", "price_period": "month",
        "max_price": 1200, "limit": 6}


def test_no_rentals_at_any_price_is_named_not_the_budget(tmp_path):
    agent, calls = _agent(tmp_path, lambda a: CARD if "transaction_type" not in a else NONE)
    _, header = _run(agent._filter_call(dict(RENT)))
    assert "rental listings don't cover Lyon" in header and "a higher rent would not help" in header
    assert len(calls) == 3 and "max_price" not in calls[1] and "transaction_type" not in calls[2]
    assert agent.sale_only == ["Lyon"]
    assert agent._suggestions("find-homes", "x") == ["Homes for sale in Lyon"]


def test_budget_named_when_it_is_the_reason(tmp_path):
    agent, calls = _agent(tmp_path, lambda a: CARD if "max_price" not in a else NONE)
    _, header = _run(agent._filter_call(dict(RENT)))
    assert "budget is what rules them out" in header and len(calls) == 2


def test_no_probe_when_there_are_results(tmp_path):
    agent, calls = _agent(tmp_path, lambda a: CARD)
    _, header = _run(agent._filter_call(dict(RENT)))
    assert "why none" not in header and len(calls) == 1


def test_no_band_gives_a_ready_sentence():
    body = {"listing_id": "x:1", "band": None, "reason": "not_enough_comparable_listings", "n_comps": 2,
            "city": "Loulé"}
    out = Agent._no_band_brief(json.dumps(body), "card #1")
    assert "only 2 comparable homes in Loulé" in out and "#1" in out and "Never say" in out
    spread = Agent._no_band_brief(json.dumps({**body, "reason": "comparables_disagree", "n_comps": 9}), "card #1")
    assert "vary too much" in spread
    band = json.dumps({"band": {"low": 1, "median": 2, "high": 3}, "n_comps": 19})
    assert "Do not call the comparison thin" in Agent._no_band_brief(band, "card #1")
    few = json.dumps({"band": {"low": 1, "median": 2, "high": 3}, "n_comps": 3})
    assert "may say the comparison rests on few" in Agent._no_band_brief(few, "card #1")


def test_thin_hedge_dropped_only_when_comparables_are_ample():
    from agent import guards
    ans = ("The asking price lies within the range, based on 19 comparable homes. Given the modest number of "
           "comparables, the comparison is relatively thin. Condition and floor could explain it.")
    out, n = guards.drop_thin_hedge(ans, '{"band": {"low": 1}, "n_comps": 19}')
    assert n == 1 and "relatively thin" not in out and "19 comparable homes" in out and "Condition" in out
    assert guards.drop_thin_hedge(ans, '{"band": {"low": 1}, "n_comps": 3}') == (ans, 0)
    de = "Da nur wenige Vergleichsobjekte vorliegen, ist die Aussage dünn. Der Preis liegt im Bereich."
    assert guards.drop_thin_hedge(de, '{"n_comps": 12}')[0] == "Der Preis liegt im Bereich."


def test_source_filler_dropped_real_gaps_kept():
    from agent import guards
    ans = ("Porto has CLIP [S2]. No source indicated a lack of school information for either city.\n\n"
           "Valencia has a metro [S10]. Neither source set reported missing details on public transport. "
           "No source covered healthcare in Porto.")
    out, rep = guards.apply(ans, "", "en", {"research_area"})
    assert "lack" not in out and "missing" not in out and "No source covered healthcare in Porto." in out
    assert rep["source_filler_dropped"] == 2
    pt = "O Porto tem metro [S1]. Nenhuma fonte indicou falta de informação sobre escolas."
    assert guards.apply(pt, "", "pt", {"research_area"})[0] == "O Porto tem metro [S1]."


def test_for_sale_button_switches_to_sale_without_the_extractor(tmp_path):
    from agent.schema import SearchFilter
    agent, calls = _agent(tmp_path, lambda a: CARD)
    agent.lang = "fr"
    agent.filter = SearchFilter(location=["Lyon"], type=["apartment"], transaction_type="rent", min_price=None,
                                max_price=1200, min_bedrooms=None, max_bedrooms=None, min_living_area=None,
                                has_parking=None, features=[], lang="fr", needs_free_text_search=False)
    agent.sale_only = ["Lyon"]
    list(agent._search_homes("Logements à vendre à Lyon"))
    assert calls[0]["transaction_type"] == "sale" and "max_price" not in calls[0]
    assert "price_period" not in calls[0] and agent.sale_only == []
