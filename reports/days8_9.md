# Days 8–9 — web UI (2026-10-20)

`agent/server.py` (FastAPI) + `web/` (one page, no build step, no external scripts).

## What's there

- **Streaming turn**: `POST /api/chat` streams NDJSON events: session, then each
  action as it happens, then the answer. The page shows the action log live,
  then folds it to "2 steps · 3.1s".
- **Cards** come from the connector output. Each shows price, type, place
  (no street), bedrooms, bathrooms and area, up to 3 tags (the ones matching
  the request first, duplicates removed), and the date it was last updated.
  Buttons: **Open listing** (the original via cubi.estate/r/…) and **Ask
  Cubi**. No photos, because the rights aren't clear.
- **Kept filters**: a localized line above the cards, e.g. "Suche: Kauf ·
  Wohnung · 2+ Schlafz. · ≤ €400,000 · in Porto".
- **Follow-up chips** in the answer's language: "Liegt der Preis von #1 im
  Rahmen ähnlicher Objekte?" and "Wie erreiche ich den Makler von #1?".
- **States**:
  - empty: example queries in 5 languages;
  - working: spinner plus live steps;
  - no results: the model suggests a change;
  - errors: rate limit, daily demo budget, message too long, model or connector
    down, shown as a plain amber note.
- **Markdown** is escaped first, then only bold, italics, http(s) links, lists
  and headings are rendered.
- **Privacy**: sessions live in process memory for 30 minutes with an LRU cap
  of 300. The log records counters only, and a test asserts no message text
  reaches it. A footer notice names Nebius Token Factory, Cubi's connector and
  Tavily (US).
- **Limits** (environment variables): 8 turns a minute and 120 a day per IP;
  1,500 turns a day for the whole demo; 30 turns per conversation;
  500-character messages. Set `TRUST_PROXY=1` behind a proxy.
- Light and dark themes; mobile-first. Checked at 390px wide with no
  horizontal scroll.

## Fix found while testing in the browser

Repeating a search word for word made Nemotron answer from history
**without calling the tool**, so a summary appeared with no cards. A
find-homes turn that doesn't point at a card now runs `search_homes` in
code. The model then only writes the summary, and may still call
`get_listing`. This also removes one Token Factory round trip: an offline
first turn now takes 3.1s, down from a 4.8s p50.

## Browser run (offline fixtures, German/French/English)

| turn | result |
|---|---|
| Wohnung in Porto bis 400.000 Euro, mindestens 2 Schlafzimmer | 6 cards, filter line in German, 3.1s |
| Liegt der Preis von #2 im Rahmen ähnlicher Objekte? | card #2 resolved; below the range of 20 comparables; not-a-valuation line, 6.1s |
| Wie erreiche ich den Makler von #2? | three Cubi contact routes + sign-in link, 2.1s |
| Studio à louer à Bordeaux, 700 € par mois maximum | no results; suggests a higher budget or nearby areas, 3.4s |
| Compare schools and public transport in Porto and Valencia | 13 source links, 3.8s |

Tests: 57 (6 new server tests).

## Open

- The action log is English in every language.
- The contact answer shows Cubi's link as the bare host name.
- Deploy (day 10): host, `TRUST_PROXY`, the scoped connector credential so
  judges don't share the anonymous 500-unit quota, and Token Factory and
  Tavily spend caps.
