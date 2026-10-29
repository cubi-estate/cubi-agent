"""The listing pane (agent/detail.py): the home in full, its area profile and a
guarded brief in the user's language, read once per conversation on tap."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import detail, fixtures  # noqa: E402
from agent.loop import Agent  # noqa: E402

LISTING = """# Detached villa with lake view in Perledo on Lake Como

**Location:** Italy, Lombardy, Gittana, Lombardy
**Details:** house/villa | 5 bd | 2 ba | 260 m2 living | 420 m2 plot | 395 000 EUR
**URL:** https://cubi.estate/r/ev%3A1
**ID:** ev:1

## Description
Spacious villa with stunning lake views. Requires some interior updating.

## Continue on Cubi
- Ask more: https://www.cubi.estate/chat?listing_id=ev%3A1&intent=ask
- Contact the agent: https://www.cubi.estate/chat?listing_id=ev%3A1&intent=contact

## Energy
- energyClass F

## Interior
- Fireplace
- Needs renovation

## Images
- https://img.example.com/1.jpg
- not a url

## Views
- Lake View
- Mountain view
- Mountain view
"""

PAIR = json.dumps({"ok": True, "mode": "pair", "seed": {
    "id": "ev:1", "eur_per_m2": 1519.2,
    "environment": {"quiet": {"state": "unknown"}, "clean_air": {"state": "yes", "value": 9.7, "unit": "µg/m³ PM2.5"},
                    "wildfire_safer": {"state": "no", "value": 89, "unit": "high fire-weather days/yr"}},
    "minutes": {"walk_time.supermarket": 4, "walk_time.school": None},
    "climate": {"sunshine_hours": 1900.0, "summer_max_c": 29.0}}, "matches": []})

BRIEF = {"tldr": "A five-bedroom villa above Lake Como with lake and mountain views; it needs some updating. A real bargain.",
         "highlights": ["Lake and mountain views", "Fireplace", "Garden of 420 m²"],
         "watch_outs": ["Needs renovation", "Energy class F", "Call 912 345 678 for a viewing"],
         "description": ""}


class _LLM:
    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.answer)))])


def test_parse_reads_facts_description_sections_images_and_links():
    x = detail.parse(LISTING)
    assert x["title"].startswith("Detached villa") and x["location"] == "Italy, Lombardy, Gittana"
    assert x["bedrooms"] == 5 and x["living_area"] == 260 and x["plot_area"] == 420 and x["price_text"] == "395 000 EUR"
    assert x["description"] == "Spacious villa with stunning lake views. Requires some interior updating."
    assert x["sections"] == {"Energy": ["energyClass F"], "Interior": ["Fireplace", "Needs renovation"],
                             "Views": ["Lake View", "Mountain view"]}
    assert x["images"] == ["https://img.example.com/1.jpg"]
    assert "intent=ask" in x["ask_url"] and "intent=contact" in x["contact_url"] and x["id"] == "ev:1"


def test_profile_keeps_the_known_axes_minutes_and_climate():
    p = detail.profile(PAIR)
    assert [e["key"] for e in p["environment"]] == ["quiet", "clean_air", "wildfire_safer"]
    assert p["minutes"] == {"walk_time.supermarket": 4} and p["climate"]["summer_max_c"] == 29.0
    assert p["eur_per_m2"] == 1519.2 and detail.profile("not json") == {}


def test_the_brief_is_guarded_and_in_the_users_language():
    cli = _LLM(BRIEF)
    b = detail.brief(cli, detail.parse(LISTING), detail.profile(PAIR), "en", "English")
    assert "bargain" not in b["tldr"] and b["tldr"].startswith("A five-bedroom villa")
    assert b["highlights"] == BRIEF["highlights"]
    assert b["watch_outs"][:2] == ["Needs renovation", "Energy class F"] and all("912" not in w for w in b["watch_outs"])
    assert b["description"] == ""   # English: Cubi's own text stands, whatever the model returned
    fr = detail.brief(_LLM({**BRIEF, "description": "Villa spacieuse avec vue sur le lac."}), detail.parse(LISTING), {}, "fr", "French")
    assert fr["description"] == "Villa spacieuse avec vue sur le lac."
    system = cli.calls[0]["messages"][0]["content"]
    assert "in English" in system and "never judge the asking price" in system
    assert "clean_air: yes" in cli.calls[0]["messages"][1]["content"]


SIMILAR = json.dumps({"ok": True, "seed_id": "ev:1", "count": 2,
                      "method": {"embedding": "pca", "ranker": "hybrid", "scope": "in_city"},
                      "matches": [
                          {"card": {"id": "ev:2", "title": "Villa in Varenna", "price": 450000, "currency": "EUR", "bedrooms": 4,
                                    "living_area": 240, "city": "Varenna", "country": "Italy", "object_type": "house/villa",
                                    "url": "https://cubi.estate/r/ev%3A2", "ask_cubi_url": "https://www.cubi.estate/chat?listing_id=ev%3A2&intent=ask"},
                           "why": "Same type, lake view, 8% smaller", "similarity": 0.81},
                          {"card": {"id": "ev:3", "price": 1200, "currency": "EUR", "price_period": "month", "city": "Bellano"},
                           "why": "", "similarity": 0.7},
                          {"card": {}, "why": "no id", "similarity": 0.1}]})


def test_similar_homes_become_lean_matches_with_the_rankers_reason():
    s = detail.similar_homes(SIMILAR)
    assert s["similar_method"]["embedding"] == "pca"
    assert [m["id"] for m in s["similar"]] == ["ev:2", "ev:3"]            # a match without an id is dropped
    m = s["similar"][0]
    assert m["price_text"] == "450 000 EUR" and m["place"] == "Varenna, Italy" and m["why"] == "Same type, lake view, 8% smaller"
    assert m["url"] == "https://cubi.estate/r/ev%3A2" and m["type"] == "house/villa" and m["bedrooms"] == 4
    assert s["similar"][1]["price_text"] == "1 200 EUR/mo" and s["similar"][1]["place"] == "Bellano"
    assert detail.similar_homes("Listing not found.") == {"similar": [], "similar_method": {}}
    assert detail.similar_homes(json.dumps({"ok": False, "error": "x"}))["similar"] == []


def test_read_merges_everything_and_the_agent_caches_it(tmp_path):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_LLM(BRIEF))
    calls = []

    def call(name, args):
        calls.append((name, args))
        text = {"get_listing": LISTING, "find_similar_elsewhere": PAIR, "find_similar_homes": SIMILAR}[name]
        return {"is_error": False, "text": text, "structured": None}
    agent.mcp.call_tool = call
    x = agent.detail("ev:1")
    assert x["ok"] and x["id"] == "ev:1" and x["images"] and x["eur_per_m2"] == 1519.2
    assert x["description"].startswith("Spacious villa") and x["translated"] is False
    assert x["highlights"] and x["watch_outs"]
    assert sorted(n for n, _ in calls) == ["find_similar_elsewhere", "find_similar_homes", "get_listing"]
    assert [m["id"] for m in x["similar"]] == ["ev:2", "ev:3"] and x["similar_method"]["embedding"] == "pca"
    assert dict(calls)["find_similar_homes"] == {"listing_id": "ev:1", "lang": "en", "limit": 3}
    assert agent.detail("EV:1") is x and len(calls) == 3


def test_a_connector_without_the_similar_tool_still_gives_the_pane(tmp_path):
    from agent.mcp_client import MCPError
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_LLM(BRIEF))

    def call(name, args):
        if name == "find_similar_homes":
            raise MCPError("tools/call: Unknown tool: find_similar_homes")
        return {"is_error": False, "text": LISTING if name == "get_listing" else PAIR, "structured": None}
    agent.mcp.call_tool = call
    x = agent.detail("ev:1")
    assert x["ok"] and x["similar"] == [] and x["similar_method"] == {}


def test_a_failed_listing_read_is_reported_not_invented(tmp_path):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_LLM(BRIEF))
    agent.mcp.call_tool = lambda name, args: {"is_error": True, "text": "boom", "structured": None}
    assert agent.detail("ev:9") == {"ok": False, "id": "ev:9"}
