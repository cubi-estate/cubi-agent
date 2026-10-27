"""guards.drop_all_have_claims: no claim that every home has a wish."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import guards  # noqa: E402


def test_claims_that_every_home_has_a_wish_are_dropped():
    # Live 2026-10-24: cards #1 and #2 listed neither a terrace nor a lift.
    a = "Found six listings. All meet the basic criteria—three bedrooms, renovation notes, and a terrace. Ask for #2."
    assert guards.drop_all_have_claims(a) == ("Found six listings. Ask for #2.", 1)
    out, report = guards.apply("Found 196. The first six all include elevator/lift and AC. Ask away.", "", "en", {"search_homes"})
    assert out == "Found 196. Ask away." and report["all_have_claims_dropped"] == 1
    assert guards.drop_all_have_claims("Encontrei 5. Todas têm piscina. Diga.")[1] == 1


def test_bounds_and_counts_with_all_are_kept():
    for a in ("All are below your budget of €700,000.", "All six are in Porto.", "The pool at #2 is heated."):
        assert guards.drop_all_have_claims(a) == (a, 0)


def test_model_reasoning_never_reaches_the_user():
    # Live (iteration 8, bc5b4db): 'Is #9 overpriced?' with six cards on screen.
    leaked = ("We don't have #9 listed. Need clarify. Probably nonexistent. Tell user we only have up to #6."
              "</think>\n\nThere is no #9 here — which of #1–#6 do you mean?")
    assert guards.strip_reasoning(leaked) == ("There is no #9 here — which of #1–#6 do you mean?", 1)
    assert guards.strip_reasoning("<think>notes</think>Answer.") == ("Answer.", 1)
    assert guards.strip_reasoning("<think>notes never closed") == ("", 1)
    assert guards.strip_reasoning("Plain answer.") == ("Plain answer.", 0)
    out, report = guards.apply("Notes.</think>Which card do you mean?", "", "en", set())
    assert out == "Which card do you mean?" and report["reasoning_stripped"] == 1


def test_bare_yes_or_no_is_a_price_verdict():
    # Live (iteration 8): "Is #1 a good deal? Just answer yes or no." → "No."
    out, n = guards.drop_price_verdicts("No.", "en")
    assert n == 1 and out.startswith("Whether it is a good buy")
    out, n = guards.drop_price_verdicts("Não. O preço está dentro do intervalo.", "pt")
    assert n == 1 and out.startswith("O preço está dentro do intervalo.")
    assert guards.drop_price_verdicts("No comparable homes were found.", "en") == ("No comparable homes were found.", 0)


def test_valuation_line_only_after_a_comparison():
    asked, _ = guards.apply("Which card do you mean?", "error: the user has not said which home", "en",
                            {"compare_asking_prices"})
    assert asked == "Which card do you mean?"
    out, _ = guards.apply("It sits mid-range.", '{"kind": "asking_price_comparison"}', "en", {"compare_asking_prices"})
    assert out.endswith("not a valuation.")


def test_listing_ids_never_reach_the_answer():
    cards = ["acasadajoana_pt:26471243", "afinest_pt:25505032"]
    out, n = guards.scrub_ids("The asking price for #2 (afinest_pt:25505032) is €447,500.", cards)
    assert out == "The asking price for #2 is €447,500." and n == 1
    out, _ = guards.scrub_ids("Listing acasadajoana_pt:26471243 has a balcony; portadafrente:a0cTg00000L7ItoIAF does not.", cards)
    assert out == "#1 has a balcony; this home does not."
    out, _ = guards.scrub_ids("Tell me the card number (e.g., #1) or the exact listing ID of the apartment.", cards)
    assert out == "Tell me the card number (e.g., #1) of the apartment."


def test_id_scrub_leaves_links_times_and_prices_alone():
    text = "See [the listing](https://www.idealista.pt/imovel/123/) at 10:30 — €410,000, ratio 3:1."
    assert guards.scrub_ids(text, []) == (text, 0)


_PLN = """Your search: Poland · house · budget up to 1,757,800 PLN — found 74 matching properties.

**1. Dom Zegrze**
   Location: Nieporęt, Masovian Voivodeship
   House | 191 m2 living | 1 750 000 PLN
   URL: https://cubi.estate/r/otodom_pl%3A1
   ID: otodom_pl:1

**2. Słoneczny Taras nad Jeziorem**
   Location: Łowyń, Greater Poland Voivodeship
   House | 2 ba | 228 m2 living | 999 999 PLN
   URL: https://cubi.estate/r/metrohouse_pl%3A2
   ID: metrohouse_pl:2
"""


def test_over_budget_claims_go_when_every_card_is_within_the_stated_cap():
    # Live 2026-10-25: złoty prices read against a €400,000 budget.
    a = ("Found 74 listings. Many exceed the budget, but #5 mentions a lake view, while others like #2 "
         "also highlight lakeside locations though above the limit. Ask for details on any home.")
    out, n = guards.drop_false_over_budget(a, _PLN)
    assert out == "Found 74 listings. Ask for details on any home." and n == 1  # both claims sat in one sentence
    out, report = guards.apply(a, _PLN, "en", {"search_homes"})
    assert report["over_budget_dropped"] == 1 and "limit" not in out


def test_over_budget_claims_stay_when_a_card_really_is_above_the_cap():
    above = _PLN.replace("1 750 000 PLN", "1 950 000 PLN")
    a = "Found 74. #1 is above the limit. Ask away."
    assert guards.drop_false_over_budget(a, above) == (a, 0)
    assert guards.drop_false_over_budget(a, "no cap stated here") == (a, 0)


LYON = ("J'ai trouvé 6 logements à vendre à Lyon. Voici les six biens :\n\n"
        "1. Appartement T3, 68 m², 2 chambres — 289 000 €\n"
        "2. Appartement T2, 45 m² — 215 000 €\n"
        "3. Maison, 120 m², 4 chambres — 640 000 €\n"
        "4. Studio, 22 m² — 129 000 €\n\n"
        "Dites-moi si vous voulez plus de détails sur l'un d'eux.")


def test_a_list_of_the_homes_on_the_cards_is_dropped():
    """Tester F22/F8: the cards already show the six homes; the text listed them again."""
    out, n = guards.drop_listed_homes(LYON)
    assert n == 4 and "289 000" not in out and "Voici" not in out
    assert out.startswith("J'ai trouvé 6 logements") and out.endswith("l'un d'eux.")
    _, rep = guards.apply(LYON, "", "fr", {"search_homes"})
    assert rep["listed_homes_dropped"] == 4


def test_short_lists_and_lists_without_homes_stay():
    two = "Two stand out:\n\n1. #1 at €289,000\n2. #4 at €129,000\n\nWant details?"
    assert guards.drop_listed_homes(two) == (two, 0)
    tips = "You could:\n- add a town\n- raise the budget\n- allow 1 bedroom less"
    assert guards.drop_listed_homes(tips) == (tips, 0)


def test_an_answer_that_is_only_the_list_is_kept():
    only = "\n".join(LYON.splitlines()[2:6])
    assert guards.drop_listed_homes(only) == (only, 0)
