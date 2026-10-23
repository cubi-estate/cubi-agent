"""Recent posts on X about a place's housing, read on demand for the home-news turn.

One call to X's recent search (last 7 days) per "what's new" question, only
when X_BEARER_TOKEN is set; otherwise the app links to X's own search page as
before. X bills per post returned (USD 0.005 in Oct 2026), so a daily cap on
posts fetched, kept in code, bounds the bill: X_DAILY_POST_CAP (default 300
posts, USD 1.50 a day). Past the cap the link comes back.

Only the place name and housing keywords are sent to X. Posts are shown live,
with the author's name, handle, date and a link to the post, as X's display
terms ask; nothing is stored or logged (no text, no handles), so a post deleted
on X is never shown again from here. Posts are people's views, not reporting:
the model is told so.

Two rules from the legitimate-interests assessment (cleverdragon
docs/privacy/lia_x_posts.md): an author who objects is blocked by handle
(X_BLOCKED_HANDLES, comma-separated, applied before anything is shown or sent
to the model), and a post that @mentions another account is dropped, so no one
appears here who did not post.

Offline (CUBI_OFFLINE=1) replies come from fixtures/x/, git-ignored: post text
is third-party content.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import httpx

from . import config
from .tavily_tool import english_name

URL = "https://api.x.com/2/tweets/search/recent"
FETCH = 10   # X's minimum max_results
SHOW = 3
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "x"

# Housing words in the demo's six languages (plus Italian); X matches them as whole words.
_WORDS = ('housing', 'rent', '"house prices"', '"property prices"', '"housing crisis"', 'habitação', 'rendas',
          'vivienda', 'alquiler', 'logement', 'loyer', 'Wohnungen', 'Miete', 'Mieten', 'woningmarkt', 'huur',
          'affitti')

# Listing ads and agents' self-promotion are most of what X returns for a city
# plus "property": not what "what's new" means.
_SELLER = re.compile(r"realt|propert|imobili|inmobili|immobili|immo|real.?estate|homes|casas|invest|broker|"
                     r"agent|villas?\b|apartments", re.I)
_AD = re.compile(r"\b(for sale|for rent|à venda|para venda|en venta|se vende|à vendre|à louer|zu verkaufen|"
                 r"zu vermieten|te koop|te huur|in vendita|dm (me|for)|link in bio|\d+\s?(bed|bd|br|quartos|"
                 r"habitaciones|chambres|zimmer)\b|T[0-9]\b)", re.I)
# An @handle, not an email address or a URL path.
_MENTION = re.compile(r"(?<![\w@/])@(\w{1,15})\b")


class XError(RuntimeError):
    pass


class _Budget:
    """Posts fetched today (UTC), in this process. One replica runs the demo."""

    def __init__(self) -> None:
        self.day, self.used, self.lock = None, 0, threading.Lock()

    def take(self, n: int, cap: int) -> bool:
        with self.lock:
            today = dt.datetime.now(dt.timezone.utc).date()
            if today != self.day:
                self.day, self.used = today, 0
            if self.used + n > cap:
                return False
            self.used += n
            return True


BUDGET = _Budget()


def cap() -> int:
    try:
        return max(0, int(os.environ.get("X_DAILY_POST_CAP", "300")))
    except ValueError:
        return 300


def blocked() -> set[str]:
    raw = os.environ.get("X_BLOCKED_HANDLES", "")
    return {h.strip().lstrip("@").lower() for h in raw.split(",") if h.strip().lstrip("@")}


def mentions_others(text: str, handle: str) -> bool:
    return any(m.lower() != handle.lower() for m in _MENTION.findall(text))


def enabled() -> bool:
    return bool(config.X_BEARER_TOKEN) or os.environ.get("CUBI_OFFLINE") == "1"


def query_for(town: str) -> str:
    names = sorted({town, english_name(town)})
    place = " OR ".join(f'"{n}"' if " " in n else n for n in names)
    return f"({place}) ({' OR '.join(_WORDS)}) -is:retweet -is:reply -is:nullcast"


def _key(query: str) -> str:
    return hashlib.sha1(query.lower().encode()).hexdigest()[:12]


def _fetch(query: str, http: httpx.Client) -> dict:
    if os.environ.get("CUBI_OFFLINE") == "1":
        f = FIXTURE_DIR / f"{_key(query)}.json"
        if not f.exists():
            raise XError("offline mode: no recorded X reply")
        return json.loads(f.read_text())
    if not config.X_BEARER_TOKEN:
        raise XError("X is not configured")
    if not BUDGET.take(FETCH, cap()):
        raise XError("today's X post budget is used up")
    r = http.get(URL, params={"query": query, "max_results": FETCH, "sort_order": "relevancy",
                              "tweet.fields": "created_at,lang", "expansions": "author_id",
                              "user.fields": "name,username"},
                 headers={"Authorization": f"Bearer {config.X_BEARER_TOKEN}"})
    if r.status_code in (401, 403):
        raise XError("X rejected the API key")
    if r.status_code == 402:
        raise XError("the X credit balance is used up")
    if r.status_code == 429:
        raise XError("X rate limit reached")
    r.raise_for_status()
    body = r.json()
    if os.environ.get("CUBI_RECORD") == "1":
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        (FIXTURE_DIR / f"{_key(query)}.json").write_text(json.dumps(body, indent=1, ensure_ascii=False))
    return body


def _posts(body: dict) -> list[dict]:
    users = {u["id"]: u for u in (body.get("includes") or {}).get("users", [])}
    block, out = blocked(), []
    for t in body.get("data") or []:
        u = users.get(t.get("author_id")) or {}
        handle, name, text = u.get("username") or "", u.get("name") or "", t.get("text") or ""
        if not handle or handle.lower() in block or mentions_others(text, handle):
            continue
        if _SELLER.search(handle + " " + name) or _AD.search(text):
            continue
        out.append({"id": t["id"], "text": text, "date": (t.get("created_at") or "")[:10], "name": name,
                    "handle": handle, "url": f"https://x.com/{handle}/status/{t['id']}"})
    return out


def recent_posts(place: str, http: httpx.Client | None = None, first_id: int = 1) -> tuple[str, dict]:
    """(text for the model, stats). stats["posts"] are for the page; stats["sources"]
    map "X1" → {url, title, date} so link_citations links [X1] like [S1]."""
    town = place.split(",")[0].strip()
    t0 = time.monotonic()
    body = _fetch(query_for(town), http or httpx.Client(timeout=15.0))
    returned = len(body.get("data") or [])
    posts = _posts(body)[:SHOW]
    sources, out = {}, [f"## Recent posts on X about housing in {town} (last 7 days)",
                        "These are people's posts, not reporting. Say what they discuss as what people on X "
                        "say (\"posts on X mention…\"), cite each by its number, e.g. [X1], and never state "
                        "a post's claim as a fact, a figure or a trend. Don't name the authors: the app shows them."]
    for i, p in enumerate(posts):
        sid = f"X{first_id + i}"
        sources[sid] = {"url": p["url"], "title": f"{p['name']} (@{p['handle']}) on X", "date": p["date"]}
        out.append(f"[{sid}] {p['date']}: " + " ".join(p["text"].split())[:400])
    if not posts:
        out.append(f"(no posts about housing in {town} on X in the last 7 days, other than listing ads)")
    return "\n".join(out), {"posts": [{**p, "sid": sid} for p, sid in zip(posts, sources)],
                            "returned": returned, "seconds": round(time.monotonic() - t0, 2),
                            "sources": sources}
