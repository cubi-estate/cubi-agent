# Days 6–7 — price check, contact, area comparison (2026-10-20)

Gate: the full demo flow runs in the CLI. **Met** for search → price → contact,
live and offline. The area comparison is built and tested, but it hasn't run
against Tavily yet because `TAVILY_API_KEY` isn't set.

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

## Needed from the owner

- A **Tavily API key** in `.env` / the demo host (`TAVILY_API_KEY`). The
  hackathon's Tavily prize is the reason to include it. With the key:
  `CUBI_RECORD=1 python cli.py "Compare schools and public transport in Porto and Valencia"`.
