"""Web server: the agent behind one page.

  .venv/bin/uvicorn agent.server:app --port 8080        # then open http://localhost:8080

POST /api/chat {"message", "session_id"?} streams one turn as NDJSON, one event
per line:

  {"type": "session", "id": ...}              first line; send it back next turn
  {"type": "action", "text": ...}             what the agent is doing (no model reasoning)
  {"type": "answer", "text", "listings", "filter", "skill", "lang", "latency_s"}
  {"type": "error", "code", "text"}           rate limit, demo budget, upstream failure

Privacy: conversations live in this process's memory only, for SESSION_TTL_S
after the last turn, and are never written to disk or to the log. The log
records counters (turns, latency, skill, errors), never message text.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from . import config, llm, steps, wizard
from .loop import Agent, _describe

log = logging.getLogger("cubi_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WEB = Path(__file__).resolve().parent.parent / "web"
MAX_MESSAGE_CHARS = 500
SESSION_TTL_S = int(os.environ.get("SESSION_TTL_S", "1800"))
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "300"))
MAX_TURNS_PER_SESSION = int(os.environ.get("MAX_TURNS_PER_SESSION", "30"))
IP_TURNS_PER_MIN = int(os.environ.get("IP_TURNS_PER_MIN", "8"))
IP_TURNS_PER_DAY = int(os.environ.get("IP_TURNS_PER_DAY", "120"))
# Whole-demo spend guard: Token Factory, Tavily and the connector's quota.
DEMO_TURNS_PER_DAY = int(os.environ.get("DEMO_TURNS_PER_DAY", "1500"))
# Behind a proxy (Fly, Render, Nebius) the client address is the first X-Forwarded-For hop.
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"


class _Session:
    def __init__(self) -> None:
        self.agent = Agent()
        self.lock = threading.Lock()
        self.turns = 0
        self.last = time.monotonic()


class Sessions:
    """In-memory, least-recently-used, expiring. Nothing is persisted."""

    def __init__(self) -> None:
        self._s: OrderedDict[str, _Session] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, sid: str | None) -> tuple[str, _Session]:
        now = time.monotonic()
        with self._lock:
            for k in [k for k, v in self._s.items() if now - v.last > SESSION_TTL_S]:
                del self._s[k]
            if sid and sid in self._s:
                self._s.move_to_end(sid)
                return sid, self._s[sid]
            while len(self._s) >= MAX_SESSIONS:
                self._s.popitem(last=False)
            sid = secrets.token_urlsafe(16)
            self._s[sid] = _Session()
            return sid, self._s[sid]

    def drop(self, sid: str) -> None:
        with self._lock:
            self._s.pop(sid, None)

    def __len__(self) -> int:
        return len(self._s)


class Limits:
    def __init__(self) -> None:
        self._minute: dict[str, deque] = defaultdict(deque)
        self._day: dict[tuple[str, str], int] = defaultdict(int)
        self._demo: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def check(self, ip: str) -> str | None:
        """None if the turn may run (and is counted), else an error code."""
        now, day = time.time(), time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            if self._demo[day] >= DEMO_TURNS_PER_DAY:
                return "demo_budget"
            q = self._minute[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= IP_TURNS_PER_MIN:
                return "rate_minute"
            if self._day[(ip, day)] >= IP_TURNS_PER_DAY:
                return "rate_day"
            q.append(now)
            self._day[(ip, day)] += 1
            self._demo[day] += 1
            for k in [k for k in self._day if k[1] != day]:
                del self._day[k]
            # Addresses are kept for the limits only: drop one a minute after its last turn.
            for k in [k for k, v in self._minute.items() if not v or now - v[-1] > 60]:
                del self._minute[k]
            return None


ERRORS = {
    "demo_budget": "The demo's daily budget is used up. It resets at midnight UTC — or run the agent "
                   "yourself from the GitHub repo.",
    "rate_minute": "That's a lot of questions in a minute — wait a moment and try again.",
    "rate_day": "You've reached today's limit for this demo. It resets at midnight UTC.",
    "session_full": "This conversation is long enough — start a new one to keep going.",
    "too_long": f"Please keep a message under {MAX_MESSAGE_CHARS} characters.",
    "busy": "Still answering your previous message.",
    "upstream": "Something went wrong reaching the model or the listing service. Try again in a moment.",
}

app = FastAPI(title="cubi-agent", docs_url=None, redoc_url=None)
sessions, limits = Sessions(), Limits()


@app.on_event("startup")
def _prewarm_steps() -> None:
    """Translate the step log for common languages beyond the six (agent/steps.py), in the background."""
    if config.NEBIUS_API_KEY and os.environ.get("STEPS_PREWARM", "x").strip():
        steps.prewarm(llm.client())
    # The wizard's first visitor would otherwise wait ~5 s for the listing counts.
    threading.Thread(target=wizard.stats, daemon=True).start()


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


def _ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _card(c: dict, f) -> dict:
    """Card for the page: tags de-duplicated, the ones matching the request first."""
    wanted = {x.lower() for x in (f.features if f else [])} | ({"garage", "parking"} if f and f.has_parking else set())
    seen, tags = set(), []
    for t in c.get("tags", []):
        if t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    tags.sort(key=lambda t: not any(w in t.lower() for w in wanted))
    return {**c, "tags": tags}


def _line(ev: dict) -> bytes:
    return (json.dumps(ev, ensure_ascii=False) + "\n").encode()


def _error(code: str, sid: str | None = None) -> StreamingResponse:
    def gen() -> Iterator[bytes]:
        if sid:
            yield _line({"type": "session", "id": sid})
        yield _line({"type": "error", "code": code, "text": ERRORS[code]})
    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _turn(sid: str, sess: _Session, message: str) -> Iterator[bytes]:
    yield _line({"type": "session", "id": sid})
    if not sess.lock.acquire(blocking=False):
        yield _line({"type": "error", "code": "busy", "text": ERRORS["busy"]})
        return
    t0 = time.monotonic()
    skill, ok = "-", False
    try:
        for ev in sess.agent.turn(message):
            if ev["type"] == "answer":
                skill = ev["skill"]
                f = sess.agent.filter
                ev = {"type": "answer", "text": ev["text"],
                      "listings": [_card(c, f) for c in ev.get("listings", [])],
                      "inventory": ev.get("inventory"),
                      "similar": ev.get("similar"),
                      "suggestions": ev.get("suggestions") or [],
                      "price_history": ev.get("price_history"),
                      "x_url": ev.get("x_url"), "x_posts": ev.get("x_posts") or [],
                      "filter": _describe(f, ev["lang"]) if f else None,
                      "skill": ev["skill"], "lang": ev["lang"], "latency_s": ev["latency_s"]}
            else:
                ev = {"type": "action", "text": ev.get("text", "")}
            yield _line(ev)
        ok = True
    except Exception as e:  # noqa: BLE001 — the user gets a friendly line, the log gets the class
        log.warning("turn failed: %s", type(e).__name__)
        yield _line({"type": "error", "code": "upstream", "text": ERRORS["upstream"]})
    finally:
        sess.turns += 1
        sess.last = time.monotonic()
        sess.lock.release()
        # Counters only: never the message or the answer.
        log.info("turn ok=%s skill=%s seconds=%.1f session_turns=%d sessions=%d",
                 ok, skill, time.monotonic() - t0, sess.turns, len(sessions))


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    message = body.message.strip()
    if len(message) > MAX_MESSAGE_CHARS:
        return _error("too_long", body.session_id)
    code = limits.check(_ip(request))
    if code:
        return _error(code, body.session_id)
    sid, sess = sessions.get(body.session_id)
    if sess.turns >= MAX_TURNS_PER_SESSION:
        return _error("session_full", sid)
    return StreamingResponse(iterate_in_threadpool(_turn(sid, sess, message)),
                             media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/reset")
async def reset(body: dict):
    if isinstance(body.get("session_id"), str):
        sessions.drop(body["session_id"])
    return {"ok": True}


@app.get("/api/wizard")
async def wizard_stats():
    """Listing counts for the home wizard's tiles; aggregate only, cached six hours."""
    data = await run_in_threadpool(wizard.stats)
    return JSONResponse(data or {"countries": {}}, headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/health")
async def health(request: Request):
    # `forwarded` tells an operator whether the platform's proxy passes the client
    # address; without it every visitor shares one per-IP limit.
    return JSONResponse({"ok": True, "sessions": len(sessions),
                         "forwarded": bool(request.headers.get("x-forwarded-for")),
                         "trust_proxy": TRUST_PROXY, "build": config.BUILD})


def _page() -> str:
    """index.html with the build on its stylesheet and script URLs: a browser that cached
    an older style.css (no Cache-Control then) showed the new wizard unstyled, 2026-10-24."""
    html = (WEB / "index.html").read_text()
    for asset in ("style.css", "app.js", "wizard.js"):
        html = html.replace(f'"/static/{asset}"', f'"/static/{asset}?v={config.BUILD}"')
    return html


@app.get("/")
async def index():
    return HTMLResponse(_page(), headers={"Cache-Control": "no-cache"})


class _Static(StaticFiles):
    """Revalidate every time (cheap: ETag → 304), so a new build is never hidden by a cache."""

    async def get_response(self, path, scope):
        res = await super().get_response(path, scope)
        res.headers.setdefault("Cache-Control", "no-cache")
        return res


app.mount("/static", _Static(directory=WEB), name="static")
