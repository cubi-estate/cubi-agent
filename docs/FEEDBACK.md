# Feedback: building an agent on Nebius Token Factory, Nemotron and Nebius AI Cloud

What we hit while building cubi-agent between Oct 13 and Oct 20, 2026. Each item says
what happened, how we worked around it, and what would have helped. The evidence is
in `reports/` and the git history.

## Nemotron on Token Factory

**1. Reasoning leaks into `json_schema` strict output unless thinking is switched off.**
Nemotron 3 models reason by default. On our first probe (`reports/day1_20261013T155549Z.md`):
- Nano spent its token budget thinking and returned nothing parseable for 2 of 6 requests.
- Super returned schema-valid JSON whose `location` field contained reasoning text:
  `["/**/??? Actually I'd better just give simple flat structure.** Let's decide on plausible keys:** - ", "cities", …]`.

With `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`, every
model produced 6/6 valid extractions, and latency fell from 3–9s to about 1s
(`reports/day1_20261013T155826Z.md`).
- *Would help:* when `response_format` is `json_schema` with `strict: true`, default
  thinking off, or keep reasoning out of the constrained output. At minimum, the model
  card and the Token Factory structured-output docs should say this up front. "Strict
  schema" reads as a guarantee about field contents, and here it was only about shape.

**2. Internal citation markup reaches the answer.** Given web sources to cite, Super
wrote `【{"id":0,"cursor":0,"loc":0}】` in place of links, in two of two runs. We
now give the model numbered sources (`[S1]`) without URLs, strip `【…】` in code,
and link the numbers ourselves (`agent/tavily_tool.py`).
- *Would help:* a documented citation convention for Nemotron, or the serving layer
  stripping this markup when the client didn't ask for it.

**3. Language drift in otherwise good answers.**
- A German question about schools was answered in English when the tool results were
  English.
- A German contact answer slipped in one Spanish word ("Um cualquiera dieser Optionen")
  and switched from *Sie* to *du*.

Naming the answer language at the end of the tool result fixed the first. The second
we only noticed.
- *Would help:* guidance on keeping the response language when context mixes
  languages, which is common for European agents.

**4. Language detection by the model is unreliable for short European queries.** On
the first probe, every model misread at least one French or German request as
Portuguese or English. We moved language detection into code (`agent/lang.py`,
60/60 on the tuning set, 36/36 held out). Not a bug, but worth stating in the docs
for multilingual agents.

**5. Nano's number reading.** Nano 30B-A3B read "até 750€" as 75,000, on both the
tuning and the held-out set. Super, Ultra and Lightning didn't. This is why Nano isn't
our extraction model, though it is the only one we found served in an EU region.
- *Would help:* a regional model table on the catalogue page. Region decides GDPR
  posture for European apps, and we had to infer it.

**6. A repeated question can skip the tool.** When a user repeated a search word
for word, Super answered from conversation history without calling the search tool,
with nothing on screen to back it. We now run the search in code for search turns. A
note in the tool-use docs about history-answering would have saved a debugging round.

**7. What worked well:**
- the OpenAI-compatible API, `json_schema` strict and tool calls worked first time on
  all four models (3/3 tool-call probes each);
- latency with thinking off: about 1s per extraction on Super;
- price: about $0.13 per 1,000 extractions on Super.

Lightning (`Nemotron-3_5-Lightning`) matched Super on the held-out set at half the
latency. We'd use it with a published price and region.

**8. Fine-tuning scope.** Token Factory fine-tuning lists Qwen, Llama, Gemma and
DeepSeek, not Nemotron. For a Nemotron-first hackathon that was a surprise. We used
deterministic normalisation instead of a fine-tuned extractor.

## Nebius AI Cloud (hosting the demo)

**9. Two tenants, one login, no hint.** After `nebius profile create`, the profile
pointed at the Token Factory tenant (`aitenant-…`). There, `iam project list` returns
`PermissionDenied`. The AI Cloud tenant only appeared with `iam v2 tenant list
--format json`; the default table output printed `{}`.
- *Would help:* `profile create` asking which tenant to use, and the table output not
  rendering a non-empty list as `{}`.

**10. Errors before billing is activated say "permission", not "billing".**
- With billing not yet activated, `mysterybox secret create` and `ai endpoint create
  --dry-run` both returned `PermissionDenied`, while reads worked.
- After activation, the dry run moved on to
  `ResourceExhausted … compute.instance.non-gpu.vcpu (limit 0, requested 2)` in
  eu-north1. eu-west2 has a 200-vCPU allowance for the same tenant.

The quota error was clear. The permission error sent us looking at IAM first.
- *Would help:* a `FailedPrecondition: billing not activated` error, and a default CPU
  quota in eu-north1 that isn't zero.

**11. Serverless endpoints are a good fit for a CPU web app.** One command, a public
GHCR image, `--auth none`, `--env-secret` from MysteryBox, and a managed HTTPS URL within
minutes. Smaller things:
- `--description` isn't accepted on `ai endpoint create`, though other resources take it;
- there's no in-place image update, so the URL changes on every redeploy. We put a stable
  redirect in front;
- the docs don't say whether the proxy sets `X-Forwarded-For`. It does, and we
  checked with our own health endpoint.

## Tavily

**12. Query wording changes results a lot.**
- "public transport in Valencia, Spain" returned public.io, a New York Times article
  and FEMA.
- "Valencia, Spain: public transport for residents" returned three relevant guides.
- Without a country, "Valencia" brought Valencia College in Florida.
- About half the results for living-in-a-place queries were Facebook or Instagram posts
  until we passed `exclude_domains`.

`published_date` was empty for every general-topic result, so answers can't say how
current a source is.
- *Would help:* query-shaping guidance in the docs, and a date for general pages when
  one is known.

## Cubi Estate's own connector (our side, for completeness)

**13.** Our connector classified the agent's `cubi-agent/…` User-Agent as Cubi's own
operator traffic, hiding it from usage stats. And anonymous apps shared one per-IP
rate limit. Both are fixed: named deployment tokens with their own budget, and a
separate source label.
