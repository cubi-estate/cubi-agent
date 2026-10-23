"""Day-1 go/no-go for "find your home from a photo": can a vision model on Token
Factory turn an inspiration photo into atlas features that find real homes?

Gates (oracle council, 2026-10-23):
  1. a vision model is served to this account (GET /v1/models) and answers a real
     image call: not a catalogue entry, a working call;
  2. it returns schema-valid JSON using only allowlisted, *visible* attributes
     (no location, climate, season or travel times from pixels);
  3. end-to-end latency per photo is measured (p50 and max), to set the budget;
  4. with --search: the observed features plus fixed hard filters (region, budget,
     bedrooms) find real homes, and those homes carry the features more often than
     a no-photo baseline with the same filters (the photo must change the result
     in the expected direction, not just change it).

Photos: put rights-cleared exterior photos (team-shot or with a recorded licence;
no people, number plates or addresses) in fixtures/photos/ (git-ignored), and
list each in fixtures/photos/licences.csv as `file,source,licence`. A photo
without a licence row is still tested but flagged in the report. Images are
resized to 1024 px (macOS `sips`) and sent to the model only; the report keeps
file names and results, never image data.

  python scripts/vision_spike.py --models-only
  python scripts/vision_spike.py
  python scripts/vision_spike.py --search --region Faro --max-price 800000 --min-bedrooms 3
  python scripts/vision_spike.py --model <id> --photos path/to/dir

Needs NEBIUS_API_KEY (and CUBI_MCP_TOKEN for --search) in the environment or .env.
Writes reports/vision_<UTC timestamp>.json and .md.
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import listings, llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
PHOTOS = ROOT / "fixtures" / "photos"
DEFAULT_MODEL = "nvidia/Nemotron-3.5-Super-VL"
MAX_ATTRS = 15

# Connector feature names that resolve to atlas concepts (concept_alias, checked
# 2026-10-23) and that a photo can actually show. Order = search priority.
FEATURES = ["Pool", "Sea View", "Garden", "Terrace", "Roof Terrace", "Balcony", "Mountain View",
            "Lake View", "Countryside Views", "Patio", "Courtyard", "Pergola", "Solar Panels",
            "Olive Trees", "Vineyard", "Garage", "Stone House", "Modern Architecture"]
TYPES = {"detached house": "house", "villa": "villa", "townhouse": "townhouse", "apartment": "apartment"}
STOREYS = ["1", "2", "3+"]

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["building", "storeys", "attributes"],
    "properties": {
        "building": {"type": "string", "enum": [*TYPES, "unknown"]},
        "storeys": {"type": "string", "enum": [*STOREYS, "unknown"]},
        "attributes": {"type": "array", "maxItems": MAX_ATTRS, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["feature", "status", "evidence"],
            "properties": {"feature": {"type": "string", "enum": FEATURES},
                           "status": {"type": "string", "enum": ["observed", "uncertain"]},
                           "evidence": {"type": "string", "maxLength": 120}}}},
    },
}

PROMPT = (
    "This is an inspiration photo of a home someone would like to live in. Describe only what is "
    "visible in it, using the allowed values. For each feature you can see, give status 'observed' "
    "if it is clearly visible and 'uncertain' if it might be there; leave out anything you cannot "
    "see. Never guess the location, country, climate, season, price, or distances to anything. A "
    "pool counts only if you can see it; whether it is private is not something to judge. "
    "'evidence' is a few words on what in the photo shows it. Allowed features: "
    + ", ".join(FEATURES) + ". Reply with the JSON object only."
)


def vision_models(cli) -> list[str]:
    ids = [m.id for m in cli.models.list().data]
    return sorted(i for i in ids if re.search(r"(^|[-_/.])(vl|vision|omni)([-_/.]|$)|minicpm|llava|pixtral",
                                              i, re.I))


def _jpeg(path: Path) -> bytes:
    """1024 px JPEG via macOS sips; the original bytes elsewhere."""
    if not shutil.which("sips"):
        return path.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "p.jpg"
        subprocess.run(["sips", "-Z", "1024", "-s", "format", "jpeg", str(path), "--out", str(out)],
                       check=True, capture_output=True)
        return out.read_bytes()


def _validate(obj: dict) -> list[str]:
    errs = []
    if obj.get("building") not in [*TYPES, "unknown"]:
        errs.append(f"building={obj.get('building')!r}")
    if obj.get("storeys") not in [*STOREYS, "unknown"]:
        errs.append(f"storeys={obj.get('storeys')!r}")
    attrs = obj.get("attributes")
    if not isinstance(attrs, list):
        return errs + ["attributes missing"]
    if len(attrs) > MAX_ATTRS:
        errs.append(f"{len(attrs)} attributes > {MAX_ATTRS}")
    for a in attrs:
        if not isinstance(a, dict) or a.get("feature") not in FEATURES:
            errs.append(f"feature not allowed: {a.get('feature') if isinstance(a, dict) else a!r}")
        elif a.get("status") not in ("observed", "uncertain"):
            errs.append(f"status={a.get('status')!r}")
    return errs


def read_photo(cli, model: str, path: Path) -> dict:
    data = base64.b64encode(_jpeg(path)).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}]
    out: dict = {"photo": path.name}
    for mode in ("json_schema", "json_object"):
        fmt = ({"type": "json_schema", "json_schema": {"name": "photo", "schema": SCHEMA, "strict": True}}
               if mode == "json_schema" else {"type": "json_object"})
        t0 = time.monotonic()
        try:
            r = cli.chat.completions.create(model=model, messages=messages, temperature=0, max_tokens=900,
                                            response_format=fmt)
        except Exception as e:  # noqa: BLE001 - the spike records any failure
            out[f"error_{mode}"] = f"{type(e).__name__}: {str(e)[:200]}"
            continue
        out["seconds"] = round(time.monotonic() - t0, 2)
        out["mode"] = mode
        out["usage"] = {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens} if r.usage else None
        text = (r.choices[0].message.content or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            out["errors"] = ["not JSON"]
            out["raw_head"] = text[:200]
            return out
        out["result"] = obj
        out["errors"] = _validate(obj)
        return out
    return out


def observed(res: dict) -> list[str]:
    attrs = (res.get("result") or {}).get("attributes") or []
    seen = {a["feature"] for a in attrs if isinstance(a, dict) and a.get("status") == "observed"}
    return [f for f in FEATURES if f in seen]


def _search(mcp, base: dict, features: list[str]) -> tuple[list[dict], list[str], float]:
    """filter_listings with up to 3 features, dropping the lowest-priority one until
    something matches (features are hard filters on the connector)."""
    feats = features[:3]
    t0 = time.monotonic()
    while True:
        args = {**base, **({"features": feats} if feats else {})}
        res = mcp.call_tool("filter_listings", args)
        cards = [] if res["is_error"] else listings.parse(res["text"])
        if cards or not feats:
            return cards, feats, round(time.monotonic() - t0, 2)
        feats = feats[:-1]


def _hits(cards: list[dict], feats: list[str]) -> float | None:
    """Share of (top-3 card, photo feature) pairs where the card's tags name the feature."""
    if not feats or not cards:
        return None
    top = cards[:3]
    n = sum(any(f.lower() in t.lower() for t in c.get("tags", [])) for c in top for f in feats)
    return round(n / (len(top) * len(feats)), 2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--photos", type=Path, default=PHOTOS)
    ap.add_argument("--models-only", action="store_true")
    ap.add_argument("--search", action="store_true", help="also run the retrieval and baseline check")
    ap.add_argument("--region", default="Faro")
    ap.add_argument("--max-price", type=float, default=800000)
    ap.add_argument("--min-bedrooms", type=int, default=3)
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()

    cli = llm.client(timeout=120.0)
    vms = vision_models(cli)
    print("vision-capable models served to this account:", ", ".join(vms) or "none")
    if a.models_only:
        return 0 if vms else 1
    if a.model not in vms:
        print(f"note: {a.model} is not in that list; trying it anyway")

    photos = sorted(p for p in a.photos.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic"))
    if not photos:
        print(f"no photos in {a.photos}")
        return 2
    lic_file = a.photos / "licences.csv"
    licensed = set()
    if lic_file.exists():
        with lic_file.open() as f:
            licensed = {row[0].strip() for row in csv.reader(f) if row and row[0].strip() != "file"}

    mcp = None
    base = {}
    if a.search:
        from agent.mcp_client import CubiMCP
        mcp = CubiMCP()
        mcp.initialize()
        base = {"lang": a.lang, "limit": 8, "transaction_type": "sale", "location": [a.region],
                "max_price": a.max_price, "min_bedrooms": a.min_bedrooms}

    rows = []
    for p in photos:
        r = read_photo(cli, a.model, p)
        r["licensed"] = p.name in licensed
        r["observed"] = observed(r)
        if mcp and r.get("result") is not None:
            btype = TYPES.get((r["result"] or {}).get("building", ""), None)
            pbase = {**base, **({"type": [btype]} if btype else {})}
            cards, used, secs = _search(mcp, pbase, r["observed"])
            bcards, _, _ = _search(mcp, pbase, [])
            r["search"] = {"features_used": used, "results": len(cards), "seconds": secs,
                           "top3": [c.get("id") for c in cards[:3]],
                           "hit_photo": _hits(cards, used), "hit_baseline": _hits(bcards, used),
                           "baseline_top3": [c.get("id") for c in bcards[:3]]}
        rows.append(r)
        s = r.get("search") or {}
        print(f"{p.name}: {r.get('seconds', '—')} s · {r.get('mode', 'FAILED')} · errors={len(r.get('errors') or [])}"
              f" · observed={', '.join(r['observed']) or '—'}"
              + (f" · {s['results']} homes with {s['features_used']} · hits {s['hit_photo']} vs baseline "
                 f"{s['hit_baseline']}" if s else ""))

    ok = [r for r in rows if r.get("result") is not None]
    valid = [r for r in ok if not r.get("errors")]
    secs = [r["seconds"] for r in ok if "seconds" in r]
    with_search = [r["search"] for r in rows if r.get("search")]
    better = [s for s in with_search if s["hit_photo"] is not None and s["hit_baseline"] is not None
              and s["hit_photo"] > s["hit_baseline"]]
    summary = {
        "model": a.model, "vision_models": vms, "photos": len(rows), "answered": len(ok),
        "schema_valid": len(valid), "unlicensed": [r["photo"] for r in rows if not r["licensed"]],
        "seconds_p50": statistics.median(secs) if secs else None, "seconds_max": max(secs) if secs else None,
        "modes": sorted({r.get("mode") for r in ok}),
    }
    if with_search:
        summary.update({"search_filters": base, "found_3_or_more": sum(s["results"] >= 3 for s in with_search),
                        "photo_beats_baseline": len(better), "searched": len(with_search)})
    gates = {
        "1 vision call works": bool(ok),
        "2 schema-valid on every answered photo": bool(ok) and len(valid) == len(ok),
        "3 latency measured": bool(secs),
    }
    if with_search:
        gates["4a at least 3 homes for most photos"] = summary["found_3_or_more"] * 2 > len(with_search)
        gates["4b photo beats no-photo baseline for most photos"] = len(better) * 2 > len(with_search)
    summary["gates"] = gates

    REPORTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORTS / f"vision_{stamp}.json").write_text(json.dumps({"summary": summary, "photos": rows}, indent=1,
                                                             ensure_ascii=False))
    md = [f"# Vision spike {stamp}", "", f"Model `{a.model}`. Vision models served: {', '.join(vms) or 'none'}.", "",
          f"{len(ok)}/{len(rows)} photos answered, {len(valid)} schema-valid; latency p50 "
          f"{summary['seconds_p50']} s, max {summary['seconds_max']} s.", ""]
    if summary["unlicensed"]:
        md += [f"**No licence row:** {', '.join(summary['unlicensed'])}", ""]
    md += ["| Gate | Pass |", "|---|---|"] + [f"| {k} | {'yes' if v else '**no**'} |" for k, v in gates.items()]
    md += ["", "| Photo | s | Observed | Homes | Features used | Hits photo / baseline | Errors |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r.get("search") or {}
        md.append(f"| {r['photo']} | {r.get('seconds', '—')} | {', '.join(r['observed']) or '—'} | "
                  f"{s.get('results', '—')} | {', '.join(s.get('features_used') or []) or '—'} | "
                  f"{s.get('hit_photo', '—')} / {s.get('hit_baseline', '—')} | "
                  f"{'; '.join(r.get('errors') or []) or r.get('error_json_object') or '—'} |")
    (REPORTS / f"vision_{stamp}.md").write_text("\n".join(md) + "\n")
    print("\n" + "\n".join(f"{'PASS' if v else 'FAIL'}  {k}" for k, v in gates.items()))
    print(f"report: reports/vision_{stamp}.md")
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
