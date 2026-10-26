"""Price history + local news for a home on screen (skill home-news). The
connector and Tavily are faked; the model is scripted."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, guards, skills, suggest, tavily_tool, x_tool  # noqa: E402
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
    monkeypatch.setattr(x_tool, "enabled", lambda: False)   # X is opt-in; its own test turns it on
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
    assert ("Cubi has seen no change in this home's asking price since 3 June 2026, when the listing first "
            "appeared on Cubi.") in tool_msg


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
    assert "since 21 October 2026, when the listing first appeared on Cubi" in tool_msg
    assert "2026-05-02" not in tool_msg and "2 May" not in tool_msg     # one date only


def test_listing_older_than_the_log_names_the_log_start_only(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, {**HIST, "changes": [], "on_cubi_since": "2025-08-26"}, "ok")
    list(agent.turn("Has #2's price dropped?"))
    tool_msg = [m for m in agent.cli.calls[0]["messages"] if m["role"] == "tool"][0]["content"]
    assert "since 2 May 2026, when Cubi's price log began" in tool_msg
    assert "2025" not in tool_msg.split("##")[0]                             # no first-seen date to garble


def test_changes_are_listed_with_long_dates(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, HIST, "ok")
    list(agent.turn("Has #2's price dropped?"))
    tool_msg = [m for m in agent.cli.calls[0]["messages"] if m["role"] == "tool"][0]["content"]
    assert "- 1 July 2026: €450,000 → €430,000 (-4.4%)" in tool_msg
    assert "In total: -8.9% (from €450,000)." in tool_msg


def test_after_news_on_a_card_its_news_question_is_not_suggested(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, HIST, "ok")
    first = list(agent.turn("Has #2's price dropped, and what's new in Lisboa?"))[-1]
    assert not any("dropped" in q for q in first["suggestions"])
    assert suggest.key("news", "remax:2") in agent.done


def test_posts_on_x_read_cited_and_sent_to_the_page(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, HIST, "A march was held [S1]; posts on X mention rising rents [X1].")
    monkeypatch.setattr(x_tool, "enabled", lambda: True)
    post = {"id": "9", "text": "Rents up again", "date": "2026-10-21", "name": "Ana", "handle": "ana_l",
            "url": "https://x.com/ana_l/status/9", "sid": "X1"}
    monkeypatch.setattr(x_tool, "recent_posts", lambda place, first_id=1: (
        "## Recent posts on X\n[X1] 2026-10-21: Rents up again",
        {"posts": [post], "returned": 10, "seconds": 0.2,
         "sources": {"X1": {"url": post["url"], "title": "Ana (@ana_l) on X", "date": post["date"]}}}))
    final = list(agent.turn("Has #2's price dropped, and what's new in Lisboa?"))[-1]
    assert final["x_posts"] == [post] and final["stats"]["x_posts_read"] == 10
    assert "[X1](https://x.com/ana_l/status/9)" in final["text"]
    tool_msg = [m for m in agent.cli.calls[0]["messages"] if m["role"] == "tool"][0]["content"]
    assert "[X1] 2026-10-21: Rents up again" in tool_msg and "you have not read them" not in tool_msg


def test_x_failure_falls_back_to_the_link(tmp_path, monkeypatch):
    agent, _, _ = _agent(tmp_path, monkeypatch, HIST, "No change.")
    monkeypatch.setattr(x_tool, "enabled", lambda: True)

    def boom(place, first_id=1):
        raise x_tool.XError("today's X post budget is used up")
    monkeypatch.setattr(x_tool, "recent_posts", boom)
    events = list(agent.turn("Has #2's price dropped, and what's new in Lisboa?"))
    assert any("Posts on X unavailable" in (e.get("text") or "") for e in events if e["type"] == "action")
    assert events[-1]["x_posts"] == [] and events[-1]["x_url"]


def test_the_news_tool_text_ends_asking_for_a_short_summary():
    from agent.loop import BRIEF_NEWS
    assert "at most three sentences" in BRIEF_NEWS and "60 words" in BRIEF_NEWS
    skill = (Path(__file__).resolve().parents[1] / "skills" / "home-news" / "SKILL.md").read_text()
    assert "at most three sentences" in skill and "No greeting" in skill


def _collect(gen):
    out = []
    try:
        while True:
            out.append(next(gen))
    except StopIteration:
        pass
    return out


def test_a_place_question_is_about_the_place_not_the_last_card(tmp_path, monkeypatch):
    """Live 2026-10-26: "What's new in Nazare, Leiria" after a Sotogrande search gave that
    home's price history and Spanish news."""
    from agent.loop import named_place
    assert named_place("What's new in Nazaré, Leiria") == "Nazaré, Leiria"
    assert named_place("Has #2's price dropped, and what's new in Lisbon?") == "Lisbon"
    assert named_place("Quoi de neuf à Lyon ?") == "Lyon" and named_place("Was gibt es Neues in Lissabon?") == "Lissabon"
    assert named_place("what's new in the area") == "" and named_place("Has #2's price dropped?") == ""
    agent, calls, seen = _agent(tmp_path, monkeypatch, HIST, "ok")
    agent.focus = "remax:2"
    agent._message = "What's new in Nazaré, Leiria"
    events = _collect(agent._home_news())
    assert not any(name == "get_price_history" for name, _ in calls)
    assert seen == ["Nazaré, Leiria"] and agent.price_history is None
    text = [e for e in events if isinstance(e, str)][-1]
    assert "about Nazaré, Leiria only" in text and "price history for" not in text
    assert any(isinstance(e, dict) and "about the place, not a home" in e["text"] for e in events)


def test_a_card_question_keeps_the_price_and_takes_the_named_place(tmp_path, monkeypatch):
    agent, calls, seen = _agent(tmp_path, monkeypatch, HIST, "ok")
    agent._message = "Has #1's price dropped, and what's new in Nazaré?"
    _collect(agent._home_news())
    assert any(name == "get_price_history" for name, _ in calls) and agent.price_history["card"] == 1
    assert seen == ["Nazaré"]
    agent, calls, seen = _agent(tmp_path, monkeypatch, HIST, "ok")
    agent._message = "Has #2's price dropped, and what's new in Lisboa?"
    _collect(agent._home_news())
    assert seen == ["Lisboa, Portugal"]   # the card's own place: unchanged path, country kept
