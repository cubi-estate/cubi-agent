# Days 4–5 — held-out eval, agent vs direct search, latency, offline mode (2026-10-20)

## 1. Held-out extraction set

`evals/filter_extraction_heldout.jsonl`: 36 new requests, 6 per language, new
places and phrasings. The normaliser was frozen before the run.
Report: `eval_20261020T151605Z.md`.

| model | fields right | all fields right | route | p50 |
|---|---|---|---|---|
| Nano | 146/148 | 34/36 | 36/36 | 0.79s |
| Lightning | 148/148 | 36/36 | 36/36 | 0.54s |
| Super | 148/148 | 36/36 | 36/36 | 1.05s |
| Ultra | 148/148 | 36/36 | 36/36 | 0.79s |

The language detector got 36/36. Nano repeats its tuning-set error: in
Portuguese it reads "750€" as 75000. **Nano is not promoted.** Super stays the
extraction model. Lightning is as accurate and twice as fast, but its price
and region aren't known yet.

Caveat: the same person wrote the rules and this set. Treat these numbers as an
upper bound until outside users' queries are logged.

## 2. Agent search vs sending the request straight to `search_properties`

`evals/compare_search.py`, on the 31 held-out requests the agent routes to the
structured filter. Final report: `compare_20261020T153024Z.md`. The baseline
before fixes is `compare_20261020T152335Z.md`.

| | agent | direct |
|---|---|---|
| no results | 2 | 4 |
| listings meeting every visible constraint | 142/158 (90%) | 137/146 (94%) |
| latency p50 / max | **1.35s / 2.8s** | 6.0s / 14.7s |
| connector quota units | **33** | 310 |

The agent is about 4× faster and uses about a tenth of the anonymous quota.
Precision is close. 11 of the agent's 13 place mismatches come from
**Cubi data, not the agent**: some `iad_pt` listings carry a wrong region,
for example houses in Viana do Castelo, Portalegre and Coimbra tagged
"Faro District". "Loulé" and "Tavira" then fall back to that region. This is
a follow-up on the cleverdragon side; the example ids are in the git-ignored
report JSON.

Fixes found by this comparison:
- **`has_parking: false`** — the models fill it when parking isn't mentioned,
  and the connector reads it as "no parking". That emptied the studio searches
  in Lisbon and Granada. Now `normalize.py` sets it only when the user asks,
  and `to_filter_args` never sends `false`.
- **Zero results with features → one retry without them.** The retry is
  disclosed in the action log, and the model is told to say so. Feature
  tagging is uneven: a studio with a lift is rarely tagged "Elevator".
- **Rate-limit text counted as results.** The connector answers "Too many
  tool calls…" as ordinary text, which the agent would have shown as "no
  homes". It is now detected as an error, and the eval waits 2.1s between
  calls.

## 3. Where a first turn's time goes

The earlier 15–20s first turn didn't reproduce. Live first turns now take
6–8s; offline, with no connector time, the p50 is 4.8s
(`audit_20261020T153931Z.md`). The turn is three Token Factory round trips:
the loop decides to call `search_homes` (about 1s), extraction (about 1s), and
the answer. The answer step used to write the whole listing list, about 500
output tokens and 3–7s.

## 4. Cards come from code, not from the model

A live German turn ("Wohnung mit Balkon in München") produced **three
invented listings** with plausible `sparkasse:` ids. The URL guard removed
their links, but their prices and places stayed on screen. Offline, the model
also either dropped the list altogether ("liens ci-dessus") or held back
2-bed homes from an "at least 1 bedroom" search. Now:

- the answer event carries `listings`, parsed from the tool output
  (`agent/listings.py`), and the CLI/UI renders them as numbered cards;
- the model writes 2–3 sentences and may refer to "#2", but doesn't list homes;
- the URL guard now drops a whole list item that carries an unverified link,
  not just the link.

Offline audit over 31 turns: 0 guard fixes, median 6 cards, 227 output tokens
per turn across all three calls (the answer itself is about 80–110). Still
open: summary numbers can contradict the cards. One answer called #1 "the
cheapest" while also quoting a lower minimum. A numbers check against the
cards is a candidate guard.

## 5. Offline mode

`CUBI_OFFLINE=1` replays `fixtures/mcp/`, and `CUBI_RECORD=1` records live
replies. Replies are cut down to facts before saving: type, place names
without street or number, size, price, URL, id and at most 5 tags. No
listing title or description is kept. The 31 fixtures were built from the
comparison run (`scripts/fixtures_from_compare.py`) without calling the
connector again. Token Factory is still called in offline mode. There is an
end-to-end test with a scripted model and a fixture directory.

## Next

- Lightning: check its price and region. If it is cheap and EU-hosted, run a
  live A/B on extraction.
- Skip the loop's first round trip when the skill is find-homes and the
  message is a search, which saves about 1s. Stream the summary.
- Add a guard that checks summary numbers against the cards.
- cleverdragon: `iad_pt` region field; "Loulé"/"Tavira" falling back to region.
- Days 6–7: price-check and contact skills end to end; Tavily area compare.
