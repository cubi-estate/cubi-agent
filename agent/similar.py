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
        "id": p.get("id"), "city": p.get("city"), "country": p.get("country"),
        "price": p.get("price"), "eur_per_m2": p.get("eur_per_m2"), "living_area": p.get("living_area"),
        "bedrooms": p.get("bedrooms"), "bathrooms": p.get("bathrooms"),
        "features": {k: (p.get("features") or {}).get(k, "not_stated") for k in FEATURES},
        "environment": {k: (p.get("environment") or {}).get(k, {"state": "unknown"}) for k in ENVIRONMENT},
        "minutes": {k: (p.get("minutes") or {}).get(k) for k in MINUTES},
        "climate": {k: (p.get("climate") or {}).get(k) for k in CLIMATE},
    }


def table(result: dict, seed_card: int | None = None, match_cards: list[int] | None = None) -> dict:
    """What the page draws: the seed column, then one per match (numbered as its card)."""
    cols = [{**_column(result["seed"]), "role": "seed", "card": seed_card}]
    for i, m in enumerate(result.get("matches") or [], 1):
        n = match_cards[i - 1] if match_cards and i <= len(match_cards) else i
        cols.append({**_column(m), "role": "match", "card": n})
    return {"city": result.get("city"), "mode": result.get("mode") or "search", "columns": cols,
            "reason": result.get("reason"),
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


def place(p: dict, cross: bool) -> str:
    """"Gittana" — or "Gittana, Italy" when the homes compared are in different countries."""
    return f"{p.get('city')}, {p['country']}" if cross and p.get("country") else str(p.get("city"))


def cross_country(homes: list[dict]) -> bool:
    return len({h.get("country") or "" for h in homes}) > 1


def _home(label: str, p: dict, cross: bool = False) -> str:
    bits = [_price(p.get("price"))]
    if p.get("eur_per_m2"):
        bits.append(f"€{p['eur_per_m2']:,}/m²")
    if p.get("living_area"):
        bits.append(f"{p['living_area']:.0f} m²")
    if p.get("bedrooms") is not None:
        bits.append(f"{p['bedrooms']} bedrooms")
    return f"{label} ({place(p, cross)}): " + ", ".join(bits)


# Why a city had no match, from the connector's pool: {"candidates": 4, "dropped":
# {"bedrooms": 0, "area": 0, "undocumented": 4}}. The line used to read "in_city"
# (absent live, so "0 candidates") and always blame bedrooms and size, when Cubi
# had the homes but too little stated about them to compare (tester F2).
_DROPPED = {
    "bedrooms": "{n} with a different number of bedrooms",
    "area": "{n} with a living area more than 15% off",
    "undocumented": "{n} whose listings don't state enough features or environment readings to compare "
                    "(a gap in the data, not in the homes)",
}


MIN_AGREEMENT = 4  # the backend's bar; its reply states it under rules.min_agreement


def documented(p: dict) -> int:
    """Stated features plus environment readings with a known state."""
    feats = p.get("features") or {}
    env = p.get("environment") or {}
    return (sum(1 for v in feats.values() if v == "stated") if isinstance(feats, dict) else 0) + \
        (sum(1 for v in env.values() if isinstance(v, dict) and v.get("state") not in (None, "unknown"))
         if isinstance(env, dict) else 0)


def no_match_line(city: str | None, pool: dict) -> str:
    n = pool.get("candidates", pool.get("in_city"))
    dropped = pool.get("dropped") or {}
    reasons = [_DROPPED[k].format(n=v) for k, v in dropped.items() if k in _DROPPED and v]
    if n == 0:
        found = f"Cubi has no candidate homes of this type in {city}."
    elif n is None:
        found = f"No home in {city} met the rules."
    else:
        found = f"Cubi had {n} candidate home{'s' if n != 1 else ''} in {city}" + (
            ": " + "; ".join(reasons) + "." if reasons else ", none meeting the rules.")
    return (f"No matching home was found in {city}. {found} Say why in these terms, with no other "
            f"reason, and do not suggest a looser match.")


def tool_text(result: dict, cards: list[dict], seed_label: str, match_labels: list[str] | None = None) -> str:
    """What the loop model reads: the prices, the differences computed here, and the rules."""
    seed, city = result["seed"], result.get("city")
    matches = result.get("matches") or []
    cross = cross_country([seed, *matches])  # a pair across borders: name the countries too
    lines = [f"[find_similar_elsewhere {json.dumps({'listing_id': seed.get('id'), 'city': city}, ensure_ascii=False)}]",
             _home(f"This home, {seed_label}", seed, cross)]
    if not matches:
        need = (result.get("rules") or {}).get("min_agreement") or MIN_AGREEMENT
        known = documented(seed)
        if known < need:
            # The home asked about states too little: no city could match it. Blaming
            # the city's homes ("150 candidates, none with enough data") was wrong
            # (Lisbon card → Porto, 27 Oct: the seed stated 0 features, 1 reading).
            lines.append(f"No matching home was found in {city}: the listing of {seed_label} itself states "
                         f"{known} of the features and environment readings Cubi compares, and a match needs "
                         f"at least {need} in common, so no city could match it. Say that, with no other "
                         f"reason, and offer a price check on {seed_label} or homes like another card.")
            lines.append("Write one or two sentences.")
            return "\n".join(lines)
        lines.append(no_match_line(city, result.get("pool") or {}))
    for i, m in enumerate(matches, 1):
        label = match_labels[i - 1] if match_labels and i <= len(match_labels) else f"#{i}"
        lines.append(_home(f"{'Home' if match_labels else 'Match'} {label}", m, cross))
        diffs = differences(seed, m, f"the {place(seed, cross)} home ({seed_label})",
                            f"the {place(m, cross)} {'home' if match_labels else 'match'} ({label})")
        lines.append(f"  Differences (copy one or two of these sentences as written, translated if needed): "
                     + (" ".join(diffs) if diffs else "none recorded."))
    if not matches:
        lines.append("Write one or two sentences: that, with the reason, then offer another city.")
        return "\n".join(lines)
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
