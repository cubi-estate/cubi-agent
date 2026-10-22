"""Homes like one listing, in another city: the connector's `find_similar_elsewhere`.

Cubi returns the listing and up to two matches in the other city, profiled on
the same rows: asking price, €/m², stated features, environment readings,
walk/drive minutes and regional climate. The page draws them as one table from
that result; the model only writes a few sentences around it.

The connector matched them on the home, never on price, so a price difference
is a finding. It is still a difference between asking prices, not a saving.
A feature "not stated" means the listing doesn't say; a reading "unknown"
means there is none. Neither is a "no".
"""
from __future__ import annotations

import json

from .inventory import card

TOOL = "find_similar_elsewhere"

FEATURES = ["balcony", "terrace", "lift", "parking", "air_conditioning", "garden", "pool", "camp_site_nearby"]
ENVIRONMENT = ["quiet", "clean_air", "leafy", "coastal", "flood_safe", "wildfire_safer", "seismic_safer",
               "stable_ground"]
MINUTES = ["walk_time.metro_station", "walk_time.railway_station", "walk_time.supermarket", "walk_time.school",
           "walk_time.park", "drive_time.coast", "drive_time.airport"]
CLIMATE = ["sunshine_hours", "sea_temp_summer_c", "summer_max_c", "winter_min_c"]


def _column(p: dict) -> dict:
    """One home as a table column: only the fields the page draws."""
    return {
        "id": p.get("id"), "city": p.get("city"),
        "price": p.get("price"), "eur_per_m2": p.get("eur_per_m2"), "living_area": p.get("living_area"),
        "bedrooms": p.get("bedrooms"), "bathrooms": p.get("bathrooms"),
        "features": {k: (p.get("features") or {}).get(k, "not_stated") for k in FEATURES},
        "environment": {k: (p.get("environment") or {}).get(k, {"state": "unknown"}) for k in ENVIRONMENT},
        "minutes": {k: (p.get("minutes") or {}).get(k) for k in MINUTES},
        "climate": {k: (p.get("climate") or {}).get(k) for k in CLIMATE},
    }


def table(result: dict, seed_card: int | None = None) -> dict:
    """What the page draws: the seed column, then one per match (numbered as its card)."""
    cols = [{**_column(result["seed"]), "role": "seed", "card": seed_card}]
    for i, m in enumerate(result.get("matches") or [], 1):
        cols.append({**_column(m), "role": "match", "card": i})
    return {"city": result.get("city"), "columns": cols, "reason": result.get("reason"),
            "rules": result.get("rules"), "pool": result.get("pool")}


def to_cards(result: dict) -> list[dict]:
    return [card(m.get("card") or {"id": m.get("id")}, i) for i, m in enumerate(result.get("matches") or [], 1)]


def _price(v) -> str:
    return "price on request" if not v else f"€{v:,.0f}"


def tool_text(result: dict, cards: list[dict], seed_label: str) -> str:
    """What the loop model reads: the figures that matter, and how to relay them."""
    seed, city = result["seed"], result.get("city")
    lines = [f"[find_similar_elsewhere {json.dumps({'listing_id': seed.get('id'), 'city': city}, ensure_ascii=False)}]",
             f"This home ({seed_label}, {seed.get('city')}): {_price(seed.get('price'))}"
             + (f", €{seed['eur_per_m2']:,}/m²" if seed.get("eur_per_m2") else "")
             + (f", {seed['living_area']:.0f} m²" if seed.get("living_area") else "")]
    matches = result.get("matches") or []
    if not matches:
        pool = result.get("pool") or {}
        lines.append(f"No documented match in {city}: {pool.get('in_city', 0)} candidates there, none with the same "
                     f"bedrooms and a living area within 15%. Say so; do not suggest a looser match.")
    for i, m in enumerate(matches, 1):
        stated = [k for k, v in (m.get("features") or {}).items() if v == "stated"]
        lines.append(f"Match #{i} ({m.get('city')}): {_price(m.get('price'))}"
                     + (f", €{m['eur_per_m2']:,}/m²" if m.get("eur_per_m2") else "")
                     + (f", {m['living_area']:.0f} m²" if m.get("living_area") else "")
                     + (f"; listing states: {', '.join(stated)}" if stated else ""))
    env_diffs = []
    for k in ENVIRONMENT:
        states = [((p.get("environment") or {}).get(k) or {}).get("state", "unknown") for p in [seed, *matches]]
        if len({s for s in states if s != "unknown"}) > 1:
            env_diffs.append(f"{k}: " + " / ".join(states))
    if env_diffs:
        lines.append("Environment readings that differ (this home / matches): " + "; ".join(env_diffs))
    lines.append(
        "The app shows everything above as a table, with the matches as numbered cards. Write two or three "
        "sentences: the asking prices side by side and one or two differences that matter. Matches were "
        "chosen on the home, never on price. Call a price difference a difference in asking prices, never a "
        "saving, a bargain or a city premium. 'not stated' means the listing doesn't say; 'unknown' means "
        "there is no reading: neither is a 'no'.")
    from .listings import render_cards
    return "\n".join(lines) + ("\n\n" + render_cards("Matches:", cards) if cards else "")
