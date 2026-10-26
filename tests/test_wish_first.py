"""A wish ("ideally with a mountain view") is searched as a requirement first:
Cubi only ranks on wishes, and a Europe-wide page showed none with it (live 2026-10-26)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import fixtures, listings  # noqa: E402
from agent.loop import Agent  # noqa: E402

CARD = "**{n}. House for rent {t}**\n   Location: {t}, Spain\n   3 bd | 1 500 EUR / month\n   URL: https://cubi.estate/r/{n}\n   ID: x:{n}\n   Tags: Mountain view, Fireplace\n"
INCOMPLETE = json.dumps({"is_error": True, "code": "search_incomplete"})


def _cards(n):
    return "Found homes.\n\n" + "".join(CARD.format(n=i, t=f"Town{i}") for i in range(1, n + 1))


def _agent(tmp_path, reply):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    calls = []

    def call(name, args):
        calls.append(args["query"])
        text = reply(args["query"])
        return {"is_error": text.lstrip().startswith("{"), "text": text, "structured": None}
    agent.mcp.call_tool = call
    agent.anywhere, agent.wish = True, "ideally with a mountain view and a fireplace, furnished"
    return agent, calls


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


Q = "Houses to rent in the mountains, anywhere in Europe, ideally with a mountain view and a fireplace, furnished"


def test_the_wishes_run_as_requirements_when_enough_homes_have_them(tmp_path):
    agent, calls = _agent(tmp_path, lambda q: _cards(1) if "ideally" in q else _cards(4))
    res, header = _run(agent._free_search(Q, Q, None))
    assert calls == ["Houses to rent in the mountains, anywhere in Europe, with a mountain view and a fireplace, furnished"]
    assert len(listings.parse(res["text"])) == 4
    assert 'every home here meets "ideally with a mountain view and a fireplace, furnished"' in header
    assert "would show more" in header


def test_too_few_with_all_wishes_falls_back_to_the_wish_search(tmp_path):
    agent, calls = _agent(tmp_path, lambda q: _cards(6) if "ideally" in q else _cards(2))
    res, header = _run(agent._free_search(Q, Q, None))
    assert len(calls) == 2 and "ideally" not in calls[0] and "ideally" in calls[1]
    assert len(listings.parse(res["text"])) == 6 and "as requirements" not in header


def test_a_timed_out_requirement_search_goes_straight_to_the_wish_search(tmp_path):
    agent, calls = _agent(tmp_path, lambda q: _cards(6) if "ideally" in q else INCOMPLETE)
    res, header = _run(agent._free_search(Q, Q, None))
    assert len(calls) == 2 and not res["is_error"] and not agent.split   # no per-market run for the attempt


def test_no_wish_means_one_search(tmp_path):
    agent, calls = _agent(tmp_path, lambda q: _cards(6))
    agent.wish = ""
    q = "Houses to rent in the mountains, anywhere in Europe"
    _run(agent._free_search(q, q, None))
    assert calls == [q]
