"""The Day-1 vision spike's own logic, offline: validation, relaxation, baseline hits."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import vision_spike as vs  # noqa: E402


def _card(n, tags):
    return f"**{n}. Villa in Faro**\n   Villa | 3 bd | 2 ba | 200 m2 living | 700 000 EUR\n   ID: x:{n}\n   Tags: {tags}\n"


class _MCP:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, args):
        self.calls.append(args)
        feats = args.get("features") or []
        if "Vineyard" in feats:                       # nothing has all three
            return {"is_error": False, "text": "No listings found."}
        if feats:
            return {"is_error": False, "text": "".join(_card(i, ", ".join(feats)) for i in range(1, 4))}
        return {"is_error": False, "text": "".join(_card(i, "Garage") for i in range(1, 4))}


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


def test_search_relaxes_lowest_priority_feature_and_beats_baseline():
    mcp = _MCP()
    cards, used, _ = vs._search(mcp, {"location": ["Faro"]}, ["Pool", "Garden", "Vineyard", "Patio"])
    assert used == ["Pool", "Garden"] and len(cards) == 3
    assert [c.get("features") for c in mcp.calls] == [["Pool", "Garden", "Vineyard"], ["Pool", "Garden"]]
    base, _, _ = vs._search(mcp, {"location": ["Faro"]}, [])
    assert vs._hits(cards, used) == 1.0 and vs._hits(base, used) == 0.0


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
