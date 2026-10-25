"""Wishes after "ideally" are not filter features (agent/normalize.py SOFT), and
the answer guard drops "all … furnishings" claims (agent/guards.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import guards, normalize  # noqa: E402
from agent.schema import SearchFilter  # noqa: E402


def _f(**kw):
    base = dict(location=["Portugal"], type=["house"], transaction_type="sale", min_price=None, max_price=None,
                min_bedrooms=None, max_bedrooms=None, min_living_area=None, has_parking=None, features=[],
                lang="en", needs_free_text_search=False)
    return SearchFilter(**{**base, **kw})


def test_wishes_after_ideally_are_not_features():
    # Live 2026-10-25: Nemotron listed the wizard's wishes as features.
    msg = ("Houses for sale in Portugal with a garden up to €700,000, ideally with a sea view, "
           "in quiet countryside and in a family-friendly area near schools")
    f = normalize.apply(_f(features=["Garden", "Sea View", "sea_view", "quiet_countryside", "family_friendly", "near_schools"]), msg)
    assert f.features == ["Garden"]


def test_requirement_before_the_wish_is_kept_in_any_language():
    # The model's own translation ("Fireplace" for "lareira") stays; the wish ("piscina") goes.
    f = normalize.apply(_f(features=["Fireplace", "Pool"], lang="pt"),
                        "Moradia em Sintra com lareira, idealmente com piscina")
    assert f.features == ["Fireplace"]


def test_a_wish_named_in_english_after_the_cue_goes_too():
    f = normalize.apply(_f(features=["Fireplace", "Sauna"]), "House in Sintra with a fireplace, ideally with a sauna")
    assert f.features == ["Fireplace"]


def test_without_a_wish_cue_the_model_features_still_count():
    f = normalize.apply(_f(features=["Fireplace", "Sea View"]), "House in Sintra with a fireplace and a sea view")
    assert f.features == ["Sea View", "Fireplace"]


def test_guard_drops_all_listed_include_furnishings():
    text = ("Over 1,000 matches were found; here are six examples. All listed studios include furnishings and "
            "basic amenities like Wi-Fi. You can refine by town.")
    out, n = guards.drop_all_have_claims(text)
    assert n == 1 and "furnishings" not in out and "refine by town" in out
