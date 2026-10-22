"""Suggested next questions (agent/suggest.py): every button must route to the
skill it advertises, in every language, and name real cards and cities."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import skills, suggest  # noqa: E402

ROUTE = {"leaders": "similar-elsewhere", "price": "check-asking-price", "contact": "contact-agent", "similar": "similar-elsewhere",
         "budget": "compare-budget", "areas": "compare-areas", "search": "find-homes"}
FILL = dict(n=2, m=4, city="Porto", a="Lisboa", b="Porto")


@pytest.mark.parametrize("lang", sorted(suggest.T))
@pytest.mark.parametrize("kind", sorted(ROUTE))
def test_every_template_routes_to_its_skill(lang, kind):
    q = suggest.T[lang][kind].format(p=suggest.money(400000, lang), **FILL)
    assert skills.select(q, has_results=True, last_skill="find-homes") == ROUTE[kind], q


@pytest.mark.parametrize("lang", sorted(suggest.T))
def test_next_budget_routes_as_a_refinement(lang):
    q = suggest.T[lang]["more"].format(p=suggest.money(500000, lang))
    assert skills.select(q, has_results=True, last_skill="compare-budget") == "compare-budget", q


SHOWN = [{"n": 1, "location": "Lisboa, Lisboa, Portugal"}, {"n": 2, "location": "Porto, Porto District, Portugal"}]


def test_after_a_search():
    qs = suggest.next_questions("find-homes", "en", places=["Lisbon", "Porto"], max_price=400000, shown=SHOWN)
    assert qs == ["Compare #1 and #2 feature by feature", "Is #1's price in line with similar homes?",
                  "What does €400,000 buy in Lisbon vs Porto?"]


def test_after_a_price_check_on_card_2_the_other_city_is_lisbon():
    qs = suggest.next_questions("check-asking-price", "de", places=["Lisbon", "Porto"], max_price=400000,
                                shown=SHOWN, focus_n=2)
    assert qs[0] == "Zeig mir ähnliche Wohnungen wie #2 in Lisbon"
    assert qs[1] == "Wie erreiche ich den Makler von #2?"


def test_after_a_budget_comparison_the_next_budget_is_offered_first():
    qs = suggest.next_questions("compare-budget", "pt", places=["Lisboa", "Porto"], max_price=400000,
                                shown=SHOWN, budget_cap=400000)
    assert qs[0] == "E até 500 000 €?" and qs[1] == "Compara a #1 e a #2 característica a característica"


def test_one_place_offers_nothing_that_needs_two():
    qs = suggest.next_questions("find-homes", "en", places=["Porto"], max_price=400000, shown=SHOWN)
    assert qs == ["Is #1's price in line with similar homes?"]


def test_nothing_on_screen_offers_no_card_questions():
    assert suggest.next_questions("compare-areas", "en", places=["Porto", "Valencia"], max_price=None,
                                  shown=[]) == []


def test_no_budget_comparison_across_countries():
    shown = [{"n": 1, "location": "Porto, Porto District, Portugal"}, {"n": 4, "location": "Valencia, Spain"}]
    qs = suggest.next_questions("find-homes", "de", places=["Porto", "Valencia"], max_price=400000, shown=shown)
    assert not any("bekommt man" in q for q in qs)
    assert qs == ["Vergleiche #1 und #4 Merkmal für Merkmal", "Liegt der Preis von #1 im Rahmen ähnlicher Objekte?",
                  "Zeig mir ähnliche Wohnungen wie #1 in Valencia"]


def test_leaders_need_a_card_in_each_place():
    shown = [{"n": 1, "location": "Porto, Porto District, Portugal"}, {"n": 2, "location": "Porto, Portugal"}]
    assert suggest.leaders(shown, ["Porto", "Valencia"]) is None
    assert suggest.leaders(SHOWN, ["Lisbon", "Porto"]) == (1, 2)
