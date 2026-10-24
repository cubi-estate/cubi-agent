import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import guards, skills  # noqa: E402
from agent.extract import extract, route_for  # noqa: E402
from agent.lang import detect  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402


@pytest.mark.parametrize("text,default,want", [
    ("Mostra-me a segunda", "en", "pt"),
    ("Et la deuxième ?", "en", "fr"),
    ("Zeig mir die zweite", "en", "de"),
    ("Laat de tweede zien", "en", "nl"),
    ("Muéstrame el segundo", "en", "es"),
    ("only ones with parking", "en", "en"),
    ("ok", "pt", "pt"),  # nothing to go on → keep the conversation's language
])
def test_lang_detect(text, default, want):
    assert detect(text, default=default) == want


def test_eval_set_languages_all_detected():
    cases = [json.loads(line) for line in (ROOT / "evals" / "filter_extraction.jsonl").read_text().splitlines()]
    misses = [c["id"] for c in cases if detect(c["q"]) != c["lang"]]
    assert misses == []


def test_verify_urls_drops_invented_listings_whole():
    tool_text = "URL: https://cubi.estate/r/iad_pt%3A158006\nURL: https://cubi.estate/r/iad_pt%3A2\n"
    answer = ("Found these:\n"
              "1. [Flat](https://cubi.estate/r/iad_pt%3A158006) — €300k\n"
              "2. **Invented** — €250k, Gaia\n   https://cubi.estate/r/made_up%3A1\n"
              "3. [Real two](https://cubi.estate/r/iad_pt%3A2) — €310k\n\n"
              "See also https://example.com/x")
    out, removed, dropped = guards.verify_urls(answer, tool_text, "en")
    assert "iad_pt%3A158006" in out and "Invented" not in out and "€250k" not in out
    assert "2. [Real two]" in out  # renumbered
    assert dropped == 1
    assert removed == ["https://cubi.estate/r/made_up%3A1", "https://example.com/x"]
    assert "See also" in out and "was removed" in out


def test_scrub_contacts_keeps_prices_and_cubi_addresses():
    out, n = guards.scrub_contacts("Call +351 912 345 678 or agent@remax.pt; €1 250 000; privacy@cubi.estate")
    assert n == 2
    assert "1 250 000" in out and "privacy@cubi.estate" in out


def test_valuation_line_added_once():
    assert guards.ensure_not_a_valuation("Within the range.", "de").endswith("keine Bewertung.")
    said = "Within range. This is not a valuation."
    assert guards.ensure_not_a_valuation(said, "en") == said


def test_skill_selection():
    assert skills.select("is the first one overpriced?", has_results=True) == "check-asking-price"
    assert skills.select("is the first one overpriced?", has_results=False) == "find-homes"
    assert skills.select("Como posso contactar o agente?", has_results=True) == "contact-agent"
    assert skills.select("3-bed house in Faro", has_results=True) == "find-homes"


def test_skills_load_from_vendored_pack():
    loaded = skills.load()
    assert set(loaded) == {"find-homes", "check-asking-price", "contact-agent", "compare-areas", "compare-budget", "similar-elsewhere", "home-news"}
    assert "filter_listings" in loaded["find-homes"].body


def _f(**kw):
    base = dict(location=[], type=[], transaction_type="sale", min_price=None, max_price=None,
                min_bedrooms=None, max_bedrooms=None, min_living_area=None, has_parking=None,
                features=[], lang="en", needs_free_text_search=False)
    base.update(kw)
    return SearchFilter(**base)


def test_route_needs_a_place_and_no_free_text_cue():
    assert route_for(_f(location=["Porto"])) == "filter"
    assert route_for(_f(location=["Algarve"], needs_free_text_search=True)) == "search"
    assert route_for(_f(location=["Toscana"])) == "filter"  # regions resolve fine
    assert route_for(_f(location=["Frankrijk"])) == "search"  # a whole country does not
    assert route_for(_f()) == "search"
    assert route_for(None) == "search"


from agent import normalize  # noqa: E402


