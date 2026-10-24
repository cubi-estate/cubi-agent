"""The step log in the user's language (agent/steps.py)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import steps  # noqa: E402


def test_steps_as_loop_writes_them_match_their_templates():
    samples = {
        "No exact matches — searching again without: Pool, Garden": "relaxed",
        "Searching listings in Porto (structured filter)": "search_place",
        "Understood: for sale · apartment · in Porto": "understood",
        "Searching listings (structured filter)": "search",
        "Counting listings within budget in Lisbon, Porto (Cubi compare_inventory)": "counting",
        "Researching Porto, Portugal on the web (Tavily): schools": "research",
        "Searching recent news about Lisbon (Tavily, last 30 days)": "news",
        "Reading recent posts about housing in Lisbon on X (last 7 days)": "x",
        "Comparing #1 and #4 feature by feature": "pair",
        "2 matching home(s) in Porto, matched on features and surroundings, not price": "matches",
        "Looking up contact options — card #1 (abc_pt:1)": "with_ref",
        "Price history: which home? (no card number or known id)": "which",
        "Budget comparison: not available right now": "na",
        "News search unavailable: timeout": "news_na",
        "Tool error: boom": "tool_error",
        "A budget comparison needs a budget": "budget_budget",
    }
    for text, key in samples.items():
        hit = steps._match(text, steps._ORDER)
        assert hit and hit[0] == key, text


def test_native_languages_cover_every_template_with_the_same_placeholders():
    for lang, t in steps.NATIVE.items():
        assert set(t) == set(steps.EN), lang
        for k, v in t.items():
            assert steps._fields(v) == steps._fields(steps.EN[k]), (lang, k)


def test_localize_keeps_the_variable_parts_and_translates_nested_labels():
    out = steps.localize("Looking up contact options — card #1 (abc_pt:1)", "de")
    assert out == "Suche Kontaktmöglichkeiten — Karte #1 (abc_pt:1)"
    assert steps.localize("Finding homes like it in Porto — card #2 (x:9)", "pt") == \
        "A procurar casas parecidas em Porto — cartão #2 (x:9)"
    assert steps.localize("Searching listings in Valencia (structured filter)", "es") == \
        "Buscando anuncios en Valencia (filtro estructurado)"
    assert steps.localize("Searching listings in Valencia (structured filter)", "en") == \
        "Searching listings in Valencia (structured filter)"
    assert steps.localize("Something new the templates don't know", "fr") == "Something new the templates don't know"
    assert steps.localize("Searching listings (structured filter)", "xx") == "Searching listings (structured filter)"


class _Cli:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply(kw)))])


def test_warm_translates_once_and_drops_templates_that_lose_a_placeholder(monkeypatch):
    monkeypatch.setattr(steps, "_RUNTIME", {})

    def reply(kw):
        src = json.loads(kw["messages"][1]["content"])
        out = {k: "IT " + v for k, v in src.items()}
        out["search_place"] = "Cerco annunci (filtro strutturato)"  # lost {place}
        return json.dumps(out)

    cli = _Cli(reply)
    steps.warm(cli, "it", "Italian", background=False)
    steps.warm(cli, "it", "Italian", background=False)
    assert len(cli.calls) == 1
    sent = json.loads(cli.calls[0]["messages"][1]["content"])
    assert "with_ref" not in sent and sent["h_card"] == "listing #{n}"   # no words to translate; no "card"
    assert steps.localize("Looking up contact options — card #1 (a:1)", "it") == \
        "IT Looking up contact options — IT listing #1 (a:1)"
    assert steps.localize("Searching listings in Roma (structured filter)", "it") == \
        "Searching listings in Roma (structured filter)"  # its template was dropped, so English


def test_warm_failure_leaves_english(monkeypatch):
    monkeypatch.setattr(steps, "_RUNTIME", {})
    steps.warm(_Cli(lambda kw: "not json"), "pl", "Polish", background=False)
    assert "pl" not in steps._RUNTIME
    assert steps.localize("Searching listings (structured filter)", "pl") == "Searching listings (structured filter)"
