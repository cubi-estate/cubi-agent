"""What a budget buys in 2-3 cities: the connector's `compare_inventory`.

Cubi counts, per city, the priced listings of one cohort (e.g. 2-bed flats for
sale) and the part within the price cap. Every number on screen comes from
that call; the model only writes a short summary around the bars.

Shares, not counts: a count says how many listings Cubi holds for a city, not
how big its market is. Parking is never compared: whether a listing records
parking depends on the agency that published it (75-97% for some Portuguese
agencies, 5-20% for Spanish portals), so a parking bar would compare sources.
"""
from __future__ import annotations

import json

from .schema import SearchFilter

TOOL = "compare_inventory"
MAX_PLACES = 3
SAMPLE_PER_PLACE = 3

PARKING_NOTE = ("[The user asked about parking. It was NOT compared: whether a listing records parking "
                "depends on the agency that published it, so the shares would compare sources, not cities. "
                "Say so in one sentence.]")


def args_for(f: SearchFilter, places: list[str]) -> dict:
    """compare_inventory arguments from the extracted filter. Sale only, no parking."""
    args: dict = {"places": places[:MAX_PLACES], "transaction_type": "sale", "max_price": f.max_price,
                  "lang": f.lang}
    if f.type:
        args["type"] = list(f.type)
    if f.min_bedrooms is not None:
        args["min_bedrooms"] = f.min_bedrooms
    if f.max_bedrooms is not None:
        args["max_bedrooms"] = f.max_bedrooms
    return args


def cohort_key(args: dict) -> tuple:
    """Everything but the budget: two results with the same key differ only in price cap."""
    return (tuple(p.lower() for p in args["places"]), tuple(args.get("type") or ()),
            args.get("min_bedrooms"), args.get("max_bedrooms"))


def _price_text(price) -> str:
    return f"{int(price):,}".replace(",", " ") + " EUR"


def to_cards(result: dict) -> list[dict]:
    """The sample listings as the app's numbered cards (same shape as listings.parse)."""
    cards: list[dict] = []
    for place in result.get("places") or []:
        for c in place.get("listings") or []:
            if not c.get("price"):
                continue  # "price on request" passes a cap but can't illustrate a budget
            card = {"n": len(cards) + 1, "id": c.get("id"), "type": c.get("object_type") or "Home",
                    "location": ", ".join(x for x in (c.get("city"), c.get("region"), c.get("country")) if x),
                    "price": c.get("price"), "price_text": _price_text(c.get("price")),
                    "url": c.get("url"), "ask_url": c.get("ask_cubi_url"),
                    "updated": str(c.get("updated_at") or "")[:10] or None}
            for key in ("bedrooms", "bathrooms", "living_area"):
                if c.get(key) is not None:
                    card[key] = float(c[key])
            cards.append({k: v for k, v in card.items() if v is not None})
    return cards


def bars(result: dict, previous: dict | None = None) -> dict:
    """What the page draws: one bar per city, the earlier budget as a marker."""
    prev = {p["place"].lower(): p for p in (previous or {}).get("places") or []}
    rows = []
    for p in result.get("places") or []:
        base, within = p.get("base") or {}, p.get("within_budget") or {}
        row = {"place": p["place"], "level": p.get("level"), "share_pct": within.get("share_pct"),
               "within": within.get("priced"), "of": base.get("priced"),
               "error": base.get("error") or within.get("error")}
        before = (prev.get(p["place"].lower()) or {}).get("within_budget") or {}
        if before.get("share_pct") is not None:
            row["previous_pct"] = before["share_pct"]
        rows.append(row)
    out = {"max_price": (result.get("filters") or {}).get("max_price"), "rows": rows,
           "as_of": result.get("as_of")}
    if previous:
        out["previous_max_price"] = (previous.get("filters") or {}).get("max_price")
    return out


def tool_text(result: dict, previous: dict | None, cards: list[dict]) -> str:
    """What the loop model reads: the figures, and the rules for relaying them."""
    cap = (result.get("filters") or {}).get("max_price")
    prev_cap = ((previous or {}).get("filters") or {}).get("max_price")
    view = bars(result, previous)
    lines = [f"[compare_inventory {json.dumps(result.get('filters'), ensure_ascii=False)}]",
             f"Share of each city's priced listings of this kind with an asking price up to €{cap:,.0f}:"]
    for r in view["rows"]:
        if r.get("error") or r.get("share_pct") is None:
            lines.append(f"- {r['place']}: could not be counted right now")
            continue
        line = f"- {r['place']} ({r['level']}): {r['share_pct']}% ({r['within']} of {r['of']} listings)"
        if r.get("previous_pct") is not None and prev_cap:
            line += f"; at €{prev_cap:,.0f} it was {r['previous_pct']}%"
        lines.append(line)
    lines.append(
        "Relay these shares; the app draws them as bars. Counts show how many listings Cubi holds per "
        "city, not how big each market is, so never compare the counts. These are asking prices of "
        "active listings, not sale prices. Do not state any other figure, and do not pick a winner. "
        f"Under the bars the app shows {len(cards)} example homes, numbered by city.")
    from .listings import render_cards
    return "\n".join(lines) + "\n\n" + render_cards("Example homes:", cards)