@pytest.mark.parametrize("msg,model_kw,want", [
    # sale vs rent decided by the user's words, not the model
    ("Penthouse met dakterras in Antwerpen", dict(location=["Antwerpen"], transaction_type="rent", features=["dakterras"]),
     dict(transaction_type="sale", type=["penthouse"], features=["Terrace"])),
    ("Location d'un studio à Paris", dict(location=["Paris"], type=["apartment"]),
     dict(transaction_type="rent", type=["studio"])),
    ("Flat in Lisbon in a great location", dict(location=["Lisbon"], type=["apartment"]),
     dict(transaction_type="sale")),
    # features canonicalised; parking words become has_parking
    ("Chalet con piscina y garaje en Marbella", dict(location=["Marbella"], features=["piscina", "garaje"]),
     dict(features=["Pool"], has_parking=True)),
    # land only when it is the thing being bought
    ("Quinta no Alentejo com muito terreno", dict(location=["Alentejo"], type=["land"]),
     dict(type=[])),
    ("Terreno para construção em Aveiro", dict(location=["Aveiro"], type=[]), dict(type=["land"])),
    # "an der Algarve" is how German names a coast, not proximity
    ("Villa mit Pool an der Algarve", dict(location=["Algarve"], type=["villa"]), dict(needs_free_text_search=False)),
    # a named neighbourhood is not a mood
    ("T2 em Campo de Ourique", dict(location=["Campo de Ourique"]), dict(needs_free_text_search=False)),
])
def test_normalize(msg, model_kw, want):
    got = normalize.apply(_f(**model_kw), msg)
    for k, v in want.items():
        assert getattr(got, k) == v, (k, getattr(got, k))


def test_normalize_follow_up_keeps_rent():
    current = _f(location=["Lisboa"], transaction_type="rent", max_price=1500)
    got = normalize.apply(_f(location=["Lisboa"], transaction_type="sale", has_parking=True), "only ones with parking", current)
    assert got.transaction_type == "rent" and got.has_parking is True


class _FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        content = self.contents.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def _fake_cli(*contents):
    comp = _FakeCompletions(contents)
    return SimpleNamespace(chat=SimpleNamespace(completions=comp)), comp


def test_extract_repairs_once_then_routes():
    good = _f(location=["Faro"], max_price=600000).model_dump_json()
    cli, comp = _fake_cli('{"location": "Faro"}', good)
    ex = extract("Haus in Faro bis 600.000", cli=cli)
    assert ex.attempts == 2 and ex.route == "filter"
    assert ex.filter.lang == "de"  # detector overrides the model's guess
    assert comp.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_extract_gives_up_to_free_text_search():
    cli, _ = _fake_cli("nonsense", "still nonsense")
    ex = extract("something", cli=cli)
    assert ex.filter is None and ex.route == "search"


# ---- offline end-to-end: fake Token Factory + recorded connector replies ----

from agent import fixtures, listings  # noqa: E402
from agent.loop import Agent  # noqa: E402

CARDS = """Showing 2 properties.

**1. Lovely T2 with river views, see description**
   Location: Rua das Flores, 12, Bonfim, Porto, Portugal, Porto District
   Apartment | 2 bd | 1 ba | 88 m2 living | 310 000 EUR
   Long description copied from the portal that must not be kept.
   URL: https://cubi.estate/r/test_pt%3A1
   ID: test_pt:1
   Last changed: 2026-10-01
   Tags: Balcony, Elevator

**2. Second home**
   Location: Paranhos, Porto, Portugal, Porto District
   Apartment | 3 bd | 2 ba | 120 m2 living | 1.250.000 EUR
   URL: https://cubi.estate/r/test_pt%3A2
   ID: test_pt:2
"""


def test_listing_cards_parse_and_sanitise():
    cards = listings.parse(CARDS)
    assert [c["price"] for c in cards] == [310000.0, 1250000.0]
    assert cards[0]["bedrooms"] == 2 and cards[0]["tags"] == ["Balcony", "Elevator"]
    clean = fixtures.sanitise(CARDS)
    assert "copied from the portal" not in clean and "Lovely" not in clean and "Rua das Flores" not in clean
    assert "https://cubi.estate/r/test_pt%3A1" in clean and "Bonfim, Porto" in clean
    assert listings.parse(clean)[1]["price"] == 1250000.0


def test_plot_area_does_not_overwrite_living_area():
    out = {}
    listings._facts_line("Village House | 3 bd | 1 ba | 112 m2 living | 1420 m2 plot | 194 000 EUR", out)
    assert out["living_area"] == 112.0 and out["plot_area"] == 1420.0 and out["price"] == 194000.0


