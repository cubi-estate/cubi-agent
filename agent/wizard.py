"""Statistics for the home wizard's region and country tiles (web/wizard.js).

Two connector calls, cached for six hours and shared by every visitor:
`corpus_stats` for active listings per country and `get_daily_new_listing_stats`
for homes added in the last seven completed days. Per-country `corpus_stats`
calls aren't used: their 30-day series are dominated by one-off re-ingests.
"""
from __future__ import annotations

import json
import threading
import time

from .fixtures import connect

TTL_S = 6 * 3600
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "data": None}


def _json(res: dict) -> dict:
    if res["is_error"]:
        raise ValueError(res["text"][:200])
    out = json.loads(res["text"])
    if isinstance(out, dict) and isinstance(out.get("result"), str):
        out = json.loads(out["result"])
    return out


def fetch(mcp) -> dict:
    corpus = _json(mcp.call_tool("corpus_stats", {"days": 1}))
    new = _json(mcp.call_tool("get_daily_new_listing_stats", {}))
    countries: dict[str, dict] = {}
    for row in corpus.get("active_by_country") or []:
        countries.setdefault(row["country"], {})["homes"] = int(row.get("active") or 0)
    for row in new.get("countries") or []:
        if row.get("country") in countries:
            countries[row["country"]]["new_7d"] = int(row.get("total7") or 0)
    return {"as_of": new.get("refreshed_at") or time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "total": corpus.get("active_listings"), "countries": countries}


def stats(mcp=None) -> dict | None:
    """Cached statistics, or the last good ones (or None) if the connector fails."""
    with _lock:
        if _cache["data"] is not None and time.monotonic() - _cache["at"] < TTL_S:
            return _cache["data"]
        try:
            _cache["data"] = fetch(mcp or connect())
            _cache["at"] = time.monotonic()
        except Exception:  # noqa: BLE001 - the wizard works without numbers
            _cache["at"] = time.monotonic() - TTL_S + 300  # retry in five minutes
        return _cache["data"]
