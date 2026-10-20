"""Area research through Tavily web search, for comparing places (schools, transport, ...).

One Tavily "basic" search per place (1 credit each), at most 3 places per call.
The tool returns sources only — title, URL, publication date when Tavily has
one, and a short excerpt — and the model must cite them; the URL guard drops
any link not in this output. Cubi's listing data is not sent to Tavily: only
the place names and topics.

Offline (CUBI_OFFLINE=1) replies come from fixtures/tavily/, which is
git-ignored: excerpts are third-party text.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx

from . import config

URL = "https://api.tavily.com/search"
MAX_PLACES = 3
EXCERPT_CHARS = 300
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "tavily"

TOOL = {
    "type": "function",
    "function": {
        "name": "research_area",
        "description": (
            "Web sources about living in up to three places — schools, public transport, safety, "
            "healthcare, beaches, cost of living or whatever the user asked. Returns titles, URLs, dates "
            "and short excerpts to cite. Use for comparing areas, not for listings or prices of homes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "places": {"type": "array", "items": {"type": "string"}, "description": "Towns, cities or neighbourhoods, e.g. ['Porto', 'Valencia']."},
                "topics": {"type": "array", "items": {"type": "string"}, "description": "What to compare, in English, e.g. ['international schools', 'public transport']."},
            },
            "required": ["places", "topics"],
        },
    },
}


class TavilyError(RuntimeError):
    pass


def _key(query: str) -> str:
    return hashlib.sha1(query.lower().encode()).hexdigest()[:12]


def _search(query: str, http: httpx.Client) -> list[dict]:
    if os.environ.get("CUBI_OFFLINE") == "1":
        f = FIXTURE_DIR / f"{_key(query)}.json"
        if not f.exists():
            raise TavilyError(f"offline mode: no recorded Tavily reply for {query!r}")
        return json.loads(f.read_text())["results"]
    if not config.TAVILY_API_KEY:
        raise TavilyError("area research is not configured (TAVILY_API_KEY is not set)")
    r = http.post(URL, json={"query": query, "search_depth": "basic", "max_results": 5,
                             "include_answer": False, "topic": "general"},
                  headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"})
    if r.status_code in (401, 403):
        raise TavilyError("Tavily rejected the API key")
    if r.status_code == 429:
        raise TavilyError("Tavily rate limit or credit limit reached")
    r.raise_for_status()
    results = r.json().get("results", [])
    if os.environ.get("CUBI_RECORD") == "1":
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        (FIXTURE_DIR / f"{_key(query)}.json").write_text(
            json.dumps({"query": query, "results": results}, indent=1, ensure_ascii=False))
    return results


def research_area(places: list[str], topics: list[str], http: httpx.Client | None = None) -> tuple[str, dict]:
    """Returns (text for the model, stats)."""
    places = [p.strip() for p in places if p and p.strip()][:MAX_PLACES]
    topics = [t.strip() for t in topics if t and t.strip()][:4] or ["quality of life"]
    http = http or httpx.Client(timeout=20.0)
    out, stats = [], {"searches": 0, "sources": 0, "seconds": 0.0}
    for place in places:
        query = f"{place} {', '.join(topics)} for residents"
        t0 = time.monotonic()
        results = _search(query, http)
        stats["searches"] += 1
        stats["seconds"] = round(stats["seconds"] + time.monotonic() - t0, 2)
        out.append(f"## {place} — sources for: {', '.join(topics)}")
        if not results:
            out.append("(no sources found)")
        for i, res in enumerate(results, 1):
            excerpt = " ".join((res.get("content") or "").split())[:EXCERPT_CHARS]
            date = res.get("published_date") or "date not given"
            out.append(f"{i}. {res.get('title', '').strip()} — {res.get('url', '')} ({date})\n   {excerpt}")
            stats["sources"] += 1
        out.append("")
    return "\n".join(out), stats
