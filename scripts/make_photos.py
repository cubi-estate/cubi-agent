"""Generate the vision spike's inspiration images on Token Factory, with an answer key.

No licensed photos needed: each image is generated from a prompt that names the
atlas features it should show, so the spike can score the vision model against what
was asked for (precision, recall), and the contrast pairs differ in exactly one
feature (same house with and without a pool, ...). The images show no real
house, person, car, text or address.

Coverage first: before generating, every candidate scene is searched on the
Cubi connector with the demo's hard filters (region, budget, bedrooms) and its
own building type and features, exactly as the vision spike will search. Only
scenes with at least --min-homes *verified* homes are generated, so picking any
image leads to listings. Verified = the full listing (get_listing) states each of
the scene's core features, the first three in search priority: the connector
relaxes features it cannot match, so "homes returned" alone overstates it (a
Faro "mountain view, stone house" search returned 10 houses with neither,
2026-10-23). Contrast pairs are kept or dropped together. The connector does
not count matches, so coverage is out of the first 10 homes.

Writes into fixtures/photos/ (git-ignored):
  <name>.png       the image
  licences.csv     file,source,licence  (model id; "AI-generated" + the model's licence)
  expected.json    {file: {"building", "storeys", "features", "pair", "coverage", "filters"}}

In the video, call these "AI-generated inspiration images", never photos of
homes for sale or photos found online.

  python scripts/make_photos.py --coverage-only  # which scenes have homes (no image calls)
  python scripts/make_photos.py --list-models
  python scripts/make_photos.py                  # covered scenes, Faro, <= 800k, 3+ bedrooms
  python scripts/make_photos.py --region Porto --max-price 500000 --min-bedrooms 2 --count 6
  python scripts/make_photos.py --model <id> --only villa_pool_sea,villa_sea
  python scripts/make_photos.py --backend openai                    # OpenAI Images API
  python scripts/make_photos.py --manual --tool "ChatGPT (OpenAI)"   # no image model on Token Factory

--backend openai reads OPENAI_API_KEY from the environment or ~/.openai/api_key
(default model gpt-image-1; OpenAI's terms assign the output to the user).

--manual writes expected.json, licences.csv and prompts.md for the selected
scenes without generating anything: generate each image from its prompt in a
tool whose terms let you use the output, save it as <scene>.png in the same
folder, then run the vision spike. (Token Factory served no image model to the
demo account on 2026-10-23.)
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import listings, llm  # noqa: E402
from scripts.vision_spike import CALLS_PER_MIN, FEATURES, TYPES, call, has_features, listing_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "photos"
DEFAULT_MODEL = "black-forest-labs/flux-schnell"
COVER_LIMIT = 10
VERIFY = 6   # homes checked with get_listing per scene
OPENAI_MODEL = "gpt-image-1"
LICENCES = {"gpt-image": "output owned by the user under OpenAI's terms", "dall-e": "output owned by the user under OpenAI's terms",
            "flux-schnell": "Apache-2.0 (FLUX.1 [schnell])", "sana": "NVIDIA open model licence (check)",
            "sdxl": "CreativeML Open RAIL++-M"}

STYLE = ("Photorealistic real-estate exterior photograph, natural daylight, eye level, wide angle. "
         "No people, no cars, no animals, no text, no logos, no signs, no house numbers, no street names. ")

# name: (prompt, building, storeys, features, pair). Features use vision_spike.FEATURES names.
SCENES = {
    "villa_pool_sea": ("A white two-storey Mediterranean villa on a hillside, a large private swimming pool in "
                       "front, a wide terrace with loungers, the sea in the background.",
                       "villa", "2", ["Pool", "Sea View", "Terrace"], "pool-sea"),
    "villa_sea": ("A white two-storey Mediterranean villa on a hillside, a wide terrace with loungers in front, "
                  "the sea in the background. No swimming pool anywhere.",
                  "villa", "2", ["Sea View", "Terrace"], "pool-sea"),
    "farmhouse_olives_pool": ("A single-storey rustic stone farmhouse in open countryside, olive trees around it, a "
                              "green garden, and a rectangular swimming pool beside the house.",
                              "detached house", "1", ["Pool", "Stone House", "Olive Trees", "Garden",
                                                      "Countryside Views"], "pool-farm"),
    "farmhouse_olives": ("A single-storey rustic stone farmhouse in open countryside, olive trees around it and a "
                         "green garden. No swimming pool anywhere.",
                         "detached house", "1", ["Stone House", "Olive Trees", "Garden", "Countryside Views"],
                         "pool-farm"),
    "townhouse_balconies": ("A narrow three-storey European townhouse in a terraced row, coloured facade, small "
                            "wrought-iron balconies on the upper floors.",
                            "townhouse", "3+", ["Balcony"], None),
    "apartment_roof_terrace": ("The top floor of a modern apartment building with a large roof terrace, a wooden "
                               "pergola and potted plants, city rooftops beyond.",
                               "apartment", "3+", ["Roof Terrace", "Pergola", "Modern Architecture"], None),
    "modern_villa_solar": ("A modern flat-roofed two-storey villa with large glass walls, solar panels on the roof, "
                           "a swimming pool and a lawn garden.",
                           "villa", "2", ["Modern Architecture", "Solar Panels", "Pool", "Garden"], "solar"),
    "modern_villa": ("A modern flat-roofed two-storey villa with large glass walls, a plain roof without any "
                     "panels, a swimming pool and a lawn garden.",
                     "villa", "2", ["Modern Architecture", "Pool", "Garden"], "solar"),
    "mountain_house": ("A two-storey stone and wood house in the mountains, snowy peaks behind, a garden in front "
                       "and an attached garage with its door closed.",
                       "detached house", "2", ["Mountain View", "Garden", "Garage", "Stone House"], None),
    "apartment_sea_balcony": ("A modern apartment block near the coast, seen from outside: generous balconies with "
                              "glass railings, the sea visible beyond.",
                              "apartment", "3+", ["Balcony", "Sea View", "Modern Architecture"], None),
    "apartment_pool": ("A low-rise apartment complex with white facades, balconies, and a shared swimming pool "
                       "with sun loungers in a landscaped garden.",
                       "apartment", "3+", ["Pool", "Balcony", "Garden"], None),
    "townhouse_terrace": ("A two-storey townhouse in a quiet row of similar houses, a tiled front terrace with "
                          "potted plants and a small table.",
                          "townhouse", "2", ["Terrace"], None),
    "villa_garden_garage": ("A detached two-storey villa with a pitched tiled roof, a lawn garden with shrubs and "
                            "an attached garage with its door closed.",
                            "villa", "2", ["Garden", "Garage"], None),
    "vineyard_house": ("A two-storey country house surrounded by vineyard rows on rolling hills, a stone patio "
                       "with a table in front.",
                       "detached house", "2", ["Vineyard", "Countryside Views", "Patio"], None),
}


def image_models(cli) -> list[str]:
    ids = [m.id for m in cli.models.list().data]
    return sorted(i for i in ids if re.search(r"flux|sdxl|stable-diffusion|sana|imagen|dall|gpt-image", i, re.I))


def image_client(backend: str):
    if backend == "tokenfactory":
        return llm.client(timeout=180.0)
    import os
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    f = Path.home() / ".openai" / "api_key"
    if not key and f.exists():
        key = f.read_text().strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set (environment or ~/.openai/api_key)")
    return OpenAI(api_key=key, timeout=180.0, max_retries=1)


def generate(cli, backend: str, model: str, prompt: str) -> bytes:
    if backend == "openai":
        r = cli.images.generate(model=model, prompt=prompt, size="1536x1024", quality="medium", n=1)
    else:
        r = cli.images.generate(model=model, prompt=prompt, response_format="b64_json",
                                extra_body={"response_extension": "png", "width": 1024, "height": 768,
                                            "num_inference_steps": 4})
    return base64.b64decode(r.data[0].b64_json)


def _licence(model: str) -> str:
    for k, v in LICENCES.items():
        if k in model.lower():
            return f"AI-generated; {v}"
    return "AI-generated; check the model licence"


def core(feats: list[str]) -> list[str]:
    """The features the vision spike searches with first: top three by priority."""
    return [f for f in FEATURES if f in feats][:3]


def coverage(mcp, filters: dict, names: list[str]) -> dict[str, dict]:
    """Per scene: homes returned (first COVER_LIMIT) for its building type + core
    features under the demo's hard filters, and how many of them verifiably have
    every core feature."""
    out = {}
    for n in names:
        _, building, _, feats, _ = SCENES[n]
        want = core(feats)
        args = {**filters, "limit": COVER_LIMIT, "features": want}
        if TYPES.get(building):
            args["type"] = [TYPES[building]]
        res = call(mcp, "filter_listings", args)
        if res["is_error"]:
            out[n] = {"returned": None, "verified": None, "core": want, "error": res["text"][:120]}
            continue
        cards = [c for c in listings.parse(res["text"]) if c.get("id")]
        verified = sum(all(has_features(listing_text(mcp, c["id"]), want).values()) for c in cards[:VERIFY])
        out[n] = {"returned": len(cards), "verified": verified, "core": want}
    return out


def select(cov: dict[str, int], min_homes: int, count: int) -> list[str]:
    """cov: verified homes per scene."""
    """Covered scenes, best-covered first; a contrast pair goes in whole or not at all."""
    units: dict[str, list[str]] = {}
    for n in cov:
        pair = SCENES[n][4]
        units.setdefault(pair or n, []).append(n)
    ok = [u for u in units.values() if all(cov[n] >= min_homes for n in u)]
    ok.sort(key=lambda u: (-len(u), -min(cov[n] for n in u)))   # pairs first: they carry gate 5
    out: list[str] = []
    for u in ok:
        if len(out) + len(u) <= count:
            out += u
    return out


def write_manual(a, names: list[str], cov: dict, filters: dict) -> int:
    exp_path, lic_path = a.out / "expected.json", a.out / "licences.csv"
    expected = json.loads(exp_path.read_text()) if exp_path.exists() else {}
    md = ["# Inspiration images to generate", "",
          f"Generate each in {a.tool}, landscape (about 4:3), and save it in this folder under the file name "
          "shown. Look at each result: regenerate any with people, cars, text or signs, or a feature it "
          "should not have (the 'no pool' images must have no pool).", ""]
    rows = []
    for n in names:
        prompt, building, storeys, feats, pair = SCENES[n]
        file = f"{n}.png"
        expected[file] = {"building": building, "storeys": storeys, "features": feats, "pair": pair,
                          "coverage": cov.get(n), "filters": filters}
        rows.append([file, f"generated with {a.tool} from a prompt in scripts/make_photos.py",
                     "AI-generated; check the tool's terms for the output"])
        md += [f"## {file}", "", STYLE + prompt, ""]
    exp_path.write_text(json.dumps(expected, indent=1))
    with lic_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "source", "licence"])
        w.writerows(rows)
    (a.out / "prompts.md").write_text("\n".join(md))
    print(f"{len(names)} prompts in {a.out / 'prompts.md'}; answer key and licences written. "
          "Save each image under its file name, then run scripts/vision_spike.py.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=["tokenfactory", "openai"], default="tokenfactory")
    ap.add_argument("--model", default=None, help=f"default {DEFAULT_MODEL} (tokenfactory) or {OPENAI_MODEL} (openai)")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated scene names")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--region", default="Faro")
    ap.add_argument("--max-price", type=float, default=800000)
    ap.add_argument("--min-bedrooms", type=int, default=3)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--min-homes", type=int, default=3, help="homes a scene must find to be generated")
    ap.add_argument("--count", type=int, default=8, help="images to generate at most")
    ap.add_argument("--coverage-only", action="store_true")
    ap.add_argument("--no-coverage", action="store_true", help="skip the connector check (offline)")
    ap.add_argument("--manual", action="store_true", help="write prompts + answer key; generate the images yourself")
    ap.add_argument("--tool", default="an image generator", help="with --manual: the tool you will use")
    a = ap.parse_args()
    a.model = a.model or (OPENAI_MODEL if a.backend == "openai" else DEFAULT_MODEL)

    if a.list_models:
        models = image_models(image_client(a.backend))
        print("image models served to this account:", ", ".join(models) or "none")
        return 0 if models else 1

    asked = [n.strip() for n in a.only.split(",") if n.strip()]
    unknown = [n for n in asked if n not in SCENES]
    if unknown:
        print("unknown scenes:", ", ".join(unknown), "— known:", ", ".join(SCENES))
        return 2
    filters = {"lang": a.lang, "transaction_type": "sale", "location": [a.region], "max_price": a.max_price,
               "min_bedrooms": a.min_bedrooms}
    cov: dict[str, dict] = {}
    if a.no_coverage:
        names = asked or list(SCENES)[:a.count]
    else:
        from agent.mcp_client import CubiMCP
        mcp = CubiMCP()
        mcp.initialize()
        cov = coverage(mcp, filters, asked or list(SCENES))
        names = asked or select({n: c["verified"] or 0 for n, c in cov.items()}, a.min_homes, a.count)
        print(f"coverage in {a.region}, <= {a.max_price:,.0f} EUR, {a.min_bedrooms}+ bedrooms "
              f"(verified among the first {VERIFY} / returned, of {COVER_LIMIT} asked; "
              f"paced at {CALLS_PER_MIN} calls a minute):")
        for n, c in sorted(cov.items(), key=lambda kv: (-(kv[1]["verified"] or -1), -(kv[1]["returned"] or 0))):
            v = "?" if c["verified"] is None else c["verified"]
            r = "?" if c["returned"] is None else c["returned"]
            print(f"  {v:>2} / {r:>2} {'✓' if n in names else ' '} {n}: {SCENES[n][1]}, core {', '.join(c['core'])}"
                  + (f"  [call failed: {c['error']}]" if c.get("error") else ""))
        if a.coverage_only:
            return 0 if names else 1
        if not names:
            print(f"no scene finds {a.min_homes}+ homes here: widen the budget or pick another region")
            return 1

    a.out.mkdir(parents=True, exist_ok=True)
    if a.manual:
        return write_manual(a, names, cov, filters)

    cli = image_client(a.backend)
    models = image_models(cli)
    print("image models served to this account:", ", ".join(models) or "none")
    if a.model not in models:
        print(f"note: {a.model} is not in that list; trying it anyway")

    exp_path, lic_path = a.out / "expected.json", a.out / "licences.csv"
    expected = json.loads(exp_path.read_text()) if exp_path.exists() else {}
    licences = {}
    if lic_path.exists():
        with lic_path.open() as f:
            licences = {r[0]: r for r in csv.reader(f) if r and r[0] != "file"}

    made = 0
    for n in names:
        prompt, building, storeys, feats, pair = SCENES[n]
        try:
            png = generate(cli, a.backend, a.model, STYLE + prompt)
        except Exception as e:  # noqa: BLE001
            print(f"{n}: FAILED {type(e).__name__}: {str(e)[:200]}")
            continue
        file = f"{n}.png"
        (a.out / file).write_bytes(png)
        expected[file] = {"building": building, "storeys": storeys, "features": feats, "pair": pair,
                          "coverage": cov.get(n), "filters": filters}
        licences[file] = [file, f"generated with {a.model} from a prompt in scripts/make_photos.py", _licence(a.model)]
        made += 1
        print(f"{n}: ok")

    exp_path.write_text(json.dumps(expected, indent=1))
    with lic_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "source", "licence"])
        w.writerows(licences[k] for k in sorted(licences))
    print(f"{made}/{len(names)} images in {a.out}. Look at each before using it: regenerate any that "
          "shows people, cars, text or a feature it should not have.")
    return 0 if made == len(names) else 1


if __name__ == "__main__":
    sys.exit(main())
