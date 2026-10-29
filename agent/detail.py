"""The listing pane: one home in full, read when its card is tapped.

Four sources, read side by side, then one fast model call:
  - get_listing (the connector): title, facts, the agency's description in the
    user's language where Cubi has it, every tag by section, and the image list
    when the listing payload carries one;
  - find_similar_elsewhere paired with itself: Cubi's profile of the home —
    surroundings (noise, air, flood, wildfire…), minutes on foot to daily
    needs, climate, €/m²;
  - find_similar_homes: up to three homes like it in the same market, picked by
    Cubi's similarity model (a 50-d PCA embedding of each listing's catalogued
    features, nearest neighbours, then a ranker on stated features, size and
    place and asking price), each with the ranker's own reason;
  - Nemotron (nano, thinking off): a brief in the user's language — a TLDR,
    highlights, things to check before deciding, and the description translated
    when it isn't in the user's language. Facts only, from the listing; the
    price-verdict guard runs on it like on every answer.

The pane is read once per home per conversation and kept in memory with it.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import guards, listings, llm, similar as similarmod
from .mcp_client import MCPError

MAX_DESC = 2500
# Cubi serves the description in these languages itself; the model translates only for the others.
CUBI_LANGS = ("en", "pt", "es", "de")
SKIP = {"description", "continue on cubi", "images", "contact"}

SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "watch_outs": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
    },
    "required": ["tldr", "highlights", "watch_outs", "description"],
    "additionalProperties": False,
}

SYSTEM = """You write a short, factual brief of one property listing for a buyer or tenant, in {lang}.
Use only the listing text, tags and area data given. Never add market knowledge, and never judge the asking price: no "bargain", "good value", "overpriced", "fair".
Return JSON with:
- tldr: one or two sentences, at most 45 words — what and where, size, and the one thing that stands out.
- highlights: 3 to 5 short items the listing states that a buyer would like (views, outdoor space, condition, light, extras).
- watch_outs: 0 to 4 short items to check before deciding, only when the listing, tags or area data say so: needs renovation, price on request, low energy class, business use only, minimum lease, no lift, ground floor, loud road nearby, high fire-weather or flood risk, far from the coast when sea view is claimed. An empty list when there is nothing.
- description: the description translated into {lang} when it is written in another language; an empty string when it already is in {lang}.
Every item in {lang}. No markdown, no URLs, no contact details."""


def parse(text: str) -> dict:
    """A get_listing reply → fields: title, location, facts, description, sections, images, links."""
    out: dict = {"title": "", "location": "", "description": "", "sections": {}, "images": [],
                 "url": "", "ask_url": "", "contact_url": "", "id": ""}
    section, seen = "", set()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# ") and not out["title"]:
            out["title"] = line[2:].strip()
        elif line.startswith("**Location:**"):
            out["location"] = listings._dedupe(line.split("**Location:**", 1)[1].strip())
        elif line.startswith("**Details:**"):
            listings._facts_line(line.split("**Details:**", 1)[1].strip(), out)
        elif line.startswith("**URL:**"):
            out["url"] = line.split("**URL:**", 1)[1].strip()
        elif line.startswith("**ID:**"):
            out["id"] = line.split("**ID:**", 1)[1].strip()
        elif line.startswith("## "):
            section = line[3:].strip()
        elif section:
            low = section.lower()
            if low == "description":
                if line:
                    out["description"] += (" " if out["description"] else "") + line
            elif low == "images":
                if line.startswith("- ") and line[2:].strip().startswith("http"):
                    out["images"].append(line[2:].strip())
            elif low == "continue on cubi":
                m = re.search(r"https?://\S+", line)
                if m and "intent=contact" in m.group(0):
                    out["contact_url"] = m.group(0)
                elif m and "intent=ask" in m.group(0):
                    out["ask_url"] = m.group(0)
            elif low not in SKIP and line.startswith("- "):
                tag = line[2:].strip()
                if tag and tag.lower() not in seen:
                    seen.add(tag.lower())
                    out["sections"].setdefault(section, []).append(tag)
    return out


def profile(text: str) -> dict:
    """The home's own profile from a pair comparison with itself."""
    try:
        body = json.loads(text)
        if isinstance(body.get("result"), str):
            body = json.loads(body["result"])
    except (json.JSONDecodeError, AttributeError):
        return {}
    seed = (body or {}).get("seed") if isinstance(body, dict) else None
    if not body.get("ok") or not isinstance(seed, dict):
        return {}
    env = seed.get("environment") or {}
    return {"environment": [{"key": k, **(env.get(k) or {"state": "unknown"})} for k in similarmod.ENVIRONMENT if k in env],
            "minutes": {k: v for k, v in (seed.get("minutes") or {}).items() if v is not None},
            "climate": seed.get("climate") or {},
            "eur_per_m2": seed.get("eur_per_m2")}


SIMILAR_TOOL = "find_similar_homes"   # Cubi's own similarity model: concept PCA embedding + hybrid ranker
MAX_SIMILAR = 3
SIMILAR_LANGS = CUBI_LANGS + ("fr", "nl", "ru")   # the connector's `why` sentences come in these


def _price(c: dict) -> str | None:
    if not c.get("price"):
        return None
    text = f"{int(c['price']):,}".replace(",", " ") + f" {c.get('currency') or 'EUR'}"
    period = str(c.get("price_period") or "").lower()
    return text + ("/mo" if "month" in period else f"/{period}" if period else "")


