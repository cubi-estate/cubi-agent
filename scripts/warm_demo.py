"""Warm Cubi for the demo's cities right before filming (tester F18).

    set -a && . ./.env && set +a && .venv/bin/python scripts/warm_demo.py

Cubi's database answers the first price check or similar-homes call for a city
it hasn't read lately in 10-25 s, or times out; the next call takes about a
second. This runs the demo's searches, then a price check on the first cards of
each and a similar-homes call between the cities, twice, and prints the seconds
so the second pass shows the cities are warm. Uses about 40 connector quota
units. The agent also retries such a call once, so this is a speed-up, not the
only fix; run it again if more than half an hour passes before filming.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import listings  # noqa: E402
from agent.mcp_client import CubiMCP  # noqa: E402

SEARCHES = {  # city → the demo's search there (docs/video/SCRIPT.md)
    "Lisbon": "2 bedroom flat for sale in Lisbon under 500000",
    "Porto": "2 bedroom flat for sale in Porto under 500000",
    "Valencia": "2 bedroom flat for sale in Valencia under 400000",
}
CARDS = 3  # the demo asks about #1 and #2


def timed(mcp: CubiMCP, name: str, args: dict) -> tuple[float, dict]:
    t0 = time.monotonic()
    try:
        res = mcp.call_tool(name, args)
    except Exception as e:  # noqa: BLE001 — report and carry on warming
        res = {"text": f"{type(e).__name__}: {e}", "is_error": True}
    return time.monotonic() - t0, res


def main() -> int:
    mcp = CubiMCP(timeout=60)
    mcp.initialize()
    ids: dict[str, list[str]] = {}
    for city, query in SEARCHES.items():
        s, res = timed(mcp, "search_properties", {"query": query, "limit": CARDS})
        ids[city] = [c["id"] for c in listings.parse(res["text"]) if c.get("id")][:CARDS]
        print(f"search {city}: {s:.1f}s, {len(ids[city])} cards")
    slow = 0
    for rnd in (1, 2):
        for city, refs in ids.items():
            other = "Porto" if city != "Porto" else "Lisbon"
            for ref in refs:
                s1, r1 = timed(mcp, "compare_asking_prices", {"listing_id": ref, "lang": "en"})
                s2, r2 = timed(mcp, "find_similar_elsewhere", {"listing_id": ref, "city": other, "lang": "en"})
                ok = not r1["is_error"] and not r2["is_error"] and r2["text"].lstrip().startswith("{")
                print(f"pass {rnd} {city} card: price {s1:.1f}s · similar in {other} {s2:.1f}s{'' if ok else ' · FAILED'}")
                if rnd == 2 and (max(s1, s2) > 5 or not ok):
                    slow += 1
    print("warm" if not slow else f"{slow} call(s) still slow or failing on the second pass; run again")
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
