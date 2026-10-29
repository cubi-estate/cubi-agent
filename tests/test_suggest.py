"""Suggested next questions (agent/suggest.py): every button must route to the
skill it advertises, in every language, and name real cards and cities."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import skills, suggest  # noqa: E402

ROUTE = {"news": "home-news", "leaders": "similar-elsewhere", "price": "check-asking-price", "contact": "contact-agent", "similar": "similar-elsewhere",
         "budget": "compare-budget", "areas": "compare-areas", "search": "find-homes", "forsale": "find-homes",
         "simpair": "similar-elsewhere", "drops": "home-news", "placenews": "home-news"}
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
    assert qs == ["Compare #1 and #2 feature by feature", "Has #1's price dropped, and what's new in Lisbon?",
                  "Is #1's price in line with similar homes?"]


def test_after_a_price_check_on_card_2_the_other_city_is_lisbon():
    qs = suggest.next_questions("check-asking-price", "de", places=["Lisbon", "Porto"], max_price=400000,
                                shown=SHOWN, focus_n=2)
    assert qs[0] == "Ist der Preis von #2 gesunken, und was gibt es Neues in Porto?"
    assert qs[1] == "Zeig mir ähnliche Wohnungen wie #2 in Lisbon"


def test_after_a_budget_comparison_the_next_budget_is_offered_first():
    qs = suggest.next_questions("compare-budget", "pt", places=["Lisboa", "Porto"], max_price=400000,
                                shown=SHOWN, budget_cap=400000)
    assert qs[0] == "E até 500 000 €?" and qs[1] == "Compara a #1 e a #2 característica a característica"


def test_one_place_offers_nothing_that_needs_two():
    # One searched place: no pair, no budget comparison; "homes like #1" goes to the
    # country's other big market (the card is in Lisboa, so Porto).
    qs = suggest.next_questions("find-homes", "en", places=["Porto"], max_price=400000, shown=SHOWN)
    assert qs == ["Has #1's price dropped, and what's new in Lisboa?", "Is #1's price in line with similar homes?",
                  "Show me homes like #1 in Porto"]


def test_nothing_on_screen_offers_no_card_questions():
    assert suggest.next_questions("compare-areas", "en", places=["Porto", "Valencia"], max_price=None,
                                  shown=[]) == []


def test_no_budget_comparison_across_countries():
    shown = [{"n": 1, "location": "Porto, Porto District, Portugal"}, {"n": 4, "location": "Valencia, Spain"}]
    qs = suggest.next_questions("find-homes", "de", places=["Porto", "Valencia"], max_price=400000, shown=shown)
    assert not any("bekommt man" in q for q in qs)
    assert qs == ["Vergleiche #1 und #4 Merkmal für Merkmal",
                  "Ist der Preis von #1 gesunken, und was gibt es Neues in Porto?",
                  "Liegt der Preis von #1 im Rahmen ähnlicher Objekte?"]


def test_leaders_need_a_card_in_each_place():
    shown = [{"n": 1, "location": "Porto, Porto District, Portugal"}, {"n": 2, "location": "Porto, Portugal"}]
    assert suggest.leaders(shown, ["Porto", "Valencia"]) is None
    assert suggest.leaders(SHOWN, ["Lisbon", "Porto"]) == (1, 2)


SHOWN_IDS = [{"n": 1, "id": "lis:1", "location": "Lisboa, Lisboa, Portugal"},
             {"n": 2, "id": "opo:2", "location": "Porto, Porto District, Portugal"}]


def test_what_was_done_on_this_listing_is_not_offered_again():
    """The screenshot case: after news and contact for #1, a price check on #1
    offered both again."""
    done = {suggest.key("news", "lis:1"), suggest.key("contact", "lis:1")}
    qs = suggest.next_questions("check-asking-price", "en", places=["Lisbon", "Porto"], max_price=500000,
                                shown=SHOWN_IDS, focus_n=1, done=done)
    assert not any("dropped" in q or "contact" in q for q in qs)
    assert qs[0] == "Show me homes like #1 in Porto" and len(qs) == 3      # the slots refill


def test_the_same_home_under_another_number_is_still_done():
    # news was asked about lis:1 when it was card #3; it is #1 now
    done = {suggest.key("news", "lis:1")}
    qs = suggest.next_questions("find-homes", "en", places=["Lisbon", "Porto"], max_price=500000,
                                shown=SHOWN_IDS, done=done)
    assert not any("dropped" in q for q in qs)


def test_a_question_typed_earlier_is_not_offered_again():
    done = {suggest.norm("compare schools and public transport in Lisbon and Porto!")}
    qs = suggest.next_questions("compare-budget", "en", places=["Lisbon", "Porto"], max_price=400000,
                                shown=SHOWN_IDS, budget_cap=400000, done=done)
    assert not any("schools" in q for q in qs)


def test_similar_in_lisboa_is_done_for_lisbon_too():
    shown = [{"n": 2, "id": "opo:2", "location": "Porto, Porto District, Portugal"}]
    done = {suggest.key("similar", "opo:2", suggest.english_city("Lisboa"))}
    qs = suggest.next_questions("check-asking-price", "en", places=["Lisbon", "Porto"], max_price=None,
                                shown=shown, focus_n=2, done=done)
    assert not any("homes like" in q for q in qs)


def test_news_is_about_the_searched_city_not_a_parish():
    card = {"n": 2, "id": "iad:1", "location": "Modivas, Vila do Conde, Porto, Portugal, Porto District"}
    assert suggest.news_place(card, ["Porto", "Valencia"]) == "Porto"
    assert suggest.news_place(card, []) == "Modivas"                       # nothing searched: the card's own
    qs = suggest.next_questions("check-asking-price", "en", places=["Porto", "Valencia"], max_price=400000,
                                shown=[card], focus_n=2)
    assert qs[0] == "Has #2's price dropped, and what's new in Porto?"


def test_news_place_is_the_city_of_an_arrondissement():
    card = {"n": 1, "location": "Lyon 8th Arrondissement, France, Auvergne-Rhône-Alpes"}
    assert suggest.news_place(card, ["Lyon"]) == "Lyon"


def test_after_an_area_comparison_three_buttons():
    """Tester F13 (27 Oct): after "Compare schools and public transport in Porto
    and Valencia" only "Homes in Porto or Valencia up to …" was offered — the
    budget comparison is not offered across countries, and nothing else was."""
    shown = [{"n": 1, "location": "Porto, Porto District, Portugal"}, {"n": 4, "location": "Valencia, Spain"}]
    qs = suggest.next_questions("compare-areas", "en", places=["Porto", "Valencia"], max_price=400000, shown=shown)
    assert qs == ["Homes in Porto or Valencia up to €400,000", "Compare #1 and #4 feature by feature",
                  "Has #1's price dropped, and what's new in Porto?"]


CARD = {"n": 3, "id": "rentola_es:1", "location": "Marbella, Andalusia, Spain"}


def test_tap_questions_cover_the_home_and_its_similar_homes():
    qs = suggest.focus_questions("en", 3, CARD, ["Marbella", "Málaga"], similar=True)
    assert [k for k, _ in qs] == ["simpair", "drops", "price", "similar", "placenews", "contact"]
    assert dict(qs)["simpair"] == "Compare #3 with its similar homes feature by feature"
    assert dict(qs)["drops"] == "Has #3's price dropped, and have its similar homes' prices dropped?"
    assert dict(qs)["placenews"] == "What's new in Marbella?"
    assert dict(qs)["contact"] == "How do I contact the agent for #3?"
    assert dict(qs)["similar"] == "Show me homes like #3 in Málaga"
    for _, q in qs:
        assert skills.select(q, has_results=True, last_skill="find-homes") in ("similar-elsewhere", "home-news", "check-asking-price", "contact-agent"), q


def test_tap_questions_without_similar_homes_and_after_a_price_check():
    qs = suggest.focus_questions("pt", 3, CARD, ["Marbella"], similar=False, done={suggest.key("price", "rentola_es:1")})
    kinds = [k for k, _ in qs]
    assert "simpair" not in kinds and "price" not in kinds
    assert dict(qs)["drops"] == "O preço da #3 baixou, e que novidades há em Marbella?"   # the plain question stands
    assert "placenews" not in kinds   # the news question would repeat it
