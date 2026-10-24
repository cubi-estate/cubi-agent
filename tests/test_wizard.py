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
          [t["id"] for t in opt["types"]] + [f["id"] for f in opt["features"]]
    assert len(ids) == len(set(ids)) == 32


def test_every_wizard_country_is_a_country_to_the_agent():
    opt = json.loads((ROOT / "web" / "wizard" / "options.json").read_text())
    assert [c for c in opt["countries"] if not normalize.is_country(c)] == []
