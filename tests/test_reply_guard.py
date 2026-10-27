"""reply_guard: a Cubi question is never relayed as "no listings" (2026-10-27)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import reply_guard as rg  # noqa: E402

# The incident: "Homes for sale, anywhere in Europe" → Cubi asked where.
CLARIFY_TEXT = ("No properties matched. Suggest the user broaden the budget, change location, "
                "or relax feature requirements.\n---\n"
                "Europe is a big place! Which country or region would you like to search — "
                "for example Portugal, Spain or Italy?")
# After the connector fix: the same question without the no-match line.
CLARIFY_NO_PREFIX = "Europe is a big place! Which country or region would you like to search?"
GENUINE_ZERO = ("Your search: Faro, Portugal · villa · budget up to 50,000 EUR — no matches found.\n---\n"
                "Nothing at that price — want me to raise the budget?")
FILTER_ZERO = ("No properties matched these filters.\n\n_Cubi request id: req_4d7feccd593b — pass it as "
               "`parent_request_id` when you fetch one of these listings, so the read is tied to this search._\n")
RESULTS = ("Your search: Lisbon · apartment — found 812 matching properties.\n\n"
           "**1. Bright 2-bed in Alfama**\n   €420,000 · 2 bed\n   URL: https://cubi.estate/r/idealista%3A123\n"
           "   ID: idealista:123\n")


def r(text, **kw):
    return {"text": text, "is_error": False, "structured": None, **kw}


# --- incoming ---------------------------------------------------------------

def test_the_incident_reply_is_a_question_not_a_zero():
    rep = rg.classify(r(CLARIFY_TEXT))
    assert rep.kind == rg.CLARIFY and rep.question.startswith("Europe is a big place!")
    assert "No properties matched" not in rep.question


def test_a_question_without_the_prefix_is_still_a_question():
    assert rg.classify(r(CLARIFY_NO_PREFIX)).kind == rg.CLARIFY


def test_genuine_zeros_from_both_tools():
    assert rg.classify(r(GENUINE_ZERO)).kind == rg.ZERO     # summary says so, even with a follow-up question
    assert rg.classify(r(FILTER_ZERO)).kind == rg.ZERO      # filter_listings' zero


def test_results_errors_and_structured():
    assert rg.classify(r(RESULTS)).kind == rg.RESULTS
    assert rg.classify(r("timeout", is_error=True)).kind == rg.ERROR
    assert rg.classify(r("", structured={"count": 0, "summary": "Your search: X — no matches found.",
                                         "listings": []})).kind == rg.ZERO
    assert rg.classify(r("", structured={"count": 197, "listings": [{"id": "a:1"}]})).kind == rg.RESULTS


# --- outgoing ---------------------------------------------------------------

def test_a_zero_claim_after_a_question_becomes_the_question():
    reps = [rg.classify(r(CLARIFY_TEXT))]
    out, rep = rg.guard_answer("Sorry, there are no listings for that. Try another search.", reps, "en")
    assert "no listings" not in out and rep["zero_claims_cut"] == 1
    assert out.endswith("Which country or region would you like to search — for example Portugal, Spain or Italy?")


def test_a_genuine_zero_may_be_said():
    reps = [rg.classify(r(GENUINE_ZERO))]
    a = "No homes match a villa in Faro under €50,000. Want me to raise the budget?"
    assert rg.guard_answer(a, reps, "en") == (a, {"zero_claims_cut": 0, "markers_stripped": 0, "ids_stripped": 0})


def test_zero_claims_are_cut_in_other_languages_and_with_results():
    clar = [rg.classify(r(CLARIFY_NO_PREFIX))]
    out, _ = rg.guard_answer("Não encontrei nenhum imóvel. Diga-me mais.", clar, "pt")
    assert "nenhum imóvel" not in out
    out, rep = rg.guard_answer("Keine Treffer gefunden.", clar, "de")
    assert "Keine Treffer" not in out and rep["zero_claims_cut"] == 1 and out.endswith("?")
    # Cards came back: a "no listings" sentence is wrong, the rest stays.
    out, _ = rg.guard_answer("Here are six homes in Lisbon. No listings in Alfama though.",
                             [rg.classify(r(RESULTS))], "en")
    assert out == "Here are six homes in Lisbon."


def test_markers_headers_and_bare_ids_are_stripped_but_links_kept():
    a = ("Here is #1 (idealista:123): https://cubi.estate/r/idealista%3A123\n"
         "[searched with search_properties (free text)]\n<!-- CUBI_HISTORY: [] -->")
    out, rep = rg.guard_answer(a, [rg.classify(r(RESULTS))], "en")
    assert "idealista:123)" not in out and "https://cubi.estate/r/idealista%3A123" in out
    assert "CUBI_HISTORY" not in out and "searched with" not in out
    assert rep["markers_stripped"] == 2 and rep["ids_stripped"] == 1


def test_ordinary_answers_pass_unchanged():
    a = "#2 has a terrace and is 10 minutes from the beach. Shall I compare it with #4?"
    assert rg.guard_answer(a, [rg.classify(r(RESULTS))], "en")[0] == a


def test_a_turn_without_a_search_is_not_policed():
    a = "There are no homes on screen yet. Search first, then ask about a card."
    assert rg.guard_answer(a, [], "en")[0] == a
