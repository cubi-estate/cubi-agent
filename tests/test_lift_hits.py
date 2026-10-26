"""Matching features show on the cards: Cubi's card line holds eight tags, the
asked-for view often sits further down, so the full detail is read (live 2026-10-26)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import fixtures, listings, normalize  # noqa: E402
from agent.loop import Agent  # noqa: E402

DETAIL = """# Villa in Perledo\n\n**Location:** Italy, Lombardy, Gittana\n\n## Description\nStunning lake views - mountain air.\n\n## Continue on Cubi\n- Ask more: https://x\n\n## Interior\n- Attic\n- Fireplace\n\n## Views\n- Green View\n- Lake View\n- Mountain view\n- Mountain view\n"""


def test_detail_tags_reads_sections_not_the_description_or_links():
    assert listings.detail_tags(DETAIL) == ["Attic", "Fireplace", "Green View", "Lake View", "Mountain view"]


def test_missing_names_the_concepts_the_cards_tags_do_not_cover():
    asked = "Houses to rent with a mountain view and near a lake"
    assert len(normalize.missing(asked, ["Gated Community"])) == 2
    assert normalize.missing(asked, ["Mountain view", "Lake View"]) == []


def _agent(tmp_path, detail):
    agent = Agent(mcp=fixtures.FixtureMCP(tmp_path), cli=object())
    calls = []

    def call(name, args):
        calls.append((name, args))
        return {"is_error": detail is None, "text": detail or "boom", "structured": None}
    agent.mcp.call_tool = call
    return agent, calls


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration:
        pass


def test_matching_tags_are_lifted_onto_the_card_first(tmp_path):
    agent, calls = _agent(tmp_path, DETAIL)
    cards = [{"n": 1, "id": "ev:1", "tags": ["Gated Community", "Optical fiber connection"]},
             {"n": 2, "id": "ev:2", "tags": ["Mountain view", "Lake View", "Pool"]}]
    _run(agent._lift_hits(cards, "Houses to rent with a mountain view and near a lake, anywhere in Europe"))
    assert [n for n, _ in calls] == ["get_listing"] and calls[0][1]["listing_id"] == "ev:1"   # #2 already shows both
    assert cards[0]["tags"][:2] == ["Lake View", "Mountain view"] and cards[0]["tags"][2] == "Gated Community"
    assert cards[1]["tags"] == ["Mountain view", "Lake View", "Pool"]
    assert agent.stats["detail_reads"] == 1


def test_no_concept_in_the_request_reads_nothing(tmp_path):
    agent, calls = _agent(tmp_path, DETAIL)
    cards = [{"n": 1, "id": "ev:1", "tags": ["Garage"]}]
    _run(agent._lift_hits(cards, "2-bedroom flats in Lisbon up to 400k"))
    assert calls == [] and cards[0]["tags"] == ["Garage"]


def test_a_failed_detail_read_leaves_the_card_as_it_was(tmp_path):
    agent, calls = _agent(tmp_path, None)
    cards = [{"n": 1, "id": "ev:1", "tags": ["Garage"]}]
    _run(agent._lift_hits(cards, "Houses with a mountain view"))
    assert len(calls) == 1 and cards[0]["tags"] == ["Garage"]
