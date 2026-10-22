"""Price history + local news for a home on screen (skill home-news). The
connector and Tavily are faked; the model is scripted."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, guards, skills, tavily_tool  # noqa: E402
from agent.loop import Agent  # noqa: E402

HIST = {"listing_id": "remax:2", "city": "Lisboa", "country": "Portugal", "currency": "EUR",
        "current_price": 410000.0, "on_cubi_since": "2026-06-03", "tracked_since": "2026-05-02",
        "changes": [{"date": "2026-07-01", "old_price": 450000.0, "new_price": 430000.0, "pct": -4.4},
                    {"date": "2026-09-02", "old_price": 430000.0, "new_price": 410000.0, "pct": -4.7}],
        "drops": 2, "raises": 0, "total_change_pct": -8.9, "first_observed_price": 450000.0}


class _LLM:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answers.pop(0),
                                                                                tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _agent(tmp_path, monkeypatch, hist, answer, news_sources=1):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=_LLM([answer, answer]))
    agent.shown = [{"n": 1, "id": "remax:1", "location": "Porto, Porto District, Portugal"},
                   {"n": 2, "id": "remax:2", "location": "Lisboa, Lisboa, Portugal"}]
    agent.has_results = True
    calls = []

    def call(name, args):
        calls.append((name, args))
        return {"is_error": hist is None, "text": json.dumps(hist) if hist else "boom"}
    agent.mcp.call_tool = call
    agent.mcp.openai_tools = lambda names=None: []
    seen = []

    def news(place, http=None, first_id=1):
        seen.append(place)
        src = {f"S{first_id + i}": {"url": f"https://news.example.pt/{i}", "title": f"Lisbon item {i}",
                                    "date": "2026-10-20"} for i in range(news_sources)}
        return "## Latest news about Lisboa\n" + "\n".join(f"[{k}] {v['title']}" for k, v in src.items()), \
            {"searches": 2, "seconds": 0.1, "sources": src}
    monkeypatch.setattr(tavily_tool, "latest_news", news)
    return agent, calls, seen


def test_price_history_then_news_for_the_homes_city(tmp_path, monkeypatch):
    agent, calls, seen = _agent(tmp_path, monkeypatch, HIST,
                                "#2 dropped twice: -4.4% on 2026-07-01 and -4.7% on 2026-09-02, -8.9% in total. "
                                "A new metro line was announced [S1]. That makes it a bargain.")
    final = list(agent.turn("Has #2's price dropped, and what's new in Lisboa?"))[-1]
    assert final["skill"] == "home-news"
    assert calls == [("get_price_history", {"listing_id": "remax:2"})]
    assert seen == ["Lisboa, Portugal"]
    ph = final["price_history"]
    assert ph["card"] == 2 and [c["pct"] for c in ph["changes"]] == [-4.4, -4.7] and ph["total_change_pct"] == -8.9
    assert final["x_url"] == "https://x.com/search?q=Lisboa&f=live"
    assert "bargain" not in final["text"]                                   # verdict dropped
    assert "](https://news.example.pt/0)" in final["text"]                  # [S1] linked in code
    assert "-8.9%" in final["text"]                                          # the tool's own figure survives
    loop_calls = [c for c in agent.cli.calls]
    assert loop_calls and not loop_calls[0].get("tools")


def test_no_change_observed_is_said_with_the_tracking_date(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, {**HIST, "changes": [], "drops": 0, "total_change_pct": None},
                         "No change observed since 2026-06-03.")
    list(agent.turn("Has #2's price dropped?"))
    tool_msg = [m for m in agent.cli.calls[0]["messages"] if m["role"] == "tool"][0]["content"]
    assert "No change observed since 2026-06-03." in tool_msg   # first seen 06-03, after the log began


def test_price_history_failure_still_searches_news(tmp_path, monkeypatch):
    agent, _, seen = _agent(tmp_path, monkeypatch, None, "The price history is not available right now.")
    final = list(agent.turn("Has #2's price dropped?"))[-1]
    assert final["price_history"] is None and seen == ["Lisboa"]          # city from the card


def test_invented_percentage_is_dropped():
    tool = "- 2026-07-01: €450,000 → €430,000 (-4.4%)\nTotal: -8.9%."
    out, rep = guards.apply("It fell -8.9% in total. That is 20% below the city average.", tool, "en", {"home_news"})
    assert out == "It fell -8.9% in total." and rep["percentages_dropped"] == 1


def test_stray_hash_before_a_word_is_removed_but_card_numbers_stay():
    out, _ = guards.apply("#Lisbon home #2 asks €447,500.", "", "en", set())
    assert out == "Lisbon home #2 asks €447,500."


def test_x_link_is_a_live_search_for_the_town():
    assert tavily_tool.x_search_url("València, Spain") == "https://x.com/search?q=Val%C3%A8ncia&f=live"


def test_news_questions_route_here_not_to_the_price_check():
    assert skills.select("Has #2's price dropped, and what's new in Lisboa?", has_results=True) == "home-news"
    assert skills.select("Is #2 overpriced?", has_results=True) == "check-asking-price"


def test_news_queries_use_the_english_name_and_the_country():
    assert tavily_tool.news_queries("Lisboa", "Portugal") == ["Lisbon, Portugal housing market",
                                                             "Lisbon, Portugal property prices"]


def test_seller_pages_are_not_news(monkeypatch):
    rows = [{"url": "https://www.dreampropertiesvalencia.com/a", "title": "Valencia market", "content": "Valencia"},
            {"url": "https://www.bbc.com/news/1", "title": "Valencia housing protest", "content": "Valencia"},
            {"url": "https://www.idealista.com/en/news/1", "title": "Valencia prices", "content": "Valencia"}]
    monkeypatch.setattr(tavily_tool, "_search", lambda q, http, topic="general", days=None: rows)
    _, st = tavily_tool.latest_news("Valencia, Spain", http=object())
    assert [v["url"] for v in st["sources"].values()] == ["https://www.bbc.com/news/1",
                                                          "https://www.idealista.com/en/news/1"]


def test_country_news_is_labelled_when_the_city_has_too_little(monkeypatch):
    rows = [{"url": "https://www.reuters.com/1", "title": "Portugal house prices rise", "content": "Portugal"}]
    monkeypatch.setattr(tavily_tool, "_search", lambda q, http, topic="general", days=None: rows)
    text, st = tavily_tool.latest_news("Porto, Portugal", http=object())
    assert "(about Portugal as a whole, not Porto specifically)" in text and len(st["sources"]) == 1


def test_news_goes_to_the_place_on_the_card_not_the_stored_city(tmp_path, monkeypatch):
    agent, _, seen = _agent(tmp_path, monkeypatch, {**HIST, "city": "Cascais"}, "ok")
    list(agent.turn("Has #2's price dropped, and what's new in Lisboa?"))
    assert seen == ["Lisboa, Portugal"]


def test_tracking_starts_when_cubi_first_saw_the_listing(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, {**HIST, "changes": [], "on_cubi_since": "2026-10-21"}, "ok")
    final = list(agent.turn("Has #2's price dropped?"))[-1]
    assert final["price_history"]["tracked_since"] == "2026-10-21"
    tool_msg = [m for m in agent.cli.calls[0]["messages"] if m["role"] == "tool"][0]["content"]
    assert "watched this listing's price since 2026-10-21" in tool_msg
    assert "No change observed since 2026-10-21." in tool_msg
