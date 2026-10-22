"""The budget comparison: what a budget buys in 2-3 cities (agent/inventory.py).

The connector's compare_inventory is faked with the shape it returned live on
2026-10-22 for Lisboa vs Porto; the model is scripted. These pin what the page
gets (bars from the tool, never from the model), that a budget change keeps the
cities and shows the earlier share, and that parking is never sent.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, guards, inventory, skills  # noqa: E402
from agent.loop import Agent  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402


def _f(**kw):
    base = dict(location=[], type=[], transaction_type="sale", min_price=None, max_price=None,
                min_bedrooms=None, max_bedrooms=None, min_living_area=None, has_parking=None,
                features=[], lang="en", needs_free_text_search=False)
    base.update(kw)
    return SearchFilter(**base)


def _result(cap, lis_pct, lis_n, opo_pct, opo_n):
    def place(name, pct, n, of, lid):
        return {"place": name, "level": "city",
                "base": {"count": of + 10, "priced": of, "on_request": 10},
                "within_budget": {"count": n, "priced": n, "on_request": 0, "share_pct": pct},
                "listings": [{"id": f"{lid}:1", "object_type": "Apartment", "city": name, "country": "Portugal",
                              "price": cap - 5000, "bedrooms": 2, "living_area": 80,
                              "url": f"https://cubi.estate/r/{lid}%3A1",
                              "ask_cubi_url": f"https://www.cubi.estate/chat?listing_id={lid}%3A1&intent=ask"}]}
    return {"ok": True, "kind": "listing_inventory_comparison", "as_of": "2026-10-22T12:00:00+00:00",
            "filters": {"transaction_type": "sale", "type": ["apartment"], "min_bedrooms": 2, "max_bedrooms": 2,
                        "max_price": float(cap), "has_parking": False},
            "denominator": "base.priced",
            "places": [place("Lisboa", lis_pct, lis_n, 2397, "remax"), place("Porto", opo_pct, opo_n, 1196, "zome")],
            "note": "asking prices"}


class _LLM:
    """Extraction calls get the next filter; loop calls get the next answer."""

    def __init__(self, filters, answers):
        self.filters, self.answers, self.calls = list(filters), list(answers), []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        content = self.filters.pop(0) if kw.get("response_format") else self.answers.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _agent(tmp_path, results, filters, answers):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_LLM(filters, answers))
    sent = []

    def call(name, args):
        sent.append((name, args))
        r = results.pop(0)
        if r is None:
            return {"is_error": True, "text": "boom"}
        return {"is_error": False, "text": json.dumps(r)}

    agent.mcp.call_tool = call
    return agent, sent


FIRST = _f(location=["Lisboa", "Porto"], type=["apartment"], min_bedrooms=2, max_bedrooms=2, max_price=400000)
SECOND = FIRST.model_copy(update={"location": [], "max_price": 500000})


@pytest.mark.parametrize("msg,last,want", [
    ("What does 400k buy in Lisbon vs Porto? 2-bed flats", None, "compare-budget"),
    ("What can I afford in Lisbon or Porto with 300k?", None, "compare-budget"),
    ("O que compro com 400 mil em Lisboa e no Porto?", None, "compare-budget"),
    ("Was bekommt man für 400.000 € in Lissabon und Porto?", None, "compare-budget"),
    ("And up to 500k?", "compare-budget", "compare-budget"),
    ("And up to 500k?", "find-homes", "find-homes"),
    ("Is #2 overpriced?", "compare-budget", "check-asking-price"),
    # A two-city search with a budget is a search, not a comparison (the video's turn 1).
    ("Wir ziehen um: Wohnung zum Kauf in Porto oder Valencia, bis 400.000 €, mindestens 2 Schlafzimmer",
     None, "find-homes"),
])
def test_selection(msg, last, want):
    assert skills.select(msg, has_results=True, last_skill=last) == want


def test_comparison_then_budget_change(tmp_path):
    agent, sent = _agent(tmp_path, [_result(400000, 9.6, 229, 30.3, 362), _result(500000, 16.8, 402, 57.5, 688)],
                         [FIRST.model_dump_json(), SECOND.model_dump_json()],
                         ["Within €400,000: Lisboa 9.6%, Porto 30.3%.",
                          "At €500,000 Porto rises to 57.5% and Lisboa to 16.8%. Porto's share is 3.4 times Lisboa's."])
    first = list(agent.turn("What does 400k buy in Lisbon vs Porto? 2-bed flats"))[-1]
    assert first["skill"] == "compare-budget"
    assert [r["share_pct"] for r in first["inventory"]["rows"]] == [9.6, 30.3]
    assert "previous_max_price" not in first["inventory"]
    assert [c["n"] for c in first["listings"]] == [1, 2]
    assert first["listings"][0]["price_text"] == "395 000 EUR"
    name, args = sent[0]
    assert name == "compare_inventory" and args["places"] == ["Lisboa", "Porto"]
    assert "has_parking" not in args and args["transaction_type"] == "sale"

    second = list(agent.turn("And up to 500k?"))[-1]
    assert second["skill"] == "compare-budget"
    assert sent[1][1]["places"] == ["Lisboa", "Porto"] and sent[1][1]["max_price"] == 500000
    rows = second["inventory"]["rows"]
    assert [(r["share_pct"], r["previous_pct"]) for r in rows] == [(16.8, 9.6), (57.5, 30.3)]
    assert second["inventory"]["previous_max_price"] == 400000
    # A ratio the model worked out itself is not Cubi's figure: dropped.
    assert "3.4 times" not in second["text"] and "57.5%" in second["text"]
    assert second["guards"]["percentages_dropped"] == 1
    # The model writes around the bars; it is offered no tools.
    loop_calls = [c for c in agent.cli.calls if not c.get("response_format")]
    assert all(not c.get("tools") for c in loop_calls)


def test_parking_is_never_sent_and_the_model_is_told_why(tmp_path):
    f = FIRST.model_copy(update={"has_parking": True})
    agent, sent = _agent(tmp_path, [_result(400000, 9.6, 229, 30.3, 362)], [f.model_dump_json()], ["ok"])
    list(agent.turn("What does 400k buy in Lisbon vs Porto with parking?"))
    assert "has_parking" not in sent[0][1]
    tool_msgs = [m for m in agent.history if m["role"] == "tool"]
    assert "NOT compared" in agent.cli.calls[-1]["messages"][-1]["content"] or tool_msgs


def test_a_failed_call_draws_no_bars(tmp_path):
    agent, _ = _agent(tmp_path, [None], [FIRST.model_dump_json()], ["It could not be checked right now."])
    final = list(agent.turn("What does 400k buy in Lisbon vs Porto?"))[-1]
    assert final["inventory"] is None and final["listings"] == []


def test_one_city_asks_for_another(tmp_path):
    agent, sent = _agent(tmp_path, [], [FIRST.model_copy(update={"location": ["Lisboa"]}).model_dump_json()],
                         ["Which other city should I compare Lisbon with?"])
    final = list(agent.turn("What does 400k buy in Lisbon?"))[-1]
    assert sent == [] and final["inventory"] is None


def test_no_budget_asks_for_one(tmp_path):
    agent, sent = _agent(tmp_path, [], [FIRST.model_copy(update={"max_price": None}).model_dump_json()],
                         ["What is your budget?"])
    list(agent.turn("What can I afford in Lisbon or Porto?"))
    assert sent == []


@pytest.mark.parametrize("sentence", ["Porto has 3 times the share.", "Das sind 20,7 Prozentpunkte mehr.",
                                      "O Porto tem 3,2 vezes mais.", "That is 21 percentage points higher."])
def test_derived_figures_are_dropped(sentence):
    out, n = guards.drop_unbacked_percentages("Lisboa 9.6%. " + sentence, "Lisboa: 9.6%")
    assert n == 1 and out == "Lisboa 9.6%."


def test_unbacked_percentages_are_dropped():
    tool = "- Lisboa: 9.6% (229 of 2397)\n- Porto: 30.3% (362 of 1196)"
    answer = "Lisboa 9.6%, Porto 30,3%. That is a gap of 20.7%. Try another budget."
    out, n = guards.drop_unbacked_percentages(answer, tool)
    assert n == 1 and "20.7" not in out and "30,3%" in out and out.endswith("Try another budget.")


def test_tool_text_relays_shares_and_the_earlier_budget():
    prev = _result(400000, 9.6, 229, 30.3, 362)
    cur = _result(500000, 16.8, 402, 57.5, 688)
    text = inventory.tool_text(cur, prev, inventory.to_cards(cur))
    assert "Lisboa (city): 16.8% (402 of 2397 listings); at €400,000 it was 9.6%" in text
    assert "never compare the counts" in text
    assert "https://cubi.estate/r/remax%3A1" in text  # card links are in the tool text for the URL guard


def test_unpriced_sample_listings_are_not_shown():
    r = _result(400000, 9.6, 229, 30.3, 362)
    r["places"][0]["listings"][0]["price"] = None
    cards = inventory.to_cards(r)
    assert [c["id"] for c in cards] == ["zome:1"] and cards[0]["n"] == 1
