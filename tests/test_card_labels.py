"""A card's labels come once, before the excerpt; the agency's text can repeat them.

Live 2026-10-26: a Marbella villa's description opened with "Location: Sierra
Blanca, Marbella Golden Mile, Marbella, Spain This beautiful…", and the card
showed that sentence as its address.
"""
from agent import listings

CARD = """Found 284 homes.

**1. 7 Bedroom luxury villa for sale in Sierra Blanca**
   Location: Calle Huerta Chica, 1 D, 29601 Marbella, Andalusia
   House | 7 bd | 1295 m2 living | 35 000 EUR/mo
   Location: Sierra Blanca, Marbella Golden Mile, Marbella, Spain This beautiful classically Andalucian styled 7 bedroom villa is located in a elevated position
   URL: https://cubi.estate/r/rentola_es%3A4135693
   ID: rentola_es:4135693
   Last changed: 2026-10-20
   Tags: Fireplace, Sea view
"""


def test_first_location_line_wins_over_the_excerpt():
    (card,) = listings.parse(CARD)
    assert card["location"] == "Calle Huerta Chica, 1 D, 29601 Marbella, Andalusia"
    assert card["id"] == "rentola_es:4135693"
    assert card["tags"] == ["Fireplace", "Sea view"]
    assert listings.places(card["location"]) == ["Marbella", "Andalusia"]


def test_excerpt_opening_with_id_or_url_does_not_override():
    # The excerpt sits before the URL and ID lines, so a look-alike there must not stick.
    text = CARD.replace("   URL: https://cubi.estate",
                        "   ID: Ref RLLVSV180367 in the agency's text\n   URL: see the agency's site\n   URL: https://cubi.estate", 1)
    (card,) = listings.parse(text)
    assert card["id"] == "rentola_es:4135693"
    assert card["url"] == "https://cubi.estate/r/rentola_es%3A4135693"


def test_postcode_before_the_town_is_not_an_address():
    assert listings.places("Rua das Flores 12, 2750-642 Cascais, Lisboa, Portugal") == ["Cascais", "Lisboa", "Portugal"]
    assert listings.places("Lipa Str, Bistrica, Sofia Region, Bulgaria") == ["Bistrica", "Sofia Region", "Bulgaria"]
