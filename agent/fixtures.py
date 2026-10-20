"""Offline mode: replay recorded connector replies instead of calling Cubi.

  CUBI_OFFLINE=1 python cli.py "2-bed apartment in Porto under 400k"   # replay
  CUBI_RECORD=1  python cli.py "..."                                    # call live, save

Recordings live in fixtures/mcp/, one JSON file per (tool, arguments). They are
cut down before saving: listing cards keep facts only (type, place, size,
price, URL, id, a few tags) — no title, no description, no street address —
so the public repo carries no text copied from the original listings. Other
tools keep only labelled fact lines.

Token Factory is still called in offline mode: it is the part being shown.
Offline mode is for tests and for reproducing results when the live service is
unavailable, not for the hosted demo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

from . import listings
from .mcp_client import QUOTA_UNITS, CubiMCP, to_openai_tool

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "fixtures" / "mcp"
TOOLS_FILE = ROOT / "fixtures" / "mcp_tools.json"

# Lines kept from non-card replies (get_listing, compare_asking_prices, ...).
_FACT_LABELS = re.compile(
    r"^\s*[-*]?\s*\**(Location|Price|Asking price|Type|Bedrooms|Bathrooms|Living area|Plot|Area|URL|ID|"
    r"Last changed|Median|Range|Comparables|Sample|Listings compared|Ask Cubi|Contact)\b[^:]*:\**", re.I)


def _plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _canon(v):
    if isinstance(v, str):
        return _plain(v)
    if isinstance(v, list):
        return sorted(_canon(x) for x in v)
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in sorted(v.items()) if k not in ("limit",)}
    return v


def key(tool: str, args: dict) -> str:
    """Stable file key: the tool plus a hash of its arguments, case/accents/order folded, limit ignored."""
    blob = json.dumps(_canon(args), sort_keys=True, ensure_ascii=True)
    return f"{tool}_{hashlib.sha1(blob.encode()).hexdigest()[:12]}"


def sanitise(text: str) -> str:
    if listings.parse(text):
        return listings.render_facts(text)
    keep = [line for line in text.splitlines() if _FACT_LABELS.match(line)]
    head = text.strip().splitlines()[:1]
    if head and not _FACT_LABELS.match(head[0]) and len(head[0]) < 240:
        keep.insert(0, head[0])  # the summary line ("Showing 3 properties…")
    return "\n".join(keep) + "\n"


class FixtureMCP:
    """Same surface as CubiMCP, answered from fixtures/mcp/."""

    def __init__(self, directory: Path = FIXTURE_DIR):
        self.dir = directory
        self.calls: list[dict] = []
        self._tools = json.loads(TOOLS_FILE.read_text())

    def initialize(self) -> dict:
        return {"serverInfo": {"name": "cubi-properties (offline fixtures)"}}

    def list_tools(self) -> list[dict]:
        return self._tools

    def openai_tools(self, names: list[str] | None = None) -> list[dict]:
        return [to_openai_tool(t) for t in self._tools if names is None or t["name"] in names]

    def _lookup(self, tool: str, args: dict) -> dict | None:
        exact = self.dir / f"{key(tool, args)}.json"
        if exact.exists():
            return json.loads(exact.read_text())
        # Near miss: the same tool and the same place, best overlap of other arguments.
        want = _canon(args)
        best, best_score = None, -1
        for f in sorted(self.dir.glob(f"{tool}_*.json")):
            rec = json.loads(f.read_text())
            got = _canon(rec["args"])
            if got.get("location") != want.get("location") and got.get("query") != want.get("query"):
                continue
            score = sum(got.get(k) == v for k, v in want.items())
            if score > best_score:
                best, best_score = rec, score
        return best

    def call_tool(self, name: str, arguments: dict) -> dict:
        rec = self._lookup(name, arguments)
        self.calls.append({"tool": name, "seconds": 0.0, "units": 0, "is_error": rec is None})
        if rec is None:
            return {"text": f"Offline mode: no recorded reply for {name} with these arguments. "
                            f"Record one with CUBI_RECORD=1, or see fixtures/mcp/INDEX.md.",
                    "is_error": True, "structured": None}
        return {"text": rec["text"], "is_error": rec.get("is_error", False), "structured": None}


class RecordingMCP(CubiMCP):
    """Calls the live connector and saves a sanitised copy of each reply."""

    def call_tool(self, name: str, arguments: dict) -> dict:
        res = super().call_tool(name, arguments)
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"tool": name, "args": arguments, "is_error": res["is_error"],
               "text": sanitise(res["text"]) if not res["is_error"] else res["text"][:300]}
        (FIXTURE_DIR / f"{key(name, arguments)}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        return res


def connect():
    """The connector for this process: live (default), recording, or offline."""
    if os.environ.get("CUBI_OFFLINE") == "1":
        return FixtureMCP()
    if os.environ.get("CUBI_RECORD") == "1":
        return RecordingMCP()
    return CubiMCP()


def write_index() -> None:
    rows = ["# Recorded connector replies", "",
            "Facts only (see agent/fixtures.py). Regenerate with `python -m agent.fixtures`.", "",
            "| file | tool | arguments | listings |", "|---|---|---|---|"]
    for f in sorted(FIXTURE_DIR.glob("*.json")):
        rec = json.loads(f.read_text())
        n = len(listings.parse(rec["text"]))
        rows.append(f"| `{f.name}` | {rec['tool']} | `{json.dumps(rec['args'], ensure_ascii=False)}` | {n} |")
    (FIXTURE_DIR / "INDEX.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    write_index()
    print(f"wrote {FIXTURE_DIR / 'INDEX.md'}")


__all__ = ["FixtureMCP", "RecordingMCP", "connect", "key", "sanitise", "QUOTA_UNITS"]
