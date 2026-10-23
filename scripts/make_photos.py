"""Generate the vision spike's inspiration images on Token Factory, with an answer key.

No licensed photos needed: each image is generated from a prompt that names the
features it should show, so the spike can score the vision model against what
was asked for (precision, recall), and the contrast pairs differ in exactly one
feature (same house with and without a pool, ...). The images show no real
house, person, car, text or address.

Writes into fixtures/photos/ (git-ignored):
  <name>.png       the image
  licences.csv     file,source,licence  (model id; "AI-generated" + the model's licence)
  expected.json    {file: {"building", "storeys", "features", "pair"}}

In the video, call these "AI-generated inspiration images", never photos of
homes for sale or photos found online.

  python scripts/make_photos.py --list-models
  python scripts/make_photos.py                 # default model, all scenes
  python scripts/make_photos.py --model <id> --only villa_pool_sea,villa_sea
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

from agent import llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "photos"
DEFAULT_MODEL = "black-forest-labs/flux-schnell"
LICENCES = {"flux-schnell": "Apache-2.0 (FLUX.1 [schnell])", "sana": "NVIDIA open model licence (check)",
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
    "vineyard_house": ("A two-storey country house surrounded by vineyard rows on rolling hills, a stone patio "
                       "with a table in front.",
                       "detached house", "2", ["Vineyard", "Countryside Views", "Patio"], None),
}


def image_models(cli) -> list[str]:
    ids = [m.id for m in cli.models.list().data]
    return sorted(i for i in ids if re.search(r"flux|sdxl|stable-diffusion|sana|imagen|dall", i, re.I))


def _licence(model: str) -> str:
    for k, v in LICENCES.items():
        if k in model.lower():
            return f"AI-generated; {v}"
    return "AI-generated; check the model licence"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated scene names")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    cli = llm.client(timeout=180.0)
    models = image_models(cli)
    print("image models served to this account:", ", ".join(models) or "none")
    if a.list_models:
        return 0 if models else 1
    if a.model not in models:
        print(f"note: {a.model} is not in that list; trying it anyway")

    names = [n.strip() for n in a.only.split(",") if n.strip()] or list(SCENES)
    a.out.mkdir(parents=True, exist_ok=True)
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
            r = cli.images.generate(model=a.model, prompt=STYLE + prompt, response_format="b64_json",
                                    extra_body={"response_extension": "png", "width": 1024, "height": 768,
                                                "num_inference_steps": 4})
        except Exception as e:  # noqa: BLE001
            print(f"{n}: FAILED {type(e).__name__}: {str(e)[:200]}")
            continue
        file = f"{n}.png"
        (a.out / file).write_bytes(base64.b64decode(r.data[0].b64_json))
        expected[file] = {"building": building, "storeys": storeys, "features": feats, "pair": pair}
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
