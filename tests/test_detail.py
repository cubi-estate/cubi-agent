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
    again = agent.detail("EV:1")
    assert again["id"] == x["id"] and again["similar"] == x["similar"] and len(calls) == 3   # cached: no new reads


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


PAIR_MATCH = json.dumps({"ok": True, "mode": "pair", "seed": {"id": "ev:1", "price": 395000, "city": "Perledo", "country": "Italy",
                                                              "features": {}, "environment": {}, "minutes": {}, "climate": {}},
                         "matches": [{"id": "ev:2", "price": 450000, "city": "Varenna", "country": "Italy", "features": {},
                                      "environment": {}, "minutes": {}, "climate": {},
                                      "card": {"id": "ev:2", "price": 450000, "city": "Varenna", "country": "Italy", "bedrooms": 4,
                                               "living_area": 240, "object_type": "house/villa", "url": "https://cubi.estate/r/ev%3A2"}}]})


class _TurnLLM:
    """Loop calls get a plain answer; json_schema calls (the pane's brief) get the brief."""
    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        content = json.dumps(BRIEF) if kw.get("response_format") else self.answer
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _tapped(tmp_path, answer="#1 is listed at €395,000, #2 at €450,000."):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_TurnLLM(answer))
    agent.shown = [{"n": 1, "id": "ev:1", "type": "house/villa", "location": "Gittana, Lombardy, Italy"}]
    agent.seen_refs = {"ev:1"}
    agent.has_results = True
    calls = []

    def call(name, args):
        calls.append((name, args))
        if name == "get_listing":
            text = LISTING
        elif name == "find_similar_homes":
            text = SIMILAR
        elif name == "find_similar_elsewhere" and args.get("compare_with"):
            text = PAIR_MATCH.replace('"ev:2"', json.dumps(args["compare_with"]))
        elif name == "find_similar_elsewhere":
            text = PAIR
        else:
            text = json.dumps({"listing_id": args.get("listing_id"), "current_price": 400000, "currency": "EUR",
                               "on_cubi_since": "2026-06-03", "tracked_since": "2026-05-02", "changes": [], "city": "Varenna"})
        return {"is_error": False, "text": text, "structured": None}
    agent.mcp.call_tool = call
    agent.mcp.openai_tools = lambda names=None: []
    return agent, calls


def test_a_tap_adds_the_homes_questions_and_points_the_chat_at_it(tmp_path):
    agent, calls = _tapped(tmp_path)
    x = agent.detail("ev:1")
    assert agent.focus == "ev:1"
    qs = x["focus"]["suggestions"]
    assert x["focus"]["n"] == 1 and qs[0] == "Compare #1 with its similar homes feature by feature"
    assert "Has #1's price dropped, and have its similar homes' prices dropped?" in qs
    assert "How do I contact the agent for #1?" in qs and "What's new in Gittana?" in qs
    assert "Show me homes like #1 in Milano" in qs and len(qs) == 6   # Italy's big market, not the card's own
    assert agent.detail("ev:1")["focus"]["suggestions"] == qs   # a second tap: the same, no new reads
    assert sum(1 for n, _ in calls if n == "get_listing") == 1


def test_compare_with_its_similar_homes_runs_the_pairs_in_code(tmp_path):
    agent, calls = _tapped(tmp_path)
    agent.detail("ev:1")
    events = list(agent.turn("Compare #1 with its similar homes feature by feature"))
    final = events[-1]
    assert final["type"] == "answer" and final["skill"] == "similar-elsewhere"
    pairs = [a for n, a in calls if n == "find_similar_elsewhere" and a.get("compare_with") not in (None, a.get("listing_id"))]
    assert [a["compare_with"] for a in pairs] == ["ev:2", "ev:3"] and all(a["listing_id"] == "ev:1" for a in pairs)
    assert [c["id"] for c in final["listings"]] == ["ev:2", "ev:3"] and [c["n"] for c in final["listings"]] == [2, 3]
    cols = final["similar"]["columns"]
    assert [c["role"] for c in cols] == ["seed", "match", "match"] and [c["card"] for c in cols] == [1, 2, 3]
    assert any("Comparing #1 with its 2 similar homes" in e.get("text", "") for e in events if e.get("type") == "action")
    assert suggest_key("pair", "ev:1+ev:2") in agent.done
    assert all(not any(t["function"]["name"] == "find_similar_elsewhere" for t in (c.get("tools") or []))
               for c in agent.cli.calls if not c.get("response_format"))


def suggest_key(kind, ids):
    from agent import suggest
    return suggest.key(kind, ids)


def test_price_drops_of_the_home_and_its_similar_homes(tmp_path, monkeypatch):
    from agent import tavily_tool
    agent, calls = _tapped(tmp_path, answer="No change on #1, #2 or #3.")
    agent.detail("ev:1")
    monkeypatch.setattr(tavily_tool, "latest_news", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no news this turn")))
    events = list(agent.turn("Has #1's price dropped, and have its similar homes' prices dropped?"))
    final = events[-1]
    assert final["type"] == "answer" and final["skill"] == "home-news"
    hist = [a["listing_id"] for n, a in calls if n == "get_price_history"]
    assert hist == ["ev:1", "ev:2", "ev:3"]
    tool_msgs = [m["content"] for c in agent.cli.calls if not c.get("response_format") for m in c["messages"] if m.get("role") == "tool"]
    assert any("price history for the similar home in Varenna" in m for m in tool_msgs)
