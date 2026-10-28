""""Villas for sale as an investment, anywhere in Europe, ideally with a pool, a
garden and a large plot" (live 2026-10-28): the plot was dropped, "land" became a
second type, and the answer repeated "as an investment" as if it had been searched."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import fixtures, listings, normalize  # noqa: E402
from agent.loop import Agent  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402

Q = "Villas for sale as an investment, anywhere in Europe, ideally with a pool, a garden and a large plot"
CARD = ("**{n}. Villa {t}**\n   Location: {t}, Spain\n   Villa | 3 bd | 200 m2{plot} | 500 000 EUR\n"
        "   URL: https://cubi.estate/r/{n}\n   ID: x:{n}\n")


def _f(**kw):
    base = dict(location=[], type=[], transaction_type="sale", min_price=None, max_price=None,
                min_bedrooms=None, max_bedrooms=None, min_living_area=None, has_parking=None,
                features=[], lang="en", needs_free_text_search=True)
    return SearchFilter(**{**base, **kw})


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


def test_a_large_plot_is_the_villas_not_a_second_type():
    assert normalize.apply(_f(type=["villa", "land"]), Q).type == ["villa"]
    assert normalize.apply(_f(type=["land"]), "Building plot in Lagos").type == ["land"]


def test_large_plot_gets_a_number_cubi_can_filter_on():
    assert normalize.plot_wish(Q) and normalize.plot_wish("Haus mit großem Grundstück")
    assert not normalize.plot_wish("villa with a big garden")
    assert normalize.with_plot_size(Q).endswith("a garden and a plot of at least 1,000 m2")


def test_investment_is_recognised():
    assert normalize.investment(Q) and normalize.investment("casa para investimento")
    assert not normalize.investment("villa with a pool in Lagos")


def test_the_free_search_sends_the_plot_size_and_marks_unknown_plots(tmp_path):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    calls = []

    def call(name, args):
        calls.append(args["query"])
        text = "Found homes.\n\n" + CARD.format(n=1, t="A", plot=" | 2400 m2 plot") + CARD.format(n=2, t="B", plot="")
        return {"is_error": False, "text": text, "structured": None}
    agent.mcp.call_tool = call
    agent.anywhere, agent.wish = True, "ideally with a pool, a garden and a large plot"
    _run(agent._free_search(Q, Q, None))
    assert all("a plot of at least 1,000 m2" in q and "large plot" not in q for q in calls)
    cards = listings.parse("Found homes.\n\n" + CARD.format(n=1, t="A", plot=" | 2400 m2 plot"))
    assert cards[0]["plot_area"] == 2400


def test_notes_tell_the_model_what_was_not_searched(tmp_path):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    notes = agent._wish_notes(Q)
    assert "plot of at least 1,000 m2" in notes and "never call it small" in notes
    assert "Do not say the homes were searched or chosen 'as an investment'" in notes
    assert "holiday-rental income, long-term rent, resale value, or own use plus letting" in notes
    assert agent._wish_notes("Villas in Lagos with a pool") == ""