def test_fixture_key_ignores_case_order_and_limit():
    a = fixtures.key("filter_listings", {"location": ["Porto"], "type": ["apartment"], "limit": 6})
    b = fixtures.key("filter_listings", {"type": ["Apartment"], "location": ["porto"], "limit": 3})
    assert a == b


def _tool_call(name, args, id_="call_1"):
    fn = SimpleNamespace(name=name, arguments=json.dumps(args))
    tc = SimpleNamespace(id=id_, type="function", function=fn)
    tc.model_dump = lambda exclude_none=True: {"id": id_, "type": "function",
                                               "function": {"name": name, "arguments": fn.arguments}}
    return tc


class _ScriptedLLM:
    """Loop calls get tool calls/answers in order; extraction calls (json_schema) get the filter."""

    def __init__(self, loop_msgs, filter_json):
        self.loop_msgs, self.filter_json, self.calls = list(loop_msgs), filter_json, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        if kw.get("response_format"):
            msg = SimpleNamespace(content=self.filter_json, tool_calls=None)
        else:
            msg = self.loop_msgs.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def test_offline_turn_end_to_end(tmp_path):
    f = _f(location=["Porto"], type=["apartment"], max_price=400000, min_bedrooms=2)
    args = f.to_filter_args(limit=6)
    rec = {"tool": "filter_listings", "args": args, "is_error": False, "text": fixtures.sanitise(CARDS)}
    (tmp_path / f"{fixtures.key('filter_listings', args)}.json").write_text(json.dumps(rec))
    answer = ("Apartments in Porto:\n"
              "1. 2-bed, €310k — https://cubi.estate/r/test_pt%3A1\n"
              "2. 4-bed villa, €390k, Foz — https://cubi.estate/r/test_pt%3A99\n")
    # The search runs in code (no model round trip); the model only writes the summary.
    llm = _ScriptedLLM([SimpleNamespace(content=answer, tool_calls=None)], f.model_dump_json())
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=llm)
    events = list(agent.turn("2-bed apartment in Porto under 400k"))
    final = events[-1]
    assert final["type"] == "answer" and final["skill"] == "find-homes"
    assert "test_pt%3A1" in final["text"] and "Foz" not in final["text"]
    assert final["guards"]["items_dropped"] == 1
    assert agent.stats["filter_searches"] == 1 and agent.stats["fallback_searches"] == 0
    assert any(name.startswith("mcp filter_listings") for name, _ in final["timings"])
    assert [c["id"] for c in final["listings"]] == ["test_pt:1", "test_pt:2"]  # cards come from the tool
    loop_calls = [c for c in llm.calls if not c.get("response_format")]
    assert len(loop_calls) == 1 and not any(t["function"]["name"] == "search_homes" for t in loop_calls[0]["tools"] or [])


def test_offline_miss_is_an_error_not_a_crash(tmp_path):
    res = fixtures.FixtureMCP(tmp_path).call_tool("filter_listings", {"location": ["Nowhere"]})
    assert res["is_error"] and "Offline mode" in res["text"]


def test_parking_never_sent_as_false():
    got = normalize.apply(_f(location=["Lisboa"], type=["studio"], has_parking=False), "Estúdio em Lisboa com elevador")
    assert got.has_parking is None
    assert "has_parking" not in got.to_filter_args()
    kept = normalize.apply(_f(location=["Lisboa"], has_parking=None), "and under 300k",
                           _f(location=["Lisboa"], has_parking=True))
    assert kept.has_parking is True


# ---- days 6-7: card references, price/contact guards, area research ----

from agent import ordinals, tavily_tool  # noqa: E402


@pytest.mark.parametrize("msg,want", [
    ("is #2 overpriced?", 2), ("o segundo é caro?", 2), ("¿el tercero es caro?", 3),
    ("Et la deuxième ?", 2), ("Ist die erste zu teuer?", 1), ("is de laatste te duur?", 6),
    ("number 4 please", 4), ("how do I contact the agent?", None), ("at least 2 bedrooms", None),
])
def test_ordinals(msg, want):
    assert ordinals.ordinal(msg, 6) == want


def test_price_verdict_sentence_dropped_layout_kept():
    ans = "It sits within the range (€360k–€380k, 16 comparables).\nThat makes it a good deal. Is it overpriced?"
    out, n = guards.drop_price_verdicts(ans, "en")
    assert n == 1 and "good deal" not in out and "Is it overpriced?" in out
    assert out.startswith("It sits within the range") and "independent valuation" in out


