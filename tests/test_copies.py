"""Copies of one home on a result page are collapsed: the same description text
and asking price under different ids (a Sierra Blanca villa came as three Rentola
cards at €18,000, live 2026-10-26)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import listings  # noqa: E402

DESC = ("Available from October 2026 Luxurious classic and elegant villa located in the prestigious residential "
        "community of Sierra Blanca Exceptional views from the 5 terraces")


def _card(n, cid, price, desc, bd=6, area=719):
    return (f"**{n}. Detached Villa in Nagüeles**\n   Location: 29660 Marbella, Andalusia\n"
            f"   House | {bd} bd | {area} m2 living | {price} EUR/mo\n   {desc}\n"
            f"   URL: https://cubi.estate/r/{cid}\n   ID: {cid}\n   Tags: Fireplace\n")


TEXT = ("Showing 4 properties.\n\n" + _card(1, "r:1", "2 000", "A garden house in Bistritsa with a view of Vitosha and a fireplace with water jacket")
        + _card(2, "r:2", "18 000", DESC) + _card(3, "r:3", "18 000", DESC, bd=5) + _card(4, "r:4", "18 000", DESC + " and more"))


def test_the_same_text_and_price_under_other_ids_is_one_card():
    out, groups, cards = listings.collapse(TEXT, 6)
    assert groups == {"r:2": ["r:3", "r:4"]}
    assert [c["id"] for c in cards] == ["r:1", "r:2"] and [c["n"] for c in cards] == [1, 2]
    assert "Showing 2 properties" in out and "r:3" not in out and DESC in out   # the excerpt is kept for the model


def test_different_homes_at_the_same_price_stay():
    text = "Showing 2 properties.\n\n" + _card(1, "r:1", "18 000", DESC) + _card(2, "r:2", "18 000", "A different villa entirely, with its own long description of the rooms and the garden")
    out, groups, cards = listings.collapse(text, 6)
    assert groups == {} and out == text and len(cards) == 2


def test_a_short_or_missing_excerpt_never_collapses():
    text = "Showing 2 properties.\n\n" + _card(1, "r:1", "18 000", "Villa") + _card(2, "r:2", "18 000", "Villa")
    assert listings.collapse(text, 6)[1] == {}
