"""Smoke-test the Cubi connector without any model: list tools, run one filter.

  python scripts/mcp_smoke.py            # live
  python scripts/mcp_smoke.py --record   # also save the reply under fixtures/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.mcp_client import CubiMCP  # noqa: E402

ARGS = {"location": ["Porto"], "type": ["apartment"], "transaction_type": "sale",
        "max_price": 400000, "min_bedrooms": 2, "features": ["Balcony"], "lang": "en", "limit": 3}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    mcp = CubiMCP()
    info = mcp.initialize()
    print("server:", info["serverInfo"])
    print("tools:", [t["name"] for t in mcp.list_tools()])
    t0 = time.monotonic()
    res = mcp.call_tool("filter_listings", ARGS)
    print(f"filter_listings: is_error={res['is_error']} {len(res['text'])} chars in {time.monotonic() - t0:.1f}s")
    print(res["text"][:1500])
    if a.record:
        (ROOT / "fixtures").mkdir(exist_ok=True)
        (ROOT / "fixtures" / "filter_listings_porto.json").write_text(
            json.dumps({"args": ARGS, "result": res}, indent=1, ensure_ascii=False))
    return 0 if not res["is_error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
