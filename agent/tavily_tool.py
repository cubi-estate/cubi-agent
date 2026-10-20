"""Area research through Tavily web search, for comparing places (schools, transport, ...).

One Tavily "basic" search per place and topic (1 credit each; at most 3 places
× 3 topics). Social-media pages are excluded: in the first live run they were
most of the results and carried the weakest claims. The tool returns numbered
sources — [S1], [S2] … with title, URL, date when Tavily has one, and a short
excerpt. The model cites the numbers; `link_citations` turns them into links
in code, so the model never writes a URL here. Cubi's listing data is not sent to Tavily: only
the place names and topics.

Offline (CUBI_OFFLINE=1) replies come from fixtures/tavily/, which is
git-ignored: excerpts are third-party text.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import config

URL = "https://api.tavily.com/search"
MAX_PLACES = 3
MAX_TOPICS = 3
RESULTS_PER_QUERY = 3
EXCERPT_CHARS = 300
EXCLUDE_DOMAINS = ["facebook.com", "instagram.com", "tiktok.com", "youtube.com", "x.com", "twitter.com",
                   "pinterest.com", "linkedin.com"]
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
                "places": {"type": "array", "items": {"type": "string"}, "description": "Towns, cities or neighbourhoods WITH their country, e.g. ['Porto, Portugal', 'Valencia, Spain'] — names like Valencia exist on several continents."},
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
    r = http.post(URL, json={"query": query, "search_depth": "basic", "max_results": RESULTS_PER_QUERY,
                             "include_answer": False, "topic": "general", "exclude_domains": EXCLUDE_DOMAINS},
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
    """Returns (text for the model, stats). stats["sources"] maps "S1" → {url, title, date}."""
    places = [p.strip() for p in places if p and p.strip()][:MAX_PLACES]
    topics = [t.strip() for t in topics if t and t.strip()][:MAX_TOPICS] or ["quality of life"]
    http = http or httpx.Client(timeout=20.0)
    out, sources, stats = [], {}, {"searches": 0, "seconds": 0.0}
    seen: dict[str, str] = {}
    pairs = [(place, topic) for place in places for topic in topics]
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(6, len(pairs) or 1)) as pool:  # searches are independent
        found = dict(zip(pairs, pool.map(lambda pt: _search(query_for(*pt), http), pairs)))
    stats["searches"] = len(pairs)
    stats["seconds"] = round(time.monotonic() - t0, 2)
    for place in places:
        out.append(f"## {place}")
        for topic in topics:
            results = [r for r in found[(place, topic)] if _mentions(r, place)]
            out.append(f"### {topic}")
            if not results:
                out.append("(no sources found)")
            for res in results:
                url = res.get("url", "")
                sid = seen.get(url)
                if sid is None:
                    sid = seen[url] = f"S{len(seen) + 1}"
                    sources[sid] = {"url": url, "title": (res.get("title") or "").strip(),
                                    "date": res.get("published_date")}
                excerpt = " ".join((res.get("content") or "").split())[:EXCERPT_CHARS]
                date = res.get("published_date") or "undated"
                out.append(f"[{sid}] {sources[sid]['title']} ({_domain(url)}, {date})\n   {excerpt}")
        out.append("")
    stats["sources"] = sources
    return "\n".join(out), stats


def query_for(place: str, topic: str) -> str:
    # "public transport in Valencia, Spain" returned public.io, the NYT and FEMA: Tavily
    # weighs the first words. Place first, then the topic, reads as one subject.
    return f"{place}: {topic} for residents"


def _plain(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _mentions(result: dict, place: str) -> bool:
    """Drop off-topic hits: the page must name the place (its first part, accents folded)."""
    name = _plain(place.split(",")[0]).strip()
    blob = _plain(" ".join(str(result.get(k) or "") for k in ("title", "content", "url")))
    return not name or name in blob


def _domain(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url


_JUNK_CITATION = re.compile(r"【[^】]*】")


def link_citations(answer: str, sources: dict[str, dict], lang: str = "en") -> tuple[str, int]:
    """[S3] → [S3](url). Unknown ids and the model's internal citation markup are removed.
    Returns (answer, citations linked)."""
    answer = _JUNK_CITATION.sub("", answer)
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        ids = [x.strip() for x in m.group(1).split(",")]
        links = [f"[{i}]({sources[i]['url']})" for i in ids if i in sources]
        n += len(links)
        return " ".join(links)

    answer = re.sub(r"\[((?:S\d+\s*,\s*)*S\d+)\](?!\()", repl, answer)
    answer = re.sub(r"[ \t]+([.,;:])", r"\1", answer)
    return answer.rstrip() + "\n\n" + _footer(answer, sources, n, lang), n


_SOURCES = {"en": ("Sources", "The answer above does not cite them one by one; check before relying on it."),
            "pt": ("Fontes", "A resposta acima não as cita uma a uma; confirme antes de confiar nela."),
            "es": ("Fuentes", "La respuesta no las cita una por una; compruébelo antes de fiarse."),
            "fr": ("Sources", "La réponse ci-dessus ne les cite pas une à une ; vérifiez avant de vous y fier."),
            "de": ("Quellen", "Die Antwort oben belegt sie nicht einzeln; bitte vor dem Verlassen darauf prüfen."),
            "nl": ("Bronnen", "Het antwoord hierboven verwijst er niet per bewering naar; controleer dit eerst.")}


def _footer(answer: str, sources: dict[str, dict], cited: int, lang: str) -> str:
    """Cited sources (or, if none were cited, every source) with title, site and date."""
    label, uncited = _SOURCES.get(lang, _SOURCES["en"])
    used = [i for i in sources if f"[{i}](" in answer] if cited else list(sources)
    rows = [f"- [{i}]({sources[i]['url']}) {sources[i]['title'][:90]} — {_domain(sources[i]['url'])}"
            + (f", {sources[i]['date']}" if sources[i].get("date") else "") for i in used]
    head = f"**{label}**" + ("" if cited else f" — _{uncited}_")
    return head + "\n" + "\n".join(rows)
