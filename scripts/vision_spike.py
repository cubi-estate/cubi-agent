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

Generated images: `python scripts/make_photos.py` writes AI-generated images
plus an answer key (fixtures/photos/expected.json); the spike then also scores
precision and recall against it, and checks the contrast pairs (same house, one
feature different: the model must see it in one and not the other).

Photos: or put rights-cleared exterior photos (team-shot or with a recorded licence;
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
# How a listing says it has the feature (get_listing's feature list and description),
# in the demo's languages. Used to verify homes, not to search.
SYNONYMS = {
    "Pool": r"pool|piscina|piscine|schwimmbad|zwembad",
    "Sea View": r"sea view|ocean view|vista (?:de )?mar|vistas al mar|vue (?:sur la )?mer|meerblick|zeezicht",
    "Garden": r"garden|jardim|jard[ií]n|jardin|garten|tuin",
    "Terrace": r"terrace|terra[çc]o|terraza|terrasse|terras",
    "Roof Terrace": r"roof ?terrace|rooftop|terra[çc]o (?:na )?cobertura|[aá]tico con terraza|toit-terrasse|dachterrasse",
    "Balcony": r"balcon|balcony|varanda|balc[oó]n|balkon",
    "Mountain View": r"mountain view|vista (?:para a )?serra|vistas? (?:a la )?monta[ñn]a|vue montagne|bergblick",
    "Lake View": r"lake view|vista (?:para o )?lago|vue (?:sur le )?lac|seeblick",
    "Countryside Views": r"countryside|rural|campo|campagne|l[äa]ndlich",
    "Patio": r"patio|p[aá]tio|innenhof",
    "Courtyard": r"courtyard|p[aá]tio interior|cour int|innenhof",
    "Pergola": r"pergola|p[ée]rgola",
    "Solar Panels": r"solar panel|pain[ée]is solares|placas solares|panneaux solaires|solaranlage|photovolta",
    "Olive Trees": r"olive|oliveira|olivo|olivier|oliven",
    "Vineyard": r"vineyard|vinha|vi[ñn]edo|vignoble|weinberg|weingut",
    "Garage": r"garage|garagem|garaje",
    "Stone House": r"stone house|stone[- ]built|built (?:of|in|from) stone|(?:casa|moradia) (?:de|em) pedra|"
                   r"casa de piedra|maison en pierre|steinhaus|natursteinhaus",
    "Modern Architecture": r"modern|contempor",
}
_LISTING_CACHE: dict[str, str] = {}

# The demo's deployment token allows 120 connector calls a minute
# (MCP_DEPLOY_RATE_PER_MIN) and the live demo shares it: stay at a third.
CALLS_PER_MIN = 40
_last_call = [0.0]


def call(mcp, name: str, args: dict) -> dict:
    """A paced connector call; waits a minute and retries once on the rate limit."""
    for attempt in range(2):
        wait = _last_call[0] + 60 / CALLS_PER_MIN - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        res = mcp.call_tool(name, args)
        if not (res["is_error"] and "Too many tool calls" in res["text"]) or attempt:
            return res
        print("  connector rate limit: waiting a minute")
        time.sleep(61)
    return res


def listing_text(mcp, listing_id: str) -> str:
    if listing_id not in _LISTING_CACHE:
        res = call(mcp, "get_listing", {"listing_id": listing_id})
        _LISTING_CACHE[listing_id] = "" if res["is_error"] else res["text"]
    return _LISTING_CACHE[listing_id]


def has_features(text: str, feats: list[str]) -> dict[str, bool]:
    return {f: bool(re.search(SYNONYMS[f], text, re.I)) for f in feats}


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
    "'evidence' is a few words on what in the photo shows it. 'building' is the kind of building the "
    "home is (a villa is a large detached house; a townhouse shares side walls with its neighbours; an "
    "apartment is one unit in a larger building), and 'storeys' the number of floors you can see above "
    "ground; use 'unknown' only if the photo really does not show it. Allowed features: "
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


def read_photo(cli, model: str, path: Path, think: bool = False) -> dict:
    data = base64.b64encode(_jpeg(path)).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}]
    out: dict = {"photo": path.name}
    # Thinking off, as for Nemotron 3 extraction (day-1 probe): with it on, the VL model
    # spent all 900 tokens reasoning and returned empty content (2026-10-23).
    extra = llm.NO_THINK if think is False else {}
    for mode in ("json_schema", "json_object"):
        fmt = ({"type": "json_schema", "json_schema": {"name": "photo", "schema": SCHEMA, "strict": True}}
               if mode == "json_schema" else {"type": "json_object"})
        t0 = time.monotonic()
        try:
            r = cli.chat.completions.create(model=model, messages=messages, temperature=0, max_tokens=2000,
                                            response_format=fmt, extra_body=extra)
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
        res = call(mcp, "filter_listings", args)
        cards = [] if res["is_error"] else listings.parse(res["text"])
        if cards or not feats or res["is_error"]:
            return cards, feats, round(time.monotonic() - t0, 2)
        feats = feats[:-1]


