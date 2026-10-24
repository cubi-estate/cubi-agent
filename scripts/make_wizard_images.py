"""Generate the home wizard's tile images (web/wizard/<id>.jpg) with OpenAI gpt-image-2.

Prompts are in web/wizard/options.json, which the page reads too, so a tile and its
image can't drift apart. Each image is 1536x1024 from the API, saved as a 640 px JPEG
(about 50 KB) with Pillow. Existing images are kept unless --force.

    OPENAI_API_KEY=... python scripts/make_wizard_images.py [--only portugal,spain] [--force]

The images are AI-generated inspiration, labelled so on the page; they show no
people, text or logos. Output is owned by the user under OpenAI's terms.
"""
from __future__ import annotations

import argparse
import json
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.make_photos import OPENAI_MODEL, generate, image_client  # noqa: E402

WIZ = ROOT / "web" / "wizard"


def save(png: bytes, out: Path) -> None:
    """640 px progressive JPEG, about 50 KB (sips at 768 px gave 140 KB each)."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((640, 640))
    im.save(out, "JPEG", quality=72, optimize=True, progressive=True)


def items(opt: dict) -> list[tuple[str, str]]:
    out = [(r["id"], r["prompt"]) for r in opt["regions"]]
    out += [(c["id"], c["prompt"]) for c in opt["countries"].values()]
    out += [(t["id"], t["prompt"]) for t in opt["types"]]
    out += [(f["id"], f["prompt"]) for f in opt["features"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated ids")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=OPENAI_MODEL)
    a = ap.parse_args()
    opt = json.loads((WIZ / "options.json").read_text())
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    todo = [(i, p) for i, p in items(opt) if (not only or i in only) and (a.force or not (WIZ / f"{i}.jpg").exists())]
    print(f"{len(todo)} image(s) to make with {a.model}")
    cli = image_client("openai")
    failed = []
    for n, (i, prompt) in enumerate(todo, 1):
        try:
            png = generate(cli, "openai", a.model, opt["style"] + " " + prompt)
        except Exception as e:  # noqa: BLE001 - keep going, report at the end
            print(f"[{n}/{len(todo)}] {i}: failed: {type(e).__name__}: {str(e)[:160]}")
            failed.append(i)
            continue
        save(png, WIZ / f"{i}.jpg")
        print(f"[{n}/{len(todo)}] {i}: {(WIZ / f'{i}.jpg').stat().st_size // 1024} KB")
    if failed:
        print("failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
