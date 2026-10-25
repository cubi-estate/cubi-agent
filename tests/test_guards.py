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
