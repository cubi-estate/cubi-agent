# cubi-agent

**Cross-border home search on open models.** Ask in English, Portuguese, Spanish,
French, German or Dutch for homes anywhere in Europe. Then ask about one of them: is
its price in line with similar homes, how do I contact the agent, what are the schools
and transport like there? An agent on **NVIDIA Nemotron**, served by **Nebius Token
Factory**, answers from **2.3M+ active listings in 20 European countries** through
[Cubi Estate](https://www.cubi.estate)'s public, read-only connector, with cited web
sources from **Tavily** for area questions.

**Live demo: https://www.cubi.estate/agent** — no account needed, free until the end of judging (Dec 15, 2026).

Built for the Nebius × NVIDIA Global AI Hackathon, Best Apps and Agents track.

---

## What it does

| You ask | The agent | Shown to you |
|---|---|---|
| "Wohnung in Porto bis 400.000 Euro, mindestens 2 Schlafzimmer" | Nemotron turns the request into a structured filter; code checks it, then calls Cubi's `filter_listings` | numbered listing cards, each linking to the original listing |
| "Is #2 overpriced?" | resolves "#2" to that card in code; calls `compare_asking_prices` | where the asking price sits against similar homes nearby, with "not a valuation" stated |
| "How do I contact the agent?" | calls `get_contact_options` | Cubi's consented contact routes and a sign-in link. Nothing is sent for you |
| "Compare schools and public transport in Porto and Valencia" | calls Tavily once per place and topic | a side-by-side answer, each point linked to its source |
| "What does 400k buy in Lisbon vs Porto? 2-bed flats", then "And up to 500k?" | calls Cubi's `compare_inventory`: per city, the share of its priced listings of that kind within the budget | one bar per city drawn from Cubi's counts (a budget change keeps the cities and marks the earlier share), with example homes from the counted set. Shares, not counts: a count shows Cubi's coverage, not the market |
| "Show me homes like #2 in Porto" | resolves "#2" in code; calls Cubi's `find_similar_elsewhere`, which matches on the home (same bedrooms, area within 15%, stated features and surroundings), never on price | one table: the home beside up to two matches — asking price, €/m², features as each listing states them, environment readings (quiet, clean air, leafy, coast, flood, wildfire, seismic, ground motion), walking and driving minutes, regional climate. "Not stated" and "no reading" are shown as such, never as "no" |

While it works, the page shows a short **action log** ("Understood: for sale ·
apartment · 2+ bed · ≤ €400,000 · in Porto" → "Searching listings"). It never shows
model reasoning.

## How it works

```
 browser ──NDJSON──▶ agent/server.py ──▶ agent/loop.py
                                           │
            ┌──────────────────────────────┼──────────────────────────────┐
            ▼                              ▼                              ▼
  Nebius Token Factory            Cubi Estate MCP connector            Tavily search
  nvidia/nemotron-3-super-120b    filter_listings · search_properties  (area questions:
  (tool loop, filter extraction,  get_listing · compare_asking_prices   place + topic only)
   short summaries)               get_contact_options
```

- **One open model does the language work.** `nvidia/nemotron-3-super-120b-a12b`,
  called at runtime through Token Factory's OpenAI-compatible API, runs the tool loop,
  extracts the search filter (JSON schema, strict) and writes the summaries. Thinking
  is off for these calls (`chat_template_kwargs.enable_thinking=false`).
- **Shared skills.** The system prompts are the `SKILL.md` files of the
  [Cubi Estate plugin for Claude](https://github.com/cubi-estate/cubi-estate-plugin),
  vendored as a pinned submodule. The same instructions drive Claude through the plugin
  and Nemotron here. A rule in code picks one skill per turn, and each skill sees only
  its own tools.
- **Code decides what the model shouldn't:**
  - language detection;
  - sale vs rent;
  - feature names;
  - which home "the second one" means;
  - whether a request needs the structured filter or Cubi's free-text search.

  The normaliser rules each fix an error the eval found to be systematic, not random
  (`agent/normalize.py`).
- **Homes are rendered from tool output, not written by the model.** Cards are parsed
  from the connector's reply (`agent/listings.py`), so the model can't invent one. It
  writes two or three sentences and may refer to "#2".
- **Deterministic guards** run on every answer (`agent/guards.py`):
  - every URL must appear verbatim in the tool output, and a list item with an unknown
    link is dropped whole;
  - phone numbers and emails are scrubbed;
  - "a good deal / overpriced" verdicts are removed after a price comparison, and the
    "not a valuation" line is added;
  - any claim of having sent or contacted something is removed;
  - Tavily citations `[S3]` are turned into links in code, and unknown ones are dropped.

## Results

All numbers are from `evals/` and `reports/`. They are reproducible with the scripts there.

**Filter extraction, held-out set** (36 new requests, 6 per language; rules frozen before the run; `reports/eval_20261020T151605Z.md`):

| model (Token Factory) | fields right | all fields right | route | p50 |
|---|---|---|---|---|
| Nemotron 3 Nano 30B-A3B | 146/148 | 34/36 | 36/36 | 0.79s |
| Nemotron 3.5 Lightning | 148/148 | 36/36 | 36/36 | 0.54s |
| **Nemotron 3 Super 120B-A12B** (used) | 148/148 | 36/36 | 36/36 | 1.05s |
| Nemotron 3 Ultra 550B-A55B | 148/148 | 36/36 | 36/36 | 0.79s |

Nano repeatedly reads "750€" as 75,000 in Portuguese, so it isn't used for
extraction. One caveat: the same person wrote the rules and this set, so treat these
numbers as an upper bound.

**Agent path vs sending the request straight to Cubi's own free-text search** (31 held-out requests; `reports/compare_20261020T153024Z.md`):

| | agent (Nemotron → `filter_listings`) | direct (`search_properties`) |
|---|---|---|
| listings meeting every visible constraint | 142/158 (90%) | 137/146 (94%) |
| no results | 2 | 4 |
| latency p50 | **1.35s** | 5.97s |
| connector quota units | **33** | 310 |

The agent's results are about as precise, it is 4× faster, and it uses a tenth of the
quota. Most of its misplaced results came from listings with a wrong region in Cubi's
data, which has been reported upstream.

**Answers** (31 first turns; `reports/audit_20261020T153931Z.md`): 0 needed a guard
fix once cards came from code. Before that, one live German turn invented three
listings with plausible ids. That's why cards are now built from tool output.

## Run it

```bash
git clone --recurse-submodules https://github.com/cubi-estate/cubi-agent
cd cubi-agent
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # NEBIUS_API_KEY required; TAVILY_API_KEY for area questions

.venv/bin/python cli.py                                   # chat in the terminal (--timings for per-stage seconds)
.venv/bin/uvicorn agent.server:app --port 8080            # web app → http://localhost:8080
.venv/bin/python -m pytest -q                             # offline tests (no keys, no network)
```

The connector needs no account. Anonymous use is rate-limited per IP; a hosted
deployment can use a deployment token (`CUBI_MCP_TOKEN`) with its own budget.

**Offline mode.** `CUBI_OFFLINE=1` replays recorded connector replies from
`fixtures/mcp/`, so results stay reproducible if the live service is down. The
fixtures are cut down to facts (type, place, size, price, URL, id, a few tags): no
listing titles, descriptions or street addresses. Token Factory is still called.

**Evals:**

```bash
.venv/bin/python evals/run_eval.py --cases evals/filter_extraction_heldout.jsonl   # model comparison
.venv/bin/python evals/compare_search.py          # agent path vs free-text search (~11 quota units/case)
CUBI_OFFLINE=1 .venv/bin/python evals/answer_audit.py   # what the guards had to fix, and where the time goes
```

**Deploy.** `Dockerfile` + `.github/workflows/image.yml` (tests, then
`ghcr.io/cubi-estate/cubi-agent`). The demo runs on a Nebius Serverless AI endpoint
(CPU only; the models are on Token Factory). See `deploy/nebius.md`.

## Data and privacy

What leaves your browser, and where it goes:

| Recipient | What | Where | Why |
|---|---|---|---|
| **This demo's server** (Nebius AI Cloud, Paris) | your messages | EU | runs the agent. The conversation is kept in memory for 30 minutes after your last message, then dropped. No chat text is written to disk or to logs; the log has counters only (turns, seconds, which skill). |
| **Nebius Token Factory** | your messages and the listing data the agent works with | Nemotron 3 Super is served from **us-central1 (US)** | model inference |
| **Cubi Estate connector** (`mcp.cubi.estate`, EU) | the search filter or search text, listing ids | EU | listing search. Cubi logs each tool call to run and secure the service: free-text queries and network addresses are removed after 7 days, the record after 14. See the [Cubi Estate privacy policy](https://www.cubi.estate/privacy-policy). Its free-text search uses OpenAI on Cubi's side. |
| **Tavily** | for area questions only: place names and topics, e.g. "Porto, Portugal: schools for residents" | US | web search. No listing data and none of your other words. |

This means the demo is **not EU-only**: model inference runs in the US. Don't enter
personal details. To contact an agent, the demo gives you a link to Cubi's own chat
and sends nothing itself. Listing data comes from public portals and agencies; each
card links to the original. Asking prices are the sellers', not valuations.

The live listing service is an external dependency, not part of this repository.
What is open here is the agent, the web app, the evals, the skill pack and the
connector's public tool schemas (`fixtures/mcp_tools.json`).

## Repository

```
agent/       loop, extraction + normaliser, guards, listing cards, Tavily tool, MCP client, web server
web/         the page (no build step, no external scripts)
skills/      skills this app adds (compare-areas, compare-budget, similar-elsewhere); the rest come from vendor/cubi-estate-plugin
evals/       eval sets and runners;   reports/ their results
fixtures/    connector tool schemas + facts-only recorded replies for offline mode
deploy/      Nebius runbook;   Dockerfile, .github/workflows/image.yml
tests/       offline tests
docs/        FEEDBACK.md — what we learned building on Token Factory and Nebius
```

## License

Apache-2.0. The vendored skill pack is MIT-licensed (see its own LICENSE). Listing
data is served by Cubi Estate under its terms and is not part of this repository.
