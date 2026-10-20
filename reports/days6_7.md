# Days 6–7 — price check, contact, area comparison (2026-10-20)

Gate: the full demo flow runs in the CLI. **Met**: search → price → contact
runs live and offline, and the area comparison runs live on Tavily (added the
same day, once the key was set; see the last section).

## Live run (German, `CUBI_RECORD=1`)

| turn | skill | what happened | latency |
|---|---|---|---|
| Wohnung in Porto bis 400.000 Euro, mindestens 2 Schlafzimmer | find-homes | `filter_listings`, 6 cards rendered from tool output | 10.3s (connector 4.6s) |
| Ist die zweite zu teuer? | check-asking-price | "die zweite" → card #2 → `iad_pt:981792`, resolved in code; below the 25–75% range from 20 comparables; not-a-valuation wording; no verdict | 5.5s |
| Wie kann ich den Makler kontaktieren? | contact-agent | same home; Cubi's three contact routes, suggested questions, sign-in link, "nothing sent until you confirm" | 6.9s |
| Vergleiche Schulen und Nahverkehr in Porto und Valencia | compare-areas | `research_area` → "not configured" → the model says research is unavailable and doesn't answer from memory | 1.4s |

The three connector replies are recorded in `fixtures/mcp/`. The flow replays
with `CUBI_OFFLINE=1` (2.6s / 4.2s / 2.5s).

## What was built

- **Card references in code** (`agent/ordinals.py`, `Agent._resolve_listing`).
  "#2", "the second one", "a segunda", "la deuxième", "die zweite", "de
  laatste" all map to the card number on screen. The card the user named wins
  over whatever id the model passed. After that come an id already shown in
  this conversation, then the home discussed last, then the only card on
  screen. Otherwise the tool returns "ask which card"; an id is never guessed.
  The cards on screen are also listed in the system prompt.
- **Price-verdict guard.** After `compare_asking_prices`, any sentence calling
  the home a good deal, a bargain, overpriced and so on (in 6 languages) is
  removed, and one line suggests an independent valuation. Questions quoting
  the user are kept, and so is the layout.
- **"Sent" guard.** After `get_contact_options`, any first-person claim of
  having sent, contacted or booked something is removed, and the answer says
  nothing has been sent.
- **Area research** (`agent/tavily_tool.py`, `skills/compare-areas/SKILL.md`).
  This is a local skill, since the plugin pack has no web tool. It does one
  Tavily basic search per place (at most 3), and the model gets each source's
  title, URL, date and a 300-character excerpt. The skill requires a citation
  for every point and "no source covered it" for gaps, and it doesn't pick a
  winner. The URL guard drops uncited links. Only place names and topics go
  to Tavily, never listing data. Tavily replies are recorded to
  `fixtures/tavily/`, which is git-ignored because the excerpts are
  third-party text.
- **Skill rule.** An area question goes to compare-areas unless it is
  clearly a home search ("2-bed flat near a metro in Lisbon").
- Fixtures accept a listing URL or a bare id, and keep Cubi-authored replies
  (price comparison, contact options) whole.

Tests: 51 offline tests pass.

## Defects seen

- **Language slip:** the German contact answer contained one Spanish word
  ("Um cualquiera dieser Optionen") and switched from *Sie* to *du*. There is
  no guard for this yet. A candidate is a per-sentence language check, or
  answering in a fixed register.
- **"Porto" means Porto district** for the connector (Felgueiras, Amarante).
  Either the demo uses a city-only place, or the agent says "Porto district".
- **iad_pt city/region bug** (1,470 of 8,577 active rows) handed to the
  cleverdragon side (europe-corpus-machine).
- Input tokens grow with history: about 23k cumulative by turn 4. Fine for
  the demo; trim tool results in history if longer chats matter.

## Area comparison, live on Tavily

First run: one combined search per place. Three problems:

1. Nemotron cited with its internal markup (`【{"id":0,"cursor":0,…}】`), not links.
2. "Valencia" brought Valencia College in Florida; most hits were Facebook/Instagram.
3. The German question was answered in English; one combined query per place found nothing on schools.

Fixes:

- One search per place × topic (at most 3 × 3), run in parallel: 4 searches in about 2s, down from 7.7s sequentially.
- Places carry their country.
- Social-media domains are excluded.
- Hits that don't name the place are dropped.
- Query shape `"<place>: <topic> for residents"`. The shape "public transport in Valencia, Spain" returned public.io, the NYT and FEMA.
- The model gets numbered sources `[S1]…` without URLs. Code turns `[S3]` into a link, removes unknown numbers and internal markup, and always adds a **Sources** list. If the model cited nothing, the list says so ("not cited one by one").
- The tool output ends with the answer language spelled out.

| run | language | citations | turn |
|---|---|---|---|
| Compare schools and public transport in Porto and Valencia | en | 12 linked, all correct cities | 6.7s |
| Compara a saúde e as praias em Cascais e Alicante | pt | 10 linked | 8.7s |

Tavily credits: 1 per search, so 4 for a two-place, two-topic comparison.
Recordings are in `fixtures/tavily/` (git-ignored). Still to watch: Tavily
gives no dates for general pages, so answers say "undated", and many sources
are relocation and real-estate marketing sites.
