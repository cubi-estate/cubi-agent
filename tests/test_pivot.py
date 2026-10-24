"""Any language through English (agent/pivot.py): offline, with a fake Token Factory."""
import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, pivot, suggest  # noqa: E402
from agent.lang import LANGS, needs_check  # noqa: E402
from agent.loop import Agent  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402

CARDS = """Showing 1 properties.

**1. Bright flat**
   Location: Bonfim, Porto, Portugal, Porto District
   Apartment | 2 bd | 1 ba | 88 m2 living | 310 000 EUR
   URL: https://cubi.estate/r/test_pt%3A1
   ID: test_pt:1
"""
URL = "https://cubi.estate/r/test_pt%3A1"


def test_six_languages_never_trigger_a_check():
    cases = [json.loads(line) for line in (ROOT / "evals" / "filter_extraction.jsonl").read_text().splitlines()]
    assert [c["q"] for c in cases if needs_check(c["q"])] == []
    fill = defaultdict(lambda: "Porto", n=2, m=3, p="€400k", city="Porto", a="Porto", b="Valencia")
    chips = [t.format_map(fill) for lang in LANGS for t in suggest.T[lang].values()]
    assert [c for c in chips if needs_check(c)] == []
    for t in ("Has #2's price dropped?", "And up to 500k?", "Villa avec piscine à Nice jusqu'à 2 millions"):
        assert not needs_check(t), t


def test_other_languages_trigger_a_check():
    for t in ("Appartamento con piscina a Roma", "Mieszkanie w Krakowie do 500 tys", "lägenhet i Stockholm med balkong",
              "Квартира в Лиссабоне до 400 тысяч", "Διαμέρισμα στη Λισαβόνα", "里斯本的公寓", "e il secondo?"):
        assert needs_check(t), t


class _LLM:
    """Routes by call: language naming, back-translation, filter extraction, loop."""

    def __init__(self, ident, loop_answer, back=None):
        self.ident, self.loop_answer, self.back = ident, loop_answer, back
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(kw)
        system = kw["messages"][0]["content"]
        if system == pivot.IDENTIFY:
            content = json.dumps(self.ident)
        elif system.startswith(pivot.BACK.split("{name}")[0]):
            src = json.loads(kw["messages"][1]["content"])
            content = json.dumps(self.back(src)) if self.back else "not json"
        elif kw.get("response_format"):
            f = SearchFilter(location=["Porto"], type=["apartment"], transaction_type="sale", max_price=400000,
                             min_bedrooms=2, features=[], lang="en", needs_free_text_search=False, min_price=None,
                             max_bedrooms=None, min_living_area=None, has_parking=None)
            content = f.model_dump_json()
        else:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.loop_answer,
                                                                                     tool_calls=None))],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    def kinds(self):
        out = []
        for c in self.calls:
            s = c["messages"][0]["content"]
            out.append("identify" if s == pivot.IDENTIFY else "back" if s.startswith("Translate every") else
                       "extract" if c.get("response_format") else "loop")
        return out


def _agent(tmp_path, llm, lang="en"):
    f = SearchFilter(location=["Porto"], type=["apartment"], transaction_type="sale", max_price=400000,
                     min_bedrooms=2, features=[], lang="en", needs_free_text_search=False, min_price=None,
                     max_bedrooms=None, min_living_area=None, has_parking=None)
    args = {**f.to_filter_args(limit=6), "lang": lang}
    rec = {"tool": "filter_listings", "args": args, "is_error": False, "text": CARDS}
    (tmp_path / f"{fixtures.key('filter_listings', args)}.json").write_text(json.dumps(rec))
    return Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=llm)


def _italian(src):
    return {"answer": src["answer"].replace("Here is one flat", "Ecco un appartamento"),
            "suggestions": [f"IT: {s}" for s in src["suggestions"]]}


