# Hosting the demo on Nebius Serverless AI endpoints

The web app (`agent/server.py`) runs as one CPU container behind a Nebius
managed HTTPS URL. No GPU: the models run on Token Factory, so the container
only serves the page and orchestrates calls.

## One-time, by the account owner

```bash
curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash   # Nebius CLI
nebius profile create --parent-id <project-id>                   # opens a browser
nebius compute platform list --parent-id <project-id> --format json   # CPU platforms + presets
```

The image is `ghcr.io/cubi-estate/cubi-agent:<sha>`, built by
`.github/workflows/image.yml` on every push to `main`. Make the GHCR
package public, or pass `--registry-secret`.

## Secrets

The container reads `NEBIUS_API_KEY` (required), `TAVILY_API_KEY` (area
comparison) and `CUBI_MCP_TOKEN` (the demo's deployment token on Cubi's
connector, `cubi-agent-demo`). Keep them in MysteryBox rather than as plain
`--env` values: plain values are readable by anyone with read access to the
endpoint spec.

## Create

```bash
nebius ai endpoint create \
  --name cubi-agent-demo \
  --image ghcr.io/cubi-estate/cubi-agent:<sha> \
  --platform <cpu platform> --preset <smallest preset> \
  --container-port 8080 \
  --auth none \
  --env TRUST_PROXY=1 --env DEMO_TURNS_PER_DAY=1500 \
  ...secrets...
```

`--auth none` is deliberate: judges open the page in a browser. Abuse is
bounded by the app's own limits (per-IP turns per minute and per day, a daily
turn budget for the whole demo) and by the connector token's own quota.

Then check that the proxy passes the client address:

```bash
curl -s "$ENDPOINT_URL/api/health"    # want "forwarded": true
```

## Updating

An endpoint's image can't be changed in place: create a new endpoint, smoke
test it, then delete the old one. Its URL changes, so the URL given to judges
is a stable redirect (`https://www.cubi.estate/agent` → the current endpoint),
not the endpoint URL itself.

## Cost

Billed from create to delete, idle included. Stop the endpoint (`nebius ai
endpoint stop`) when it isn't needed. Judging runs until Dec 15.