def similar_homes(text: str | None) -> dict:
    """The connector's `find_similar_homes` reply → what the pane draws:
    {"similar": [{id, title, price_text, type, bedrooms, living_area, place, url, ask_url, why, similarity}],
     "similar_method": {embedding, ranker, scope}}. Empty when the tool failed or is absent."""
    empty = {"similar": [], "similar_method": {}}
    if not text:
        return empty
    try:
        body = json.loads(text)
        if isinstance(body.get("result"), str):
            body = json.loads(body["result"])
    except (json.JSONDecodeError, AttributeError):
        return empty
    if not isinstance(body, dict) or not body.get("ok"):
        return empty
    out = []
    for m in (body.get("matches") or [])[:MAX_SIMILAR]:
        c = m.get("card") or {}
        if not c.get("id"):
            continue
        out.append({"id": c["id"], "title": c.get("title") or "", "price_text": _price(c),
                    "type": c.get("object_type") or "", "bedrooms": c.get("bedrooms"), "living_area": c.get("living_area"),
                    "place": ", ".join(x for x in (c.get("city"), c.get("country")) if x),
                    "url": c.get("url") or "", "ask_url": c.get("ask_cubi_url") or "",
                    "why": (m.get("why") or "").strip(), "similarity": m.get("similarity")})
    return {"similar": out, "similar_method": body.get("method") or {}}


def _area_text(prof: dict) -> str:
    bits = []
    for e in prof.get("environment") or []:
        if e.get("state") in ("yes", "no"):
            bits.append(f"{e['key']}: {e['state']}" + (f" ({e['value']} {e.get('unit', '')})" if e.get("value") is not None else ""))
    for k, v in (prof.get("minutes") or {}).items():
        bits.append(f"{k}: {v} min")
    return "; ".join(bits)


def brief(cli, listing: dict, prof: dict, lang: str, lang_name: str) -> dict:
    """The model's brief, guarded. Empty fields when the model fails."""
    empty = {"tldr": "", "highlights": [], "watch_outs": [], "description": ""}
    facts = " | ".join(str(listing.get(k)) for k in ("type", "bedrooms", "bathrooms", "living_area", "plot_area", "price_text")
                       if listing.get(k) is not None)
    tags = "\n".join(f"{s}: {', '.join(items)}" for s, items in (listing.get("sections") or {}).items())
    user = (f"Title: {listing.get('title')}\nLocation: {listing.get('location')}\nFacts: {facts}\n"
            f"Description: {(listing.get('description') or '')[:MAX_DESC]}\nTags by section:\n{tags}\n"
            f"Area data: {_area_text(prof) or 'none'}")
    try:
        r = cli.chat.completions.create(
            model=llm.model("nano"),
            messages=[{"role": "system", "content": SYSTEM.format(lang=lang_name)}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {"name": "ListingBrief", "schema": SCHEMA, "strict": True}},
            temperature=0, max_tokens=1500, extra_body=llm.NO_THINK)
        body = json.loads(r.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001 — the pane still shows the listing itself
        return empty
    if not isinstance(body, dict):
        return empty
    def clean(s: str) -> str:
        s, _ = guards.drop_price_verdicts(str(s), lang)
        s, _ = guards.scrub_contacts(s)
        if re.search(r"\d[\d .-]{6,}\d", s) and re.search(r"(?:\d\D{0,2}){8,}", s):
            return ""   # a phone number the agency wrote into its text: the item goes
        return s.strip()

    return {"tldr": clean(body.get("tldr") or ""),
            "highlights": [clean(x) for x in (body.get("highlights") or []) if clean(x)][:5],
            "watch_outs": [clean(x) for x in (body.get("watch_outs") or []) if clean(x)][:4],
            # The model rewrote an English description "in English" (local 2026-10-26):
            # a translation counts only where Cubi could not have translated already.
            "description": clean(body.get("description") or "") if lang not in CUBI_LANGS else ""}


def read(mcp, cli, ref: str, *, data_lang: str, lang: str, lang_name: str, timings: list | None = None) -> dict:
    """The pane for one listing. Connector reads side by side, then the brief."""
    t0 = time.monotonic()

    def listing_text():
        try:
            res = mcp.call_tool("get_listing", {"listing_id": ref, "lang": data_lang})
        except (MCPError, httpx.HTTPError):
            return None
        return None if res["is_error"] else res["text"]

    def profile_text():
        try:
            res = mcp.call_tool(similarmod.TOOL, {"listing_id": ref, "compare_with": ref, "lang": data_lang})
        except (MCPError, httpx.HTTPError):
            return None
        return None if res["is_error"] else res["text"]

    def similar_text():
        # A connector without the tool answers with an error: the pane then shows no matches.
        try:
            res = mcp.call_tool(SIMILAR_TOOL, {"listing_id": ref, "lang": lang if lang in SIMILAR_LANGS else "en",
                                               "limit": MAX_SIMILAR})
        except (MCPError, httpx.HTTPError):
            return None
        return None if res["is_error"] else res["text"]

    with ThreadPoolExecutor(max_workers=3) as pool:
        text_f, prof_f, sim_f = pool.submit(listing_text), pool.submit(profile_text), pool.submit(similar_text)
        text, prof_text, sim_text = text_f.result(), prof_f.result(), sim_f.result()
    if timings is not None:
        timings.append(("listing detail + profile + similar homes, in parallel", round(time.monotonic() - t0, 2)))
    if not text:
        return {"ok": False, "id": ref}
    listing = parse(text)
    prof = profile(prof_text) if prof_text else {}
    prof.update(similar_homes(sim_text))
    t1 = time.monotonic()
    summary = brief(cli, listing, prof, lang, lang_name)
    if timings is not None:
        timings.append(("listing brief (nano)", round(time.monotonic() - t1, 2)))
    out = {"ok": True, **listing, **prof, **summary, "id": listing.get("id") or ref}
    out["translated"] = bool(summary["description"])
    out["description"] = summary["description"] or listing["description"]
    return out