def test_italian_runs_in_english_and_comes_back_in_italian(tmp_path):
    llm = _LLM({"lang": "it", "name": "Italian", "english": "2-bed apartment in Porto under 400k"},
               f"Here is one flat: {URL}", _italian)
    agent = _agent(tmp_path, llm)
    final = list(agent.turn("Bilocale a Porto fino a 400 mila"))[-1]
    assert llm.kinds() == ["identify", "extract", "loop", "back"]
    extract_msg = json.dumps(llm.calls[llm.kinds().index("extract")]["messages"], ensure_ascii=False)
    assert "2-bed apartment in Porto under 400k" in extract_msg and "Bilocale" not in extract_msg
    assert final["text"] == f"Ecco un appartamento: {URL}" and final["lang"] == "it" and final["via"] == "en"
    assert final["suggestions"] and all(s.startswith("IT: ") for s in final["suggestions"])
    assert [c["id"] for c in final["listings"]] == ["test_pt:1"]
    assert [t for t, _ in final["timings"]][0] == "identify language" and final["timings"][-1][0] == "translate back"
    assert agent.history[0]["content"] == "2-bed apartment in Porto under 400k"  # the model's memory stays English

    # The translated button runs its English original, with no naming call.
    chip = next(c for c in final["suggestions"] if c.startswith("IT: Is #"))  # the price check: no web call
    before = len(llm.calls)
    list(agent.turn(chip))
    assert "identify" not in llm.kinds()[before:]
    assert [m["content"] for m in agent.history if m["role"] == "user"][-1] == chip[len("IT: "):]


def test_russian_asks_cubi_in_russian(tmp_path):
    llm = _LLM({"lang": "ru", "name": "Russian", "english": "2-bed apartment in Porto under 400k"},
               f"Here is one flat: {URL}", _italian)
    agent = _agent(tmp_path, llm, lang="ru")
    final = list(agent.turn("Двушка в Порту до 400 тысяч"))[-1]
    assert final["lang"] == "ru" and agent.data_lang == "ru" and agent.lang == "en"
    assert agent.mcp.calls[-1]["tool"] == "filter_listings" and not agent.mcp.calls[-1]["is_error"]


def test_a_translation_that_changes_a_link_is_not_shown(tmp_path):
    bad = lambda src: {"answer": "Ecco: https://evil.example/x", "suggestions": src["suggestions"]}  # noqa: E731
    llm = _LLM({"lang": "it", "name": "Italian", "english": "2-bed apartment in Porto under 400k"},
               f"Here is one flat: {URL}", bad)
    final = list(_agent(tmp_path, llm).turn("Bilocale a Porto fino a 400 mila"))[-1]
    assert final["text"].startswith(f"Here is one flat: {URL}") and final["text"].endswith(pivot.NOTE)
    assert "evil" not in final["text"]


def test_a_failed_back_translation_shows_english_with_a_note(tmp_path):
    llm = _LLM({"lang": "it", "name": "Italian", "english": "2-bed apartment in Porto under 400k"},
               f"Here is one flat: {URL}", None)
    agent = _agent(tmp_path, llm)
    final = list(agent.turn("Bilocale a Porto fino a 400 mila"))[-1]
    assert final["text"].endswith(pivot.NOTE) and agent.stats["pivot_failures"] == 1


def test_a_check_that_names_one_of_the_six_runs_natively(tmp_path):
    llm = _LLM({"lang": "es", "name": "Spanish", "english": "ignored"}, f"Aquí tienes un piso: {URL}")
    final = list(_agent(tmp_path, llm).turn("Appartamento con piscina a Porto"))[-1]
    assert final["lang"] == "es" and "via" not in final and "back" not in llm.kinds()


def test_a_bare_reference_keeps_the_conversation_in_its_language(tmp_path):
    llm = _LLM({"lang": "it", "name": "Italian", "english": "2-bed apartment in Porto under 400k"},
               f"Here is one flat: {URL}", _italian)
    agent = _agent(tmp_path, llm)
    list(agent.turn("Bilocale a Porto fino a 400 mila"))
    before = len(llm.calls)
    final = list(agent.turn("Porto"))[-1]
    assert final["lang"] == "it" and llm.kinds()[before:][-1] == "back" and "identify" not in llm.kinds()[before:]


def test_english_makes_no_translation_calls(tmp_path):
    llm = _LLM({}, f"Here is one flat: {URL}")
    final = list(_agent(tmp_path, llm).turn("2-bed apartment in Porto under 400k"))[-1]
    assert llm.kinds() == ["extract", "loop"] and final["lang"] == "en"