def _hits(mcp, cards: list[dict], feats: list[str]) -> float | None:
    """Share of (top-3 home, photo feature) pairs where the full listing (get_listing)
    states the feature. Card tags show only 8 items, so they are not enough."""
    top = [c for c in cards[:3] if c.get("id")]
    if not feats or not top:
        return None
    n = sum(sum(has_features(listing_text(mcp, c["id"]), feats).values()) for c in top)
    return round(n / (len(top) * len(feats)), 2)


def _same_building(got: str | None, want: str) -> bool:
    """A villa is a detached house: either name is right for the other."""
    houses = {"villa", "detached house"}
    return got == want or (got in houses and want in houses)


def score(rows: list[dict], expected: dict) -> dict:
    """Precision/recall of observed features against the answer key, building-type
    agreement, and contrast pairs (the one differing feature seen in the right image only)."""
    per, pairs = [], {}
    for r in rows:
        exp = expected.get(r["photo"])
        if not exp or r.get("result") is None:
            continue
        got, want = set(r["observed"]), set(exp["features"])
        r["expected"] = sorted(want)
        r["precision"] = round(len(got & want) / len(got), 2) if got else None
        r["recall"] = round(len(got & want) / len(want), 2) if want else None
        r["building_ok"] = _same_building((r["result"] or {}).get("building"), exp["building"])
        per.append(r)
        if exp.get("pair"):
            pairs.setdefault(exp["pair"], []).append((want, got))
    pair_ok = []
    for name, two in pairs.items():
        if len(two) != 2:
            continue
        (w1, g1), (w2, g2) = two
        diff = (w1 ^ w2)
        ok = all((f in g1) == (f in w1) and (f in g2) == (f in w2) for f in diff)
        pair_ok.append({"pair": name, "differs_in": sorted(diff), "ok": ok})
    ps = [r["precision"] for r in per if r["precision"] is not None]
    rs = [r["recall"] for r in per if r["recall"] is not None]
    return {"scored": len(per), "precision_mean": round(statistics.mean(ps), 2) if ps else None,
            "recall_mean": round(statistics.mean(rs), 2) if rs else None,
            "building_ok": sum(r["building_ok"] for r in per), "pairs": pair_ok}


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

    exp_file = a.photos / "expected.json"
    expected = json.loads(exp_file.read_text()) if exp_file.exists() else {}

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
                           "hit_photo": _hits(mcp, cards, used), "hit_baseline": _hits(mcp, bcards, used),
                           "baseline_top3": [c.get("id") for c in bcards[:3]]}
        rows.append(r)
        s = r.get("search") or {}
        print(f"{p.name}: {r.get('seconds', '—')} s · {r.get('mode', 'FAILED')} · errors={len(r.get('errors') or [])}"
              f" · observed={', '.join(r['observed']) or '—'}"
              + (f" · {s['results']} homes with {s['features_used']} · hits {s['hit_photo']} vs baseline "
                 f"{s['hit_baseline']}" if s else ""))

    answered = [r for r in rows if "seconds" in r]          # the call came back
    ok = [r for r in rows if r.get("result") is not None]   # ... with JSON
    valid = [r for r in ok if not r.get("errors")]
    secs = [r["seconds"] for r in answered]
    with_search = [r["search"] for r in rows if r.get("search")]
    better = [s for s in with_search if s["hit_photo"] is not None and s["hit_baseline"] is not None
              and s["hit_photo"] > s["hit_baseline"]]
    summary = {
        "model": a.model, "vision_models": vms, "photos": len(rows), "answered": len(answered), "json": len(ok),
        "schema_valid": len(valid), "unlicensed": [r["photo"] for r in rows if not r["licensed"]],
        "seconds_p50": statistics.median(secs) if secs else None, "seconds_max": max(secs) if secs else None,
        "modes": sorted({r.get("mode") for r in ok}),
    }
    if with_search:
        summary.update({"search_filters": base, "found_3_or_more": sum(s["results"] >= 3 for s in with_search),
                        "photo_beats_baseline": len(better), "searched": len(with_search)})
    gates = {
        "1 vision call works": bool(answered),
        "2 schema-valid on every answered photo": bool(answered) and len(valid) == len(answered),
        "3 latency measured": bool(secs),
    }
    if with_search:
        gates["4a at least 3 homes for most photos"] = summary["found_3_or_more"] * 2 > len(with_search)
        gates["4b photo beats no-photo baseline for most photos"] = len(better) * 2 > len(with_search)
    if expected:
        sc = score(rows, expected)
        summary["answer_key"] = sc
        if sc["pairs"]:
            gates["5 contrast pairs: the differing feature seen in the right image only"] = all(
                p["ok"] for p in sc["pairs"])
    summary["gates"] = gates

    REPORTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORTS / f"vision_{stamp}.json").write_text(json.dumps({"summary": summary, "photos": rows}, indent=1,
                                                             ensure_ascii=False))
    md = [f"# Vision spike {stamp}", "", f"Model `{a.model}`. Vision models served: {', '.join(vms) or 'none'}.", "",
          f"{len(answered)}/{len(rows)} photos answered, {len(ok)} with JSON, {len(valid)} schema-valid; latency p50 "
          f"{summary['seconds_p50']} s, max {summary['seconds_max']} s.", ""]
    if summary["unlicensed"]:
        md += [f"**No licence row:** {', '.join(summary['unlicensed'])}", ""]
    if expected and summary.get("answer_key"):
        sc = summary["answer_key"]
        md += [f"Answer key: {sc['scored']} images scored; precision {sc['precision_mean']}, recall "
               f"{sc['recall_mean']}; building type right {sc['building_ok']}/{sc['scored']}. Pairs: "
               + (", ".join(f"{p['pair']} ({'/'.join(p['differs_in'])}) {'ok' if p['ok'] else 'WRONG'}"
                            for p in sc["pairs"]) or "none"), ""]
    md += ["| Gate | Pass |", "|---|---|"] + [f"| {k} | {'yes' if v else '**no**'} |" for k, v in gates.items()]
    md += ["", "| Photo | s | Observed | Expected | P / R | Homes | Features used | Hits photo / baseline | Errors |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r.get("search") or {}
        md.append(f"| {r['photo']} | {r.get('seconds', '—')} | {', '.join(r['observed']) or '—'} | "
                  f"{', '.join(r.get('expected') or []) or '—'} | {r.get('precision', '—')} / {r.get('recall', '—')} | "
                  f"{s.get('results', '—')} | {', '.join(s.get('features_used') or []) or '—'} | "
                  f"{s.get('hit_photo', '—')} / {s.get('hit_baseline', '—')} | "
                  f"{'; '.join(r.get('errors') or []) or r.get('error_json_object') or '—'} |")
    (REPORTS / f"vision_{stamp}.md").write_text("\n".join(md) + "\n")
    print("\n" + "\n".join(f"{'PASS' if v else 'FAIL'}  {k}" for k, v in gates.items()))
    print(f"report: reports/vision_{stamp}.md")
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
