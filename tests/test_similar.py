"""Homes like one listing in another city (agent/similar.py).

The connector's find_similar_elsewhere is faked in the shape it returns; the
model is scripted. These pin what the page gets (the table comes from the
tool, the matches become the cards), the card the user named, and the guards
on "saving"/"premium" wording."""
import json

import pytest
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
    r["matches"][0]["features"]["parking"] = "stated"
    text = similar.tool_text(r, similar.to_cards(r), "#2")
    assert "This home, #2 (Porto): €350,000, €4,375/m², 80 m², 2 bedrooms" in text
    assert ("The listing for the Lisboa match (#1) mentions parking; the listing for the Porto home (#2) "
            "doesn't say.") in text
    assert ("the Porto home (#2) is more than 5 km from the coast; the Lisboa match (#1) is within 5 km "
            "of the coast.") in text
    assert "The region of the Porto home (#2) gets about 2,450 hours of sun a year; the region of the Lisboa match (#1), about 2,800." in text
    assert "coastal" not in text.split("Matches:")[0]        # plain words, not internal keys
    assert "do not say what they have in common" in text
    assert "never a saving" in text and "https://cubi.estate/r/lis%3A1" in text


def test_unknown_readings_are_not_differences():
    seed = {"environment": {"quiet": {"state": "unknown"}}, "features": {}}
    m = {"environment": {"quiet": {"state": "yes"}}, "features": {}}
    assert similar.differences(seed, m) == []


def test_two_cards_named_runs_the_pair_in_code_and_keeps_the_cards(tmp_path):
    pair = _result(matches=1)
    pair.update(mode="pair", city="Porto")
    pair["seed"] = _profile("lis:1", "Lisboa", 430000, balcony=True)
    pair["matches"][0].update(_profile("opo:4", "Porto", 350000, balcony=True))
    llm = _LLM([SimpleNamespace(content="Lisbon #1 asks €430,000; Porto #4 asks €350,000.", tool_calls=None)])
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=llm)
    agent.shown = [{"n": 1, "id": "lis:1"}, {"n": 2, "id": "lis:2"}, {"n": 4, "id": "opo:4"}]
    agent.has_results = True
    sent = []
    agent.mcp.call_tool = lambda name, args: (sent.append(args), {"is_error": False, "text": json.dumps(pair)})[1]
    agent.mcp.openai_tools = lambda names=None: []
    final = list(agent.turn("Compare #1 and #4 feature by feature"))[-1]
    assert final["skill"] == "similar-elsewhere"
    assert sent == [{"listing_id": "lis:1", "compare_with": "opo:4", "lang": "en"}]
    assert [(c["role"], c["card"]) for c in final["similar"]["columns"]] == [("seed", 1), ("match", 4)]
    assert final["similar"]["mode"] == "pair" and final["listings"] == []
    assert [c["n"] for c in agent.shown] == [1, 2, 4]          # "#4" still means the Porto home
    loop_calls = [c for c in llm.calls]
    assert len(loop_calls) == 1 and not loop_calls[0].get("tools")


def test_absent_from_is_reworded_and_lacks_is_dropped():
    live = ("The Porto match #2 cites lift, parking, garden and a nearby campsite absent from the Lisbon listing, "
            "and it is closer to the metro.")
    out, n = guards.fix_absence_wording(live)
    assert n == 1 and "not mentioned in the Lisbon listing" in out and "absent" not in out
    out, n = guards.fix_absence_wording("Both ask about €400,000. The Lisbon home lacks parking. "
                                        "The Porto listing mentions a lift; the Lisbon listing doesn't say.")
    assert n == 1 and "lacks" not in out and out.startswith("Both ask about €400,000.")
    assert "doesn't say" in out


@pytest.mark.parametrize("sentence", [
    "O apartamento de Lisboa não tem estacionamento.", "El piso de Lisboa no tiene garaje.",
    "Die Lissabonner Wohnung hat keinen Aufzug.", "L'appartement de Lisbonne n'a pas de parking.",
    "De woning in Lissabon heeft geen lift.", "The Lisbon flat comes without a balcony.",
])
def test_absence_claims_are_dropped_in_every_language(sentence):
    out, n = guards.fix_absence_wording("Ok. " + sentence)
    assert n == 1 and out == "Ok."


def test_does_not_mention_is_kept():
    text = "The Lisbon listing does not mention parking."
    assert guards.fix_absence_wording(text) == (text, 0)


def test_the_guard_runs_only_for_similar_homes():
    answer, rep = guards.apply("Parking is absent from the listing.", "", "en", {"get_listing"})
    assert "absent" in answer and rep["absence_wording_fixed"] == 0