def test_sent_claim_dropped():
    out, n = guards.drop_sent_claims("Ich habe dem Makler Ihre Fragen geschickt. Öffnen Sie den Link.", "de")
    assert n == 1 and "geschickt" not in out.split("\n")[0] and "noch nichts gesendet" in out


def test_select_area_vs_home_search():
    assert skills.select("Compare schools and public transport in Porto and Valencia", True) == "compare-areas"
    assert skills.select("2-bed flat near a metro station in Lisbon", False) == "find-homes"


def test_research_area_numbers_sources_and_links_citations(monkeypatch):
    monkeypatch.setattr(tavily_tool, "_search", lambda q, http: [
        {"title": f"About {q}", "url": "https://example.org/" + q.split(",")[0].lower(),
         "content": "x " * 400, "published_date": "2025-03-01"},
        {"title": "Disaster assistance", "url": "https://fema.example/public", "content": "grants"}])  # off-topic
    text, st = tavily_tool.research_area(["Porto, Portugal", "Valencia, Spain"], ["schools", "transport"], http=object())
    assert st["searches"] == 4 and set(st["sources"]) == {"S1", "S2"}  # same URL → same number
    assert "[S1] About Porto, Portugal: schools for residents (example.org, 2025-03-01)" in text
    assert "fema" not in text
    assert "https://" not in text  # the model gets numbers, not URLs
    assert max(len(line) for line in text.splitlines()) < 400
    ans = 'Porto has bilingual schools [S1]【{"id":0,"cursor":0}】. Valencia too [S1, S2]. Made up [S9].'
    out, n = tavily_tool.link_citations(ans, st["sources"])
    assert n == 3 and "【" not in out and "[S9]" not in out
    wide, nw = tavily_tool.link_citations("Porto has schools【S1】 and so does Valencia【S1，S2】.", st["sources"])
    assert nw == 3 and "schools [S1](https://example.org/porto)" in wide and "【" not in wide
    assert "[S1](https://example.org/porto) [S2](https://example.org/valencia)." in wide
    assert "[S1](https://example.org/porto)" in out and "[S2](https://example.org/valencia)" in out
    assert "**Sources**\n- [S1](https://example.org/porto)" in out
    bare, n0 = tavily_tool.link_citations("Both are fine.", st["sources"], "de")
    assert n0 == 0 and "nicht einzeln" in bare and "[S2](https://example.org/valencia)" in bare


def test_research_area_without_key_is_reported(monkeypatch):
    monkeypatch.setattr(tavily_tool.config, "TAVILY_API_KEY", "")
    monkeypatch.delenv("CUBI_OFFLINE", raising=False)
    with pytest.raises(tavily_tool.TavilyError, match="not configured"):
        tavily_tool.research_area(["Porto"], ["schools"], http=object())


def test_follow_up_resolves_card_number(tmp_path):
    agent_ = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=SimpleNamespace())
    agent_.shown = listings.parse(CARDS)
    agent_.seen_refs = {"test_pt:1", "test_pt:2"}
    agent_._message = "is the second one overpriced?"
    assert agent_._resolve_listing("test_pt:1") == ("test_pt:2", "card #2")  # the user's card wins
    agent_._message = "is it overpriced?"
    assert agent_._resolve_listing("https://cubi.estate/r/test_pt%3A1")[0] == "test_pt:1"
    assert agent_._resolve_listing("made_up:9") == (None, "unknown")
    agent_.focus = "test_pt:2"
    assert agent_._resolve_listing("made_up:9") == ("test_pt:2", "the home discussed last")


def test_new_place_starts_a_fresh_search():
    """Live 2026-10-20: a Lisbon rental made the next, Valencia purchase search a rental."""
    current = _f(location=["Lisboa"], transaction_type="rent", max_price=1500, has_parking=True)
    got = normalize.apply(_f(location=["Valencia"], transaction_type="rent", max_price=300000),
                          "Busco piso de 3 habitaciones en Valencia hasta 300.000 €", current)
    assert got.transaction_type == "sale" and got.has_parking is None
    # a refinement of the same place still keeps rent and parking
    kept = normalize.apply(_f(location=["Lisboa"], transaction_type="sale"), "and with a balcony", current)
    assert kept.transaction_type == "rent" and kept.has_parking is True


