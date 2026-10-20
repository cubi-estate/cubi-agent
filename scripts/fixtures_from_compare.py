"""Build offline fixtures from a compare_search.py run without calling the connector again.

The compare report keeps the parsed listing facts per request but not the exact
arguments, so they are re-derived with the same extraction the agent uses
(Token Factory only). Each fixture is saved under the arguments the agent will
send, with facts only (agent/listings.render_cards).

  python scripts/fixtures_from_compare.py reports/compare_<UTC>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import fixtures, listings  # noqa: E402
from agent.extract import extract  # noqa: E402


def main(path: str) -> int:
    rows = json.loads(Path(path).read_text())
    fixtures.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        side = r["agent"]
        if side.get("skipped") or side.get("is_error"):
            continue
        ex = extract(r["q"])
        if ex.filter is None or ex.route != "filter":
            continue
        args = ex.filter.to_filter_args(limit=6)
        text = listings.render_cards(side.get("header") or f"Showing {len(side['cards'])} properties.", side["cards"])
        if side.get("relaxed"):  # the agent's first, exact call found nothing
            empty = {"tool": "filter_listings", "args": dict(args), "is_error": False,
                     "text": "No properties matched these filters.\n"}
            (fixtures.FIXTURE_DIR / f"{fixtures.key('filter_listings', args)}.json").write_text(
                json.dumps(empty, indent=1, ensure_ascii=False) + "\n")
            args.pop("features", None)
        rec = {"tool": "filter_listings", "args": args, "is_error": False, "text": text, "case": r["id"]}
        (fixtures.FIXTURE_DIR / f"{fixtures.key('filter_listings', args)}.json").write_text(
            json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        n += 1
    fixtures.write_index()
    print(f"wrote {n} fixtures to {fixtures.FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
