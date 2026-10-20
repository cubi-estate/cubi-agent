# cubi-agent

Cross-border home search on open models: an agent that runs on **NVIDIA Nemotron via
Nebius Token Factory** and searches 2.2M+ European homes for sale and rent through
[Cubi Estate](https://www.cubi.estate)'s public, read-only connector.

> Work in progress for the Nebius × NVIDIA Global AI Hackathon (Best Apps and Agents).

## How it works (so far)

- `agent/mcp_client.py` — a small client for Cubi's MCP connector (`https://mcp.cubi.estate/mcp`).
  No account needed; anonymous use is rate-limited.
- `agent/schema.py` — the search filter Nemotron extracts from a request in any of six
  languages, mapped onto the connector's `filter_listings` tool. The open model does the
  language understanding; the connector runs no language model on this path.
- `agent/llm.py` — OpenAI-compatible client pointed at Token Factory.
- `vendor/cubi-estate-plugin` — the same skill pack used by the
  [Cubi Estate plugin for Claude](https://github.com/cubi-estate/cubi-estate-plugin), pinned.

## Setup

```bash
git clone --recurse-submodules https://github.com/cubi-estate/cubi-agent
cd cubi-agent
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # add NEBIUS_API_KEY (and TAVILY_API_KEY later)

.venv/bin/python scripts/mcp_smoke.py           # connector only, no key needed
.venv/bin/python scripts/day1_probe.py          # Nemotron capability probe → reports/
.venv/bin/python -m pytest -q                   # offline tests
```

## Run it

```bash
.venv/bin/python cli.py                                            # chat in the terminal
.venv/bin/uvicorn agent.server:app --port 8080                     # web app → http://localhost:8080
CUBI_OFFLINE=1 .venv/bin/uvicorn agent.server:app --port 8080      # same, replaying fixtures/ (no connector calls)
```

The web app streams each turn as NDJSON from `POST /api/chat`. It shows what the
agent does as a short action log, never model reasoning. Homes appear as cards
built from the connector's output, linking to the original listing. Limits for a
public deployment are environment variables in `agent/server.py`: per-IP turns per
minute and per day, and a daily turn budget for the whole demo.

## Data and privacy

Requests go to Nebius Token Factory (model inference; some Nemotron models are served
from the US region) and to Cubi Estate's connector, which logs tool calls as described in
the [Cubi Estate privacy policy](https://www.cubi.estate/privacy-policy). Area questions
send place names and topics, never listing data, to Tavily (US). The web app keeps a
conversation in memory for 30 minutes after the last message. It writes no chat text
to disk or logs; the log records counters only.

## License

Apache-2.0. The vendored skill pack is MIT-licensed (see its own LICENSE).
