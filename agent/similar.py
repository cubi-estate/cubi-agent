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


FEATURE_WORDS = {"air_conditioning": "air conditioning", "camp_site_nearby": "a campsite nearby"}
MINUTE_WORDS = {"walk_time.metro_station": "the metro on foot", "walk_time.railway_station": "a train station on foot",
                "walk_time.supermarket": "a supermarket on foot", "walk_time.school": "a school on foot",
                "walk_time.park": "a park on foot", "drive_time.coast": "the coast by car",
                "drive_time.airport": "the airport by car"}


ENV_SENTENCES = {  # axis: (said of a home where it holds, said where it doesn't)
    "quiet": ("is in a quiet spot (no loud road or rail noise)", "is near loud road or rail noise"),
    "clean_air": ("has clean air (PM2.5 at most 15)", "has PM2.5 above 15"),
    "leafy": ("has leafy surroundings", "has few trees around"),
    "coastal": ("is within 5 km of the coast", "is more than 5 km from the coast"),
    "flood_safe": ("is outside modelled river-flood zones", "is in a modelled river-flood zone"),
    "wildfire_safer": ("is in an area of lower wildfire weather", "is in an area of high wildfire weather"),
    "seismic_safer": ("is in an area of lower seismic hazard", "is in an area of higher seismic hazard"),
    "stable_ground": ("is on ground with no notable movement", "is in an area of notable ground movement"),
}


def differences(seed: dict, m: dict, seed_name: str = "this home", match_name: str = "the match") -> list[str]:
    """What tells the two homes apart, as finished sentences that name each home.
    Computed here so the model never infers a shared feature ("both include
    parking", when one listing stated it) and never has to map "this home / the
    match" back to cities (it swapped sunshine hours and wildfire weather)."""
    out = []
    for k in FEATURES:
        a, b = (seed.get("features") or {}).get(k), (m.get("features") or {}).get(k)
        word = FEATURE_WORDS.get(k, k)
        if a == "stated" and b != "stated":
            out.append(f"The listing for {seed_name} mentions {word}; the listing for {match_name} doesn't say.")
        elif b == "stated" and a != "stated":
            out.append(f"The listing for {match_name} mentions {word}; the listing for {seed_name} doesn't say.")
    for k in ENVIRONMENT:
        a = ((seed.get("environment") or {}).get(k) or {}).get("state", "unknown")
        b = ((m.get("environment") or {}).get(k) or {}).get("state", "unknown")
        if a != b and "unknown" not in (a, b):
            good, bad = ENV_SENTENCES[k]
            out.append(f"{seed_name} {good if a == 'yes' else bad}; {match_name} {good if b == 'yes' else bad}.")
    for k in MINUTES:
        a, b = (seed.get("minutes") or {}).get(k), (m.get("minutes") or {}).get(k)
        if a is not None and b is not None and abs(a - b) >= 5:
            out.append(f"From {seed_name} it is {a:.0f} minutes to {MINUTE_WORDS[k]}; from {match_name}, {b:.0f}.")
    a, b = (seed.get("climate") or {}).get("sunshine_hours"), (m.get("climate") or {}).get("sunshine_hours")
    if a and b and abs(a - b) >= 150:
        out.append(f"The region of {seed_name} gets about {a:,.0f} hours of sun a year; "
                   f"the region of {match_name}, about {b:,.0f}.")
    return out


def _home(label: str, p: dict) -> str:
    bits = [_price(p.get("price"))]
    if p.get("eur_per_m2"):
        bits.append(f"€{p['eur_per_m2']:,}/m²")
    if p.get("living_area"):
        bits.append(f"{p['living_area']:.0f} m²")
    if p.get("bedrooms") is not None:
        bits.append(f"{p['bedrooms']} bedrooms")
    return f"{label} ({p.get('city')}): " + ", ".join(bits)


def tool_text(result: dict, cards: list[dict], seed_label: str) -> str:
    """What the loop model reads: the prices, the differences computed here, and the rules."""
    seed, city = result["seed"], result.get("city")
    lines = [f"[find_similar_elsewhere {json.dumps({'listing_id': seed.get('id'), 'city': city}, ensure_ascii=False)}]",
             _home(f"This home, {seed_label}", seed)]
    matches = result.get("matches") or []
    if not matches:
        pool = result.get("pool") or {}
        lines.append(f"No documented match in {city}: {pool.get('in_city', 0)} candidates there, none with the same "
                     f"bedrooms and a living area within 15%. Say so; do not suggest a looser match.")
    for i, m in enumerate(matches, 1):
        lines.append(_home(f"Match #{i}", m))
        diffs = differences(seed, m, f"the {seed.get('city')} home ({seed_label})",
                            f"the {m.get('city')} match (#{i})")
        lines.append(f"  Differences (copy one or two of these sentences as written, translated if needed): "
                     + (" ".join(diffs) if diffs else "none recorded."))
    lines.append(
        "The app shows every row as a table, with the matches as numbered cards. Write two or three sentences: "
        "the asking prices side by side, then one or two of the Differences sentences, keeping which home "
        "each one is about exactly as written. "
        "Mention nothing else about the homes: do not say what they have in common, and do not add rooms, "
        "bathrooms or features that are not written above. Matches were chosen on the home, never on price. "
        "Call a price difference a difference in asking prices, never a saving, a bargain or a city premium. "
        "\"doesn't say\" and \"no reading\" are not a \"no\".")
    from .listings import render_cards
    return "\n".join(lines) + ("\n\n" + render_cards("Matches:", cards) if cards else "")
