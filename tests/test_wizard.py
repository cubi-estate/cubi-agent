"""Home wizard: listing counts (agent/wizard.py), options and countries."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import normalize, wizard  # noqa: E402


class _MCP:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def call_tool(self, name, args):
        self.calls.append(name)
        if self.fail:
            return {"is_error": True, "text": "down"}
        if name == "corpus_stats":
            body = {"active_listings": 300, "active_by_country": [{"country": "Portugal", "active": 200},
                                                                    {"country": "Malta", "active": 100}]}
            return {"is_error": False, "text": json.dumps({"result": json.dumps(body)})}
        body = {"refreshed_at": "2026-10-24 05:31 UTC",
                "countries": [{"country": "Portugal", "total7": 207}, {"country": "Ukraine", "total7": 2}]}
        return {"is_error": False, "text": json.dumps(body)}


def test_stats_join_the_two_calls_and_are_cached(monkeypatch):
    monkeypatch.setattr(wizard, "_cache", {"at": 0.0, "data": None})
    mcp = _MCP()
    s = wizard.stats(mcp)
    assert s["countries"] == {"Portugal": {"homes": 200, "new_7d": 207}, "Malta": {"homes": 100}}
    assert s["total"] == 300 and s["as_of"] == "2026-10-24 05:31 UTC"
    wizard.stats(mcp)
    assert mcp.calls == ["corpus_stats", "get_daily_new_listing_stats"]  # second read from the cache


def test_stats_failure_returns_none_then_last_good(monkeypatch):
    monkeypatch.setattr(wizard, "_cache", {"at": 0.0, "data": None})
    assert wizard.stats(_MCP(fail=True)) is None
    good = {"countries": {"Malta": {"homes": 1}}}
    monkeypatch.setattr(wizard, "_cache", {"at": 0.0, "data": good})
    assert wizard.stats(_MCP(fail=True)) == good


def test_options_cover_every_region_country_once_and_ids_are_unique():
    opt = json.loads((ROOT / "web" / "wizard" / "options.json").read_text())
    in_regions = [c for r in opt["regions"] for c in r["countries"]]
    assert sorted(in_regions) == sorted(opt["countries"])
    ids = [r["id"] for r in opt["regions"]] + [c["id"] for c in opt["countries"].values()] + \
          [x["id"] for x in opt["environments"]] + [t["id"] for t in opt["types"]] + [g["id"] for g in opt["goals"]] + \
          [f["id"] for f in opt["priorities"]]
    assert len(ids) == len(set(ids)) == 56


def test_options_tags_are_ones_the_page_knows():
    opt = json.loads((ROOT / "web" / "wizard" / "options.json").read_text())
    types = {t["id"] for t in opt["types"]}
    goals = {g["id"] for g in opt["goals"]}
    climates, lands = {"warm", "mild", "cold"}, {"coast", "mountains", "lakes"}
    for c in opt["countries"].values():
        assert c["climate"] in climates and set(c["has"]) <= lands
    for g in opt["goals"]:
        assert g["deal"] in {"sale", "rent"} and set(g.get("types", [])) <= types
    for x in opt["environments"]:
        assert x.get("needs") in lands | {None} and x["soft"], x["id"]
    tops = climates | lands | types | goals | {x["id"] for x in opt["environments"]} | {"sale", "rent"}
    for x in opt["priorities"]:
        assert x.get("needs") in lands | {None}, x["id"]
        assert set(x.get("types", [])) <= types and set(x.get("climate", [])) <= climates, x["id"]
        assert set(x.get("top", [])) <= tops and set(x.get("goals", [])) <= goals, x["id"]
        # The page merges "with ..." phrases; a condition is an adjective before the noun.
        assert ("phrase" in x) != ("pre" in x), x["id"]
        assert "land" in x.get("types", ["land"]) or x["id"] not in ("sea", "mountainview", "plot", "quiet"), x["id"]


def test_every_option_has_its_image():
    opt = json.loads((ROOT / "web" / "wizard" / "options.json").read_text())
    ids = [r["id"] for r in opt["regions"]] + [c["id"] for c in opt["countries"].values()] + \
          [x["id"] for x in opt["environments"]] + [t["id"] for t in opt["types"]] + [g["id"] for g in opt["goals"]] + \
          [f["id"] for f in opt["priorities"]]
    assert [i for i in ids if not (ROOT / "web" / "wizard" / f"{i}.jpg").exists()] == []


def test_every_wizard_country_is_a_country_to_the_agent():
    opt = json.loads((ROOT / "web" / "wizard" / "options.json").read_text())
    assert [c for c in opt["countries"] if not normalize.is_country(c)] == []
