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
    band = json.dumps({"band": {"low": 1, "median": 2, "high": 3}})
    assert Agent._no_band_brief(band, "card #1") == band
