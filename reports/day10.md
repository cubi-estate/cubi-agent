# Day 10 — deploy (2026-10-20)

Gate: the public URL works for an outside tester. **Met.**

- **Live:** https://port8080-mjzwgfk7vxespzx.tunnel.applications.eu-west2.nebius.cloud
  - Nebius Serverless AI endpoint in eu-west2 (Paris): 2 vCPU / 8 GB CPU, no GPU.
  - Image: `ghcr.io/cubi-estate/cubi-agent:<sha>`, public, built by GitHub
    Actions after the offline tests pass.
  - Secrets come from MysteryBox. Details are in `deploy/nebius.md`.
- **Cubi connector** (cleverdragon `75880fb8`, Heroku v2962):
  - Named deployment tokens (`MCP_DEPLOY_TOKENS`). The demo calls as
    `deploy:cubi-agent-demo`, with its own budget of 5,000 units a day and
    a limit of 120 calls a minute. It is never operator and is refused at
    `/mcp/ops`. All of this was checked live.
  - Calls from the open-source agent are no longer logged as Cubi's own
    operator traffic.
- **Live checks:**
  - health reports `forwarded: true`, and the page returns 200;
  - Lisbon search: 3.3s, 6 cards;
  - München search: 7.9s, 6 cards.
  - The first-ever Lisbon call hit a cold cache on Cubi's side
    (`search_incomplete`). It fell back to free-text search and still
    answered, in 34s.

## Incidents

- `scripts/config_set.py` printed the new deployment token in its output (the
  dry run doesn't show the value). It was rotated within minutes with the
  output redacted; the leaked value returns 401.
- eu-north1 has a CPU quota of 0 for this tenant, so the demo runs in eu-west2.

## Open

- A stable link for Devpost (proposed: `www.cubi.estate/agent` → the endpoint
  URL), because an image change means a new endpoint and a new URL.
- Warm the Cubi read set before judging, or have the agent retry
  `filter_listings` once before falling back.
- Monitor uptime until Dec 15. Billing runs from create to delete.
