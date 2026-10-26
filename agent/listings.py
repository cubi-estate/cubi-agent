"""Parse the connector's listing cards into facts, and rebuild cards from facts.

`filter_listings` and `search_properties` both return markdown cards:

    **1. T3 Apartment in Bougado**
       Location: Bougado, Trofa, Porto, Portugal, Porto District
       Apartment | 3 bd | 3 ba | 134 m2 living | 335 000 EUR
       <description excerpt>
       URL: https://cubi.estate/r/iad_pt%3A158006
       ID: iad_pt:158006
       Last changed: 2026-09-22
       Ask Cubi (...): https://www.cubi.estate/chat?listing_id=...
       Tags: Garage

`parse()` keeps the facts (used by the eval to check constraints), and
`render_facts()` rebuilds a card without the title or description, so recorded
fixtures carry no text copied from the original listing.
"""
from __future__ import annotations

import re

_HEAD = re.compile(r"^\*\*(\d+)\.\s+(.*?)\*\*\s*$")
_NUM = re.compile(r"[\d][\d .,]*")


def _number(s: str) -> float | None:
    m = _NUM.search(s)
    if not m:
        return None
    digits = re.sub(r"[ .,](?=\d{3}\b)", "", m.group().strip())
    try:
        return float(digits.replace(",", "."))
    except ValueError:
        return None


def _facts_line(line: str, out: dict) -> None:
    parts = [p.strip() for p in line.split("|")]
    out["type"] = parts[0]
    for p in parts[1:]:
        low = p.lower()
        if low.endswith(" bd"):
            out["bedrooms"] = _number(p)
        elif low.endswith(" ba"):
            out["bathrooms"] = _number(p)
        elif "m2" in low and "plot" in low:
            # "112 m2 living | 1420 m2 plot": the plot came last and overwrote the
            # living area (1420 m2 village houses on the cards, live 2026-10-24).
            out["plot_area"] = _number(p)
        elif "m2" in low:
            out["living_area"] = _number(p)
        # Cubi prices in the listing's own currency: złoty, koruna, forint, leu,
        # lev and Nordic krona too (Polish rents showed "—" on the cards).
        elif re.search(r"\b(eur|usd|gbp|chf|pln|czk|huf|ron|bgn|sek|dkk|nok)\b", low) or "price on request" in low:
            # "495 000 → 395 000 EUR 🔻20%": the asking price is the one after the
            # arrow (a Lake Orta villa carried its old price, live 2026-10-26).
            out["price"] = _number(p.split("→")[-1] if "→" in p else p)
            out["price_text"] = p


def _dedupe(location: str) -> str:
    """"Italy, Lombardy, Gittana, Lombardy" → "Italy, Lombardy, Gittana" (the region
    repeated after the city on Italian cards, live 2026-10-26)."""
    seen, out = set(), []
    for part in (x.strip() for x in location.split(",")):
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return ", ".join(out)


def parse(text: str) -> list[dict]:
    cards: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        head = _HEAD.match(line)
        if head:
            cur = {"n": int(head.group(1))}
            cards.append(cur)
            continue
        if cur is None or not line:
            continue
        if line.startswith("Location:"):
            cur["location"] = _dedupe(line[9:].strip())
        elif line.startswith("URL:"):
            cur["url"] = line[4:].strip()
        elif line.startswith("ID:"):
            cur["id"] = line[3:].strip()
        elif line.startswith("Last changed:"):
            cur["updated"] = line[13:].strip()
        elif line.startswith("Ask Cubi"):
            cur["ask_url"] = line.split(": ", 1)[-1].strip()
        elif line.startswith("Tags:"):
            cur["tags"] = [t.strip() for t in line[5:].split(",") if t.strip()]
        elif "|" in line and "type" not in cur:
            _facts_line(line, cur)
    return cards


def detail_tags(text: str) -> list[str]:
    """Every tag in a get_listing detail: the "- item" lines of its sections (Views,
    Outdoor, Interior…), not the description or the links. De-duplicated, in order."""
    tags, seen, section = [], set(), ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif line.startswith("- ") and section and section not in ("description", "continue on cubi"):
            tag = line[2:].strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
    return tags


def header(text: str) -> str:
    """The summary line(s) before the first card."""
    out = []
    for line in text.splitlines():
        if _HEAD.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out).strip()


_STREET = re.compile(r"^(rua|r\.|calle|c/|carrer|avenida|av\.|avda|travessa|largo|praca|plaza|via|viale|"
                     r"rue|avenue|boulevard|chemin|impasse|allee)\b|(strasse|straße|str\.|weg|gasse|platz|"
                     r"straat|laan|plein|gracht)$", re.I)


