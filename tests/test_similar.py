"""Homes like one listing in another city (agent/similar.py).

The connector's find_similar_elsewhere is faked in the shape it returns; the
model is scripted. These pin what the page gets (the table comes from the
tool, the matches become the cards), the card the user named, and the guards
on "saving"/"premium" wording."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, guards, similar  # noqa: E402
from agent.loop import Agent  # noqa: E402


def _profile(id_, city, price, area=80, **feat):
    return {"id": id_, "city": city, "price": price, "living_area": area, "bedrooms": 2, "bathrooms": 1,
            "eur_per_m2": round(price / area),
            "features": {k: ("stated" if feat.get(k) else "not_stated") for k in similar.FEATURES},
            "environment": {"quiet": {"state": "yes"}, "clean_air": {"state": "yes", "value": 9.4, "unit": "µg/m³ PM2.5"},
                            "coastal": {"state": "no" if city == "Porto" else "yes", "value": 7.0 if city == "Porto" else 3.0}},
            "minutes": {"walk_time.metro_station": 6}, "climate": {"sunshine_hours": 2450 if city == "Porto" else 2800}}


def _result(matches=2):
    ms = [{**_profile(f"lis:{i}", "Lisboa", 420000 + i * 10000, balcony=True),
           "card": {"id": f"lis:{i}", "object_type": "Apartment", "city": "Lisboa", "country": "Portugal",
                    "price": 420000 + i * 10000, "bedrooms": 2, "living_area": 80,
                    "url": f"https://cubi.estate/r/lis%3A{i}", "ask_cubi_url": f"https://www.cubi.estate/chat?listing_id=lis%3A{i}"}}
          for i in range(1, matches + 1)]
    return {"ok": True, "kind": "similar_elsewhere", "city": "Lisboa", "seed": _profile("opo:2", "Porto", 350000, balcony=True),
            "matches": ms, "pool": {"engine": 9, "in_city": 4, "dropped": {"bedrooms": 1, "area": 1}},
            "rules": {"ranking": "never price"}, "reason": None if ms else "no_documented_match"}


def _tool_call(name, args):
    fn = SimpleNamespace(name=name, arguments=json.dumps(args))
    tc = SimpleNamespace(id="c1", type="function", function=fn)
    tc.model_dump = lambda exclude_none=True: {"id": "c1", "type": "function", "function": {"name": name, "arguments": fn.arguments}}
    return tc


class _LLM:
    def __init__(self, msgs):
        self.msgs, self.calls = list(msgs), []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.msgs.pop(0))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _agent(tmp_path, result, answer):
    llm = _LLM([SimpleNamespace(content="", tool_calls=[_tool_call(similar.TOOL, {"listing_id": "#2", "city": "Lisboa"})]),
                SimpleNamespace(content=answer, tool_calls=None)])
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=llm)
    agent.shown = [{"n": 1, "id": "opo:1"}, {"n": 2, "id": "opo:2"}]
    agent.has_results = True
    sent = []

    def call(name, args):
        sent.append((name, args))
        return {"is_error": False, "text": json.dumps(result) if isinstance(result, dict) else result}

    agent.mcp.call_tool = call
    agent.mcp.openai_tools = lambda names=None: []
    return agent, sent


def test_table_and_cards_come_from_the_tool(tmp_path):
    agent, sent = _agent(tmp_path, _result(), "In Lisboa the two matches ask €430,000 and €440,000; #2 asks €350,000.")
    final = list(agent.turn("Show me homes like #2 in Lisbon"))[-1]
    assert final["skill"] == "similar-elsewhere"
    assert sent[0][1]["listing_id"] == "opo:2" and sent[0][1]["city"] == "Lisboa"   # "#2" resolved in code
    cols = final["similar"]["columns"]
    assert [(c["role"], c["card"], c["id"]) for c in cols] == [("seed", 2, "opo:2"), ("match", 1, "lis:1"), ("match", 2, "lis:2")]
    assert cols[0]["environment"]["coastal"]["state"] == "no" and cols[1]["environment"]["leafy"]["state"] == "unknown"
    assert cols[1]["features"]["lift"] == "not_stated"
    assert [c["id"] for c in final["listings"]] == ["lis:1", "lis:2"] and final["listings"][0]["price_text"] == "430 000 EUR"
    assert agent.shown[0]["id"] == "lis:1"     # "#1" now means the first match


def test_saving_and_premium_wording_is_dropped():
    out, n = guards._drop_sentences("Lisbon asks €430,000. That is a saving of €80,000 in Porto. "
                                    "Lisbon carries a premium.", guards._SAVING)
    assert n == 2 and out == "Lisbon asks €430,000."
    answer, rep = guards.apply("Porto is a bargain. Both list a balcony.", "", "en", {similar.TOOL})
    assert "bargain" not in answer and rep["verdicts_dropped"] == 1


def test_no_match_is_said(tmp_path):
    agent, _ = _agent(tmp_path, _result(matches=0), "No similar listing was found in Lisbon.")
    final = list(agent.turn("Show me homes like #2 in Lisbon"))[-1]
    assert final["listings"] == [] and len(final["similar"]["columns"]) == 1
    text = similar.tool_text(_result(matches=0), [], "#2")
    assert "No documented match in Lisboa" in text and "do not suggest a looser match" in text


def test_same_city_and_failures_draw_nothing(tmp_path):
    agent, _ = _agent(tmp_path, {"ok": False, "error": "same_city"}, "That home is already in Lisbon.")
    final = list(agent.turn("Show me homes like #2 in Lisbon"))[-1]
    assert final["similar"] is None
    agent, _ = _agent(tmp_path, "Cubi backend returned HTTP 500.", "Not available right now.")
    final = list(agent.turn("Show me homes like #2 in Lisbon"))[-1]
    assert final["similar"] is None and final["listings"] == []


def test_tool_text_names_the_differences_not_a_verdict():
    r = _result()
    text = similar.tool_text(r, similar.to_cards(r), "#2")
    assert "This home (#2, Porto): €350,000, €4,375/m², 80 m²" in text
    assert "coastal: no / yes / yes" in text
    assert "never a saving" in text and "https://cubi.estate/r/lis%3A1" in text