def test_connector_calls_use_this_turns_language(tmp_path):
    agent_ = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=SimpleNamespace())
    agent_.shown = listings.parse(CARDS)
    agent_.seen_refs = {"test_pt:1", "test_pt:2"}
    agent_.lang, agent_._message = "en", "How do I contact the agent for #1?"
    sent = []
    agent_.mcp.call_tool = lambda name, args: sent.append(args) or {"text": "ok", "is_error": False}
    list(agent_._run_tool("get_contact_options", {"listing_id": "test_pt:1", "lang": "nl"}))
    assert sent == [{"listing_id": "test_pt:1", "lang": "en"}]


def test_tool_failure_is_reported_as_failure(tmp_path):
    agent_ = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=SimpleNamespace())
    agent_.shown = listings.parse(CARDS)
    agent_.seen_refs = {"test_pt:1", "test_pt:2"}
    agent_.lang, agent_._message = "en", "is #2 overpriced?"
    out = list(agent_._run_tool("compare_asking_prices", {}))
    assert out[-1].startswith("error: the compare_asking_prices call failed")
    assert "do not guess" in out[-1]


def test_multi_place_search_runs_once_per_place(tmp_path):
    """Live 2026-10-21: Porto + Valencia in one filter came back all Valencia, and the
    model said Porto had nothing. Each place now gets its own search."""
    vlc = CARDS.replace("test_pt", "test_es").replace("Porto, Portugal, Porto District", "Valencia, Spain")
    agent_ = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=SimpleNamespace())
    sent = []

    def call(name, args):
        sent.append(args)
        return {"is_error": False, "text": CARDS if args["location"] == ["Porto"] else vlc}

    agent_.mcp.call_tool = call
    f = _f(location=["Porto", "Valencia"], type=["apartment"], max_price=400000)
    res, _ = _drain(agent_._filter_per_place(f.to_filter_args(limit=6), ["Porto", "Valencia"]))
    assert [a["location"] for a in sent] == [["Porto"], ["Valencia"]] and {a["limit"] for a in sent} == {3}
    cards = listings.parse(res["text"])
    assert [c["n"] for c in cards] == [1, 2, 3, 4]
    assert [c["id"] for c in cards] == ["test_pt:1", "test_pt:2", "test_es:1", "test_es:2"]
    assert "Porto: 2 shown; Valencia: 2 shown" in res["text"]
    assert "Long description" not in res["text"]


def _drain(gen):
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def test_source_date_falls_back_to_the_url():
    from agent.tavily_tool import source_date
    assert source_date({"url": "https://x.eu/news/free-sundays-2022-05-09_en"}) == "2022-05-09 (from the URL)"
    assert source_date({"url": "https://x.com/2024/03/guide"}) == "2024-03 (from the URL)"
    assert source_date({"url": "https://x.com/guide-123456"}) is None
    assert source_date({"url": "https://x.com/2022-05-09", "published_date": "2025-01-02"}) == "2025-01-02"


def test_uncited_area_answer_is_retried_once(monkeypatch, tmp_path):
    src = {"S1": {"url": "https://example.org/porto", "title": "Porto schools", "date": None}}
    monkeypatch.setattr(tavily_tool, "research_area", lambda places, topics: ("[S1] Porto schools", {
        "searches": 1, "seconds": 0.1, "sources": src}))
    llm = _ScriptedLLM([
        SimpleNamespace(content="", tool_calls=[_tool_call("research_area", {"places": ["Porto, Portugal"], "topics": ["schools"]})]),
        SimpleNamespace(content="Porto has many schools.", tool_calls=None),
        SimpleNamespace(content="Porto has many schools [S1].", tool_calls=None),
    ], "{}")
    agent_ = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=llm)
    final = list(agent_.turn("Compare schools in Porto and Valencia"))[-1]
    assert final["skill"] == "compare-areas"
    assert "[S1](https://example.org/porto)" in final["text"] and "one by one" not in final["text"]
    assert agent_.stats["citation_retries"] == 1


def test_a_place_search_asks_for_the_city_not_its_district():
    assert _f(location=["Porto"]).to_filter_args()["city_only"] is True
    assert "city_only" not in _f(location=[]).to_filter_args()


def test_fixture_keys_ignore_city_only():
    a = {"location": ["Porto"], "limit": 6}
    assert fixtures.key("filter_listings", a) == fixtures.key("filter_listings", {**a, "city_only": True})