def places(location: str) -> list[str]:
    """The place names of a card's Location line, without street or house number.

    Everything up to the last component holding a digit is the address; street
    words catch addresses written without a number."""
    parts = [x.strip() for x in location.split(",") if x.strip()]
    last_digit = max((i for i, x in enumerate(parts) if re.search(r"\d", x)), default=-1)
    return [x for x in parts[last_digit + 1:] if not _STREET.search(x)]


def render_facts(text: str) -> str:
    """The same reply with each card reduced to facts (no title, no description)."""
    return render_cards(header(text), parse(text))


def render_cards(head: str, cards: list[dict]) -> str:
    parts = [head, ""]
    for c in cards:
        place = next(iter(places(c.get("location") or "")), "")
        parts.append(f"**{c['n']}. {c.get('type', 'Home')} in {place}**")
        if c.get("location"):
            parts.append(f"   Location: {', '.join(places(c['location']))}")
        facts = [c.get("type", "")]
        if c.get("bedrooms") is not None:
            facts.append(f"{c['bedrooms']:.0f} bd")
        if c.get("bathrooms") is not None:
            facts.append(f"{c['bathrooms']:.0f} ba")
        if c.get("living_area") is not None:
            facts.append(f"{c['living_area']:.0f} m2 living")
        if c.get("price_text"):
            facts.append(c["price_text"])
        parts.append("   " + " | ".join(f for f in facts if f))
        for key, label in (("url", "URL"), ("id", "ID"), ("updated", "Last changed"), ("ask_url", "Ask Cubi")):
            if c.get(key):
                parts.append(f"   {label}: {c[key]}")
        if c.get("tags"):
            parts.append("   Tags: " + ", ".join(c["tags"][:5]))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


_LABELS = ("Location:", "URL:", "ID:", "Last changed:", "Ask Cubi", "Tags:", "Image:")


def _excerpt(block: list[str]) -> str:
    """The card's description excerpt, folded: the first line that is neither the
    title, a labelled line nor the facts line."""
    for raw in block[1:]:
        line = raw.strip()
        if not line or line.startswith(_LABELS) or " | " in line:
            continue
        return re.sub(r"[^a-z0-9]+", "", line.lower())[:80]
    return ""


def collapse(text: str, limit: int) -> tuple[str, dict[str, list[str]], list[dict]]:
    """The same reply without copies of a home: the same description text and
    asking price (and living area, when both give one) under different ids — a
    Sierra Blanca villa came as three Rentola cards at €18,000 (live 2026-10-26).
    Returns the text (renumbered), {kept id: [copy ids]} and the kept cards."""
    blocks: list[list[str]] = []
    for raw in text.splitlines():
        if _HEAD.match(raw.strip()):
            blocks.append([raw])
        elif blocks:
            blocks[-1].append(raw)
    first: dict[tuple, str] = {}
    groups: dict[str, list[str]] = {}
    copies: set[str] = set()
    for block in blocks:
        card = parse("\n".join(block))[0]
        ex = _excerpt(block)
        if not card.get("id") or len(ex) < 40 or card.get("price") is None:
            continue
        key = (ex, card["price"], card.get("living_area"))
        if key in first:
            groups.setdefault(first[key], []).append(card["id"])
            copies.add(card["id"])
        else:
            first[key] = card["id"]
    if not copies:
        return text, {}, parse(text)
    out, _ = keep(text, lambda c: c.get("id") not in copies, limit)
    return out, groups, parse(out)


def keep(text: str, wanted, limit: int) -> tuple[str, list[dict]]:
    """The same reply with only the cards `wanted(card)` accepts, at most `limit`,
    renumbered; also returns the cards left out. Titles and descriptions are kept."""
    head, blocks = [], []
    for raw in text.splitlines():
        if _HEAD.match(raw.strip()):
            blocks.append([raw])
        elif blocks:
            blocks[-1].append(raw)
        else:
            head.append(raw)
    kept, dropped = [], []
    for block in blocks:
        card = parse("\n".join(block))[0]
        (kept if wanted(card) and len(kept) < limit else dropped).append((block, card))
    dropped = [c for _, c in dropped if not wanted(c)]
    out = "\n".join(head)
    out = re.sub(r"Showing \d+ propert(y|ies)", f"Showing {len(kept)} propert{'y' if len(kept) == 1 else 'ies'}", out)
    for n, (block, _) in enumerate(kept, 1):
        block = [_HEAD.sub(lambda m: f"**{n}. {m.group(2)}**", block[0].strip(), count=1)] + block[1:]
        out += "\n" + "\n".join(block)
    return out.rstrip() + "\n", dropped
