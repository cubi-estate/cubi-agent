"""The Day-1 vision spike's own logic, offline: validation, relaxation, baseline hits."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import vision_spike as vs  # noqa: E402

vs.CALLS_PER_MIN = 10 ** 6   # no pacing in tests


def _card(n, tags, src="x"):
    return f"**{n}. Villa in Faro**\n   Villa | 3 bd | 2 ba | 200 m2 living | 700 000 EUR\n   ID: {src}:{n}\n   Tags: {tags}\n"


class _MCP:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, args):
        if name == "get_listing":                     # featured homes list their features
            return {"is_error": False, "text": "- pool\n- garden" if args["listing_id"].startswith("f:") else "- garage"}
        self.calls.append(args)
        feats = args.get("features") or []
        if "Vineyard" in feats:                       # nothing has all three
            return {"is_error": False, "text": "No listings found."}
        if feats:
            return {"is_error": False, "text": "".join(_card(i, ", ".join(feats), "f") for i in range(1, 4))}
        return {"is_error": False, "text": "".join(_card(i, "Garage", "b") for i in range(1, 4))}


def test_schema_rejects_inferred_or_unknown_attributes():
    good = {"building": "villa", "storeys": "2", "attributes": [
        {"feature": "Pool", "status": "observed", "evidence": "blue pool in front"}]}
    assert vs._validate(good) == []
    bad = {"building": "castle", "storeys": "2", "attributes": [
        {"feature": "Near the beach", "status": "observed", "evidence": ""},
        {"feature": "Pool", "status": "likely", "evidence": ""}]}
    errs = vs._validate(bad)
    assert any("building" in e for e in errs) and any("not allowed" in e for e in errs) and any("status" in e for e in errs)
    assert "Near the beach" not in vs.FEATURES and "Pool" in vs.SCHEMA["properties"]["attributes"]["items"][
        "properties"]["feature"]["enum"]


def test_only_observed_features_in_priority_order():
    res = {"result": {"attributes": [{"feature": "Garden", "status": "observed"},
                                     {"feature": "Pool", "status": "observed"},
                                     {"feature": "Sea View", "status": "uncertain"}]}}
    assert vs.observed(res) == ["Pool", "Garden"]


def test_stone_house_dropped_when_evidence_says_trim_or_cladding_panels():
    def res(ev):
        return {"result": {"attributes": [{"feature": "Stone House", "status": "observed", "evidence": ev}]}}
    assert vs.observed(res("house walls made of stone")) == ["Stone House"]
    assert vs.observed(res("stone cladding on the exterior walls")) == ["Stone House"]
    for ev in ("white stucco walls with stone trim", "stone-like pillars", "stone panels beside the windows",
               "smooth white walls, not clearly stone"):
        assert vs.observed(res(ev)) == [], ev


def test_search_relaxes_lowest_priority_feature_and_beats_baseline():
    vs._LISTING_CACHE.clear()
    mcp = _MCP()
    cards, used, _ = vs._search(mcp, {"location": ["Faro"]}, ["Pool", "Vineyard", "Garden"])
    assert used == ["Pool"] and len(cards) == 3
    assert [c.get("features") for c in mcp.calls] == [["Pool", "Vineyard"], ["Pool"]]
    assert vs._hits(mcp, cards, used) == 1.0
    base, _, _ = vs._search(mcp, {"location": ["Faro"]}, [])
    assert vs._hits(mcp, base, used) == 0.0


def test_vision_model_ids_are_recognised():
    class M:
        def __init__(self, i):
            self.id = i

    class C:
        class models:
            @staticmethod
            def list():
                return type("L", (), {"data": [M("nvidia/Nemotron-3.5-Super-VL"), M("nvidia/nemotron-3-super-120b-a12b"),
                                               M("openbmb/MiniCPM-V-4"), M("Qwen/Qwen2.5-VL-72B-Instruct")]})()

    assert vs.vision_models(C()) == ["Qwen/Qwen2.5-VL-72B-Instruct", "nvidia/Nemotron-3.5-Super-VL", "openbmb/MiniCPM-V-4"]


def test_read_photo_falls_back_to_json_object_and_sends_no_file_name(tmp_path, monkeypatch):
    p = tmp_path / "villa.jpg"
    p.write_bytes(b"jpeg")
    monkeypatch.setattr(vs, "_jpeg", lambda path: b"jpeg")
    sent = []

    class Completions:
        def create(self, **kw):
            sent.append(kw)
            if kw["response_format"]["type"] == "json_schema":
                raise ValueError("response_format json_schema not supported")
            msg = type("M", (), {"content": '```json\n{"building": "villa", "storeys": "2", "attributes": '
                                            '[{"feature": "Pool", "status": "observed", "evidence": "pool"}]}\n```'})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    cli = type("Cli", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    r = vs.read_photo(cli, "m", p)
    assert r["mode"] == "json_object" and r["errors"] == [] and vs.observed(r) == ["Pool"]
    assert "json_schema" in r["error_json_schema"] and "villa.jpg" not in str(sent)
    assert sent[-1]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_answer_key_scores_and_contrast_pairs():
    from scripts import make_photos as mp
    assert all(set(sc[3]) <= set(vs.FEATURES) and sc[1] in vs.TYPES for sc in mp.SCENES.values())
    expected = {"a.png": {"building": "villa", "storeys": "2", "features": ["Pool", "Sea View"], "pair": "p"},
                "b.png": {"building": "villa", "storeys": "2", "features": ["Sea View"], "pair": "p"}}
    rows = [{"photo": "a.png", "result": {"building": "villa"}, "observed": ["Pool", "Sea View", "Garden"]},
            {"photo": "b.png", "result": {"building": "house"}, "observed": ["Sea View"]}]
    sc = vs.score(rows, expected)
    assert sc["precision_mean"] == 0.83 and sc["recall_mean"] == 1.0 and sc["building_ok"] == 1
    assert sc["pairs"] == [{"pair": "p", "differs_in": ["Pool"], "ok": True}]
    rows[1]["observed"] = ["Sea View", "Pool"]           # sees a pool that isn't there
    assert vs.score(rows, expected)["pairs"][0]["ok"] is False


def test_synonyms_cover_every_feature_and_stay_strict():
    assert set(vs.SYNONYMS) == set(vs.FEATURES)
    assert vs.has_features("Moradia em pedra com piscina e vista mar", ["Stone House", "Pool", "Sea View"]) == {
        "Stone House": True, "Pool": True, "Sea View": True}
    assert not vs.has_features("stone floors in the kitchen", ["Stone House"])["Stone House"]


def test_coverage_counts_only_verified_homes_and_keeps_pairs_whole():
    from scripts import make_photos as mp

    class M:
        def call_tool(self, name, args):
            if name == "get_listing":
                return {"is_error": False, "text": "piscina" if args["listing_id"] == "x:1" else "garagem"}
            return {"is_error": False, "text": "".join(_card(i, "") for i in range(1, 4))}

    vs._LISTING_CACHE.clear()
    cov = mp.coverage(M(), {"location": ["Faro"]}, ["villa_pool_sea"])
    assert cov["villa_pool_sea"]["returned"] == 3 and cov["villa_pool_sea"]["verified"] == 0  # no sea view
    assert mp.core(["Terrace", "Sea View", "Pool", "Garden"]) == ["Pool", "Sea View"]
    pick = mp.select({"villa_pool_sea": 5, "villa_sea": 1, "townhouse_terrace": 4}, 3, 8)
    assert pick == ["townhouse_terrace"]


def test_rate_limited_call_waits_and_retries_once(monkeypatch):
    slept = []
    monkeypatch.setattr(vs.time, "sleep", lambda s: slept.append(s))
    replies = [{"is_error": True, "text": "Too many tool calls from this deployment in the last minute."},
               {"is_error": False, "text": "ok"}]

    class M:
        def call_tool(self, name, args):
            return replies.pop(0)

    assert vs.call(M(), "filter_listings", {})["text"] == "ok" and 61 in slept


def test_verify_puts_homes_that_state_the_features_first_and_stops_at_three():
    vs._LISTING_CACHE.clear()
    texts = {"a:1": "garage", "a:2": "piscina e jardim", "a:3": "pool, garden", "a:4": "pool only",
             "a:5": "jardim, piscina", "a:6": "piscina, jardim"}

    class M:
        n = 0

        def call_tool(self, name, args):
            M.n += 1
            return {"is_error": False, "text": texts[args["listing_id"]]}

    cards = [{"id": f"a:{i}"} for i in range(1, 7)]
    out, ok, part, checked = vs.verify(M(), cards, ["Pool", "Garden"])
    assert [c["id"] for c in out[:3]] == ["a:2", "a:3", "a:5"] and (ok, part, checked) == (3, 0, 5) and M.n == 5
    assert vs.verify(M(), cards, []) == (cards, 0, 0, 0)


def test_partial_matches_fill_the_gap_and_say_what_is_missing():
    vs._LISTING_CACHE.clear()
    texts = {"b:1": "garage", "b:2": "piscina", "b:3": "pool and garden", "b:4": "pool", "b:5": "jardim"}

    class M:
        def call_tool(self, name, args):
            return {"is_error": False, "text": texts[args["listing_id"]]}

    out, ok, part, checked = vs.verify(M(), [{"id": f"b:{i}"} for i in range(1, 6)], ["Pool", "Garden"])
    assert [c["id"] for c in out[:3]] == ["b:3", "b:2", "b:4"] and (ok, part, checked) == (1, 2, 5)
    assert [vs.label(c) for c in out[:3]] == ["", "garden not mentioned", "garden not mentioned"]
    assert out[3]["match"] == "none"    # garden only: never shown as a match for a pool photo


def test_unspecified_water_counts_as_sea_view_and_says_so():
    t = "## Views\n- Sea or lake view (unspecified water)\n- private pool"
    assert vs.has_features(t, ["Sea View", "Pool"]) == {"Sea View": True, "Pool": True}
    assert vs.water_note(t, ["Sea View"]) == vs.WATER_NOTE
    assert vs.water_note(t + "\nVista mar", ["Sea View"]) == ""         # it does say sea elsewhere
    assert not vs.has_features("terrace overlooking the Douro River", ["Sea View"])["Sea View"]
    assert vs.label({"match": "full", "missing": [], "note": vs.WATER_NOTE}) == vs.WATER_NOTE
